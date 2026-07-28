"""xcodebuild invocation. The process launcher is injectable.

The output is not parsed, with one exception: lines carrying `error:` — a
long-stable format — are lifted into the error's context. That is what
separates "the build failed" from "MeeshyWatch cannot find WatchConnectivity".
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections import namedtuple

from .. import paths
from ..errors import XcodeError
from . import destination as dest

BuildResult = namedtuple(
    "BuildResult",
    "target action ok duration exit_code destination log_path error result_bundle")

MAX_ERROR_LINES = 10
CI_SIGNING = ["CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_REQUIRED=NO",
              "CODE_SIGN_IDENTITY=", "CODE_SIGN_ENTITLEMENTS=",
              "CODE_SIGNING_INJECT_BASE_ENTITLEMENTS=NO"]


def run_process(argv, cwd=None, stdout=None, merge_stderr=True):
    """Default launcher: actually runs. Tests inject something else.

    merge_stderr is right for build logs — a compiler error on stderr belongs in
    the log next to the line that caused it. It is wrong for anything parsed:
    xcodebuild prefixes `-json` output with warnings like "Using the first of
    multiple matching destinations", which corrupt the payload.
    """
    return subprocess.call(
        argv, cwd=cwd, stdout=stdout,
        stderr=subprocess.STDOUT if merge_stderr else subprocess.DEVNULL)


def xcodebuild_available():
    """Whether xcodebuild is on the PATH — the only DRY-RUN trigger."""
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if directory and os.path.isfile(os.path.join(directory, "xcodebuild")):
            return True
    return False


def _in_ci():
    return (os.environ.get("CI") == "true"
            or os.environ.get("GITHUB_ACTIONS") == "true")


def log_path(project_root, target_name, action):
    directory = os.path.join(paths.andp_dir(project_root), "build", "logs")
    if not os.path.isdir(directory):
        os.makedirs(directory)
    return os.path.join(directory, "%s-%s.log" % (target_name, action))


def _error_lines(path):
    lines = []
    try:
        with open(path) as handle:
            for line in handle:
                if "error:" in line:
                    lines.append(line.rstrip())
    except (IOError, OSError):
        return []
    return lines[-MAX_ERROR_LINES:]


def _base_argv(target, extra=None):
    argv = ["xcodebuild",
            "-scheme", target.scheme,
            "-configuration", target.configuration,
            "-destination", dest.to_argument(target)]
    if _in_ci():
        # Without this, every CI build fails for want of a certificate
        # (ported from build.sh, which did the same).
        argv.extend(CI_SIGNING)
    argv.extend(extra or [])
    return argv


def _invoke(argv, project_dir, path, launcher, append=False):
    launcher = launcher or run_process
    handle = open(path, "a" if append else "w")
    try:
        return launcher(argv, cwd=project_dir, stdout=handle)
    finally:
        handle.close()


def _capture(argv, project_dir, launcher):
    """Run and return (exit_code, stdout) without touching a log file.

    stderr is discarded, not merged: every caller here parses the output as
    JSON, and xcodebuild happily writes warnings to stderr ahead of it.
    """
    launcher = launcher or run_process
    handle = tempfile.TemporaryFile(mode="w+")
    try:
        code = launcher(argv, cwd=project_dir, stdout=handle,
                        merge_stderr=False)
        handle.seek(0)
        return code, handle.read()
    finally:
        handle.close()


def list_schemes(project_dir, run_process=None):
    """The project's schemes, via `xcodebuild -list -json`."""
    code, payload = _capture(["xcodebuild", "-list", "-json"], project_dir,
                             run_process)
    if code != 0:
        raise XcodeError(
            "No usable Xcode project in %s." % project_dir,
            code="no_project",
            remediation=("Check $ANDP_APP_DIR or `project.dir` in andp.yml, and "
                         "that the project has been generated (xcodegen)."),
            context={"project_dir": project_dir})
    try:
        data = json.loads(payload)
    except ValueError:
        raise XcodeError(
            "Unreadable output from `xcodebuild -list -json`.",
            code="no_project",
            remediation="Run `xcodebuild -list` by hand to see what it prints.",
            context={"project_dir": project_dir})
    container = data.get("workspace") or data.get("project") or {}
    return list(container.get("schemes") or [])


def result_bundle_path(project_root, target_name):
    """Where the .xcresult of a test run lands.

    test-report.sh consumes it, so the path is a contract — not an internal
    detail. It lives under .andp/build/ like everything else the tool produces.
    """
    return os.path.join(paths.andp_dir(project_root), "build",
                        "%s.xcresult" % target_name)


def _result(target, action, ok, started, code, path, error, bundle=None):
    return BuildResult(target=target.name, action=action, ok=ok,
                       duration=round(time.time() - started, 2), exit_code=code,
                       destination=dest.to_argument(target), log_path=path,
                       error=error, result_bundle=bundle)


def _failure(target, code, error_code, path, message):
    return XcodeError(
        message, code=error_code,
        remediation="Read the full log: %s" % path,
        context={"target": target.name, "exit_code": code, "log": path,
                 "errors": _error_lines(path)})


def build(target, project_dir, project_root=".", archive=False, run_process=None):
    """Compile the target. With archive=True, chains archive then exportArchive."""
    if archive and target.destination != dest.GENERIC:
        raise XcodeError(
            "Archiving requires `destination: generic` (got: %s)."
            % target.destination,
            code="bad_target_config",
            remediation="Archiving for a simulator produces nothing installable.",
            context={"target": target.name, "destination": target.destination})

    action = "archive" if archive else "build"
    path = log_path(project_root, target.name, action)
    started = time.time()

    if not archive:
        code = _invoke(_base_argv(target, ["build"]), project_dir, path,
                       run_process)
        error = None if code == 0 else _failure(
            target, code, "build_failed", path,
            "xcodebuild exited with %s." % code)
        return _result(target, action, code == 0, started, code, path, error)

    build_dir = os.path.join(paths.andp_dir(project_root), "build")
    archive_path = os.path.join(build_dir, "%s.xcarchive" % target.name)
    export_path = os.path.join(build_dir, "exported")

    code = _invoke(_base_argv(target, ["archive", "-archivePath", archive_path]),
                   project_dir, path, run_process)
    if code != 0:
        error = _failure(target, code, "build_failed", path,
                         "Archiving exited with %s." % code)
        return _result(target, action, False, started, code, path, error)

    code = _invoke(["xcodebuild", "-exportArchive",
                    "-archivePath", archive_path,
                    "-exportPath", export_path],
                   project_dir, path, run_process, append=True)
    error = None if code == 0 else _failure(
        target, code, "export_failed", path,
        "Exporting the archive exited with %s." % code)
    return _result(target, action, code == 0, started, code, path, error)


def test(target, project_dir, project_root=".", run_process=None):
    path = log_path(project_root, target.name, "test")
    bundle = result_bundle_path(project_root, target.name)
    if os.path.isdir(bundle):
        # xcodebuild refuses to overwrite an existing bundle.
        shutil.rmtree(bundle)
    started = time.time()
    code = _invoke(_base_argv(target, ["test", "-resultBundlePath", bundle]),
                   project_dir, path, run_process)
    error = None if code == 0 else _failure(
        target, code, "test_failed", path,
        "The test suite exited with %s." % code)
    return _result(target, "test", code == 0, started, code, path, error,
                   bundle=bundle)


def app_path(target, project_dir, run_process=None):
    """The built .app, via -showBuildSettings. Needed to install and launch."""
    code, payload = _capture(_base_argv(target, ["-showBuildSettings", "-json"]),
                             project_dir, run_process)
    settings = {}
    if code == 0:
        try:
            for entry in json.loads(payload):
                settings = entry.get("buildSettings") or {}
                break
        except (ValueError, AttributeError):
            settings = {}
    directory = settings.get("TARGET_BUILD_DIR")
    name = settings.get("FULL_PRODUCT_NAME")
    if not directory or not name:
        raise XcodeError(
            "Cannot locate the built product of `%s`." % target.name,
            code="app_not_found",
            remediation="Build the target first: andp build %s" % target.name,
            context={"target": target.name, "project_dir": project_dir})
    return os.path.join(directory, name)
