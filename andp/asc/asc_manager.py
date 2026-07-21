"""ANDP App Store Connect CLI.

Wires auth -> client -> managers and exposes the commands used by the
shell wrappers (asc-manager.sh) and the CI pipeline.

Without real credentials (secrets.example.yml placeholders) every command
runs in DRY-RUN mode: it validates inputs and prints what it would do,
so CI stays green without an Apple account.
"""
import json
import os
import sys

from .apps import AppsManager
from .appstore import AppStoreManager
from .auth import ASCAuth, ASCAuthError
from .builds import BuildProcessingError, BuildsManager
from .client import ASCAPIError, ASCClient
from .config import ConfigError, load_account
from .managers import Managers, make_managers
from .testflight import TestFlightManager

USAGE = """Usage: asc_manager.py <command> [args] [--account <account_id>]

Commands (all accept --json for a structured, agent-friendly envelope):
  verify [bundle_id]                             Preflight: credentials -> JWT -> API -> app lookup
                                                 (exits 1 when publishing is not possible)
  upload <ipa_path>                              Upload a build (Build Upload API)
  release <ipa_path> [--group <name>]            verify -> upload -> wait processing -> TestFlight group
  status <bundle_id> <build_number>              Poll build processing state
  testflight <bundle_id> <group> add [emails...] Manage TestFlight group testers
  submit <bundle_id> <version>                   Submit a version for App Review
"""


def _read_file_stripped(path, default=""):
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read().strip()
    return default


def _ipa_metadata(ipa_path):
    """(bundle_id, version, build) from the IPA's own Info.plist — the upload
    metadata must match the binary, not the calling repo. All None if unreadable."""
    import plistlib
    import zipfile

    try:
        with zipfile.ZipFile(ipa_path) as zf:
            for name in zf.namelist():
                if name.endswith(".app/Info.plist") and name.startswith("Payload/"):
                    info = plistlib.loads(zf.read(name))
                    return (
                        info.get("CFBundleIdentifier"),
                        info.get("CFBundleShortVersionString"),
                        info.get("CFBundleVersion"),
                    )
    except Exception:
        pass
    return None, None, None


def _cmd_verify(account, managers, dry_run, args, json_mode=False):
    """Publish preflight. Unlike the other commands this one FAILS in DRY-RUN:
    its whole point is to tell the truth about whether publishing can work."""
    bundle_id = args[0] if args else None
    checks = []
    app_payload = None

    def check(name, ok, text, **extra):
        checks.append({"name": name, "ok": ok, "detail": text, **extra})
        if not json_mode:
            print(f"  {'✅' if ok else '❌'} {text}")

    def finish(ok):
        if json_mode:
            payload = {"command": "verify", "ok": ok, "checks": checks}
            if app_payload:
                payload["app"] = app_payload
            print(json.dumps(payload))
        else:
            if ok:
                print("PREFLIGHT PASSED — the tool can publish to App Store Connect.")
        return 0 if ok else 1

    if not json_mode:
        print(f"ASC publish preflight (account '{account.account_id}'):")

    missing = account.missing_fields()
    if missing:
        for name in missing:
            if not json_mode:
                print(f"  ❌ credentials — missing: {name} (absent or placeholder in secrets.yml)")
        checks.append({"name": "credentials", "ok": False,
                       "detail": "missing or placeholder fields", "missing": missing})
        if not json_mode:
            print("PREFLIGHT FAILED — fill in the fields above (template: secrets.example.yml).")
        return finish(False)
    check("credentials", True,
          f"credentials — key_id {account.key_id}, issuer_id set, private key present")

    try:
        managers.client.auth.token()
    except ASCAuthError as exc:
        check("jwt", False, f"JWT signing failed: {exc}")
        if not json_mode:
            print("PREFLIGHT FAILED — the private key is not a usable ES256 (.p8) key.")
        return finish(False)
    check("jwt", True, "JWT signed (ES256)")

    try:
        if bundle_id:
            app = managers.apps.find_app(bundle_id)
            check("api_auth", True, "API authentication accepted")
            if app is None:
                check("app_record", False,
                      f"app '{bundle_id}' not found on this App Store Connect account")
                if not json_mode:
                    print("PREFLIGHT FAILED — create the app record in the ASC UI first.")
                return finish(False)
            name = (app.get("attributes") or {}).get("name", "?")
            app_payload = {"id": app["id"], "name": name, "bundle_id": bundle_id}
            check("app_record", True, f"app found: {name} ({bundle_id}) — id {app['id']}")
        else:
            managers.client.get("/v1/apps", params={"limit": 1})
            check("api_auth", True, "API authentication accepted (GET /v1/apps)")
    except ASCAPIError as exc:
        check("api_auth", False, f"API rejected the request: {exc}")
        if not json_mode:
            print("PREFLIGHT FAILED — check key_id/issuer_id and the key's ASC role.")
        return finish(False)

    return finish(True)


def _cmd_upload(account, managers, dry_run, args, json_mode=False):
    if not args:
        print("Error: IPA path required for upload.")
        return 2
    ipa_path = args[0]
    if not os.path.exists(ipa_path):
        print(f"Error: IPA not found: {ipa_path}")
        return 1
    bundle_id, version, build_number = _ipa_metadata(ipa_path)
    if not version:
        version = _read_file_stripped("VERSION", "0.0.0")
    if not build_number:
        build_number = _read_file_stripped("BUILD_NUMBER", "0")

    if dry_run:
        if json_mode:
            print(json.dumps({"command": "upload", "ok": True, "dry_run": True,
                              "ipa": ipa_path, "bundle_id": bundle_id,
                              "version": version, "build_number": build_number}))
        else:
            print(
                f"[DRY-RUN] Would upload {ipa_path} as version {version} "
                f"(build {build_number}) via the Build Upload API."
            )
        return 0

    if not bundle_id:
        print(f"Error: Could not read CFBundleIdentifier from {ipa_path}.")
        return 1
    app = managers.apps.find_app(bundle_id)
    if app is None:
        print(f"Error: App {bundle_id} not found in App Store Connect.")
        return 1

    upload_id = managers.builds.upload_ipa(
        ipa_path, version=version, build_number=build_number, app_id=app["id"]
    )
    if json_mode:
        print(json.dumps({"command": "upload", "ok": True, "dry_run": False,
                          "ipa": ipa_path, "bundle_id": bundle_id,
                          "version": version, "build_number": build_number,
                          "app_id": app["id"], "upload_id": upload_id}))
    else:
        print(f"Upload started: buildUploads/{upload_id}")
    return 0


def _cmd_release(account, managers, dry_run, args, json_mode=False):
    """One-shot automation primitive: verify app record -> upload -> wait for
    Apple processing -> optional TestFlight group assignment.

    Subcommands expose the resumable machine for agents:
      release start <ipa> [--group G]   begin (or resume) a release -> release_id
      release poll <id>                 advance one non-blocking step
      release status <id>               read state without advancing
      release list                      list all releases
    """
    args = list(args)
    if args and args[0] in ("start", "poll", "status", "list", "reset", "approve"):
        return _cmd_release_sub(account, args[0], args[1:], json_mode)

    group_name = None
    if "--group" in args:
        idx = args.index("--group")
        group_name = args[idx + 1]
        del args[idx:idx + 2]
    if not args:
        print("Usage: release <ipa_path> [--group <name>]")
        return 2
    ipa_path = args[0]
    if not os.path.exists(ipa_path):
        print(f"Error: IPA not found: {ipa_path}")
        return 1
    bundle_id, version, build_number = _ipa_metadata(ipa_path)

    if dry_run:
        planned = ["app_record", "upload", "processing"] + (["testflight_group"] if group_name else [])
        if json_mode:
            print(json.dumps({"command": "release", "ok": True, "dry_run": True,
                              "ipa": ipa_path, "bundle_id": bundle_id,
                              "stages_planned": planned}))
        else:
            print(f"[DRY-RUN] Would release {ipa_path}: {' -> '.join(planned)}.")
        return 0

    stages = []

    def stage(name, ok, detail):
        stages.append({"name": name, "ok": ok, "detail": detail})
        if not json_mode:
            print(f"  {'✅' if ok else '❌'} {name}: {detail}")

    def finish(ok, build=None, app_id=None, upload_id=None):
        if json_mode:
            payload = {"command": "release", "ok": ok, "dry_run": False,
                       "ipa": ipa_path, "bundle_id": bundle_id, "stages": stages}
            if app_id:
                payload["app_id"] = app_id
            if upload_id:
                payload["upload_id"] = upload_id
            if build is not None:
                payload["build"] = {
                    "id": build["id"],
                    "processing_state": build["attributes"].get("processingState"),
                }
            print(json.dumps(payload))
        else:
            print("RELEASE " + ("SUCCEEDED" if ok else "FAILED"))
        return 0 if ok else 1

    if not bundle_id:
        stage("app_record", False, f"Could not read CFBundleIdentifier from {ipa_path}")
        return finish(False)
    app = managers.apps.find_app(bundle_id)
    if app is None:
        stage("app_record", False, f"App {bundle_id} not found in App Store Connect")
        return finish(False)
    app_name = (app.get("attributes") or {}).get("name", "?")
    stage("app_record", True, f"{app_name} ({bundle_id}) — id {app['id']}")

    upload_id = managers.builds.upload_ipa(
        ipa_path, version=version, build_number=build_number, app_id=app["id"]
    )
    stage("upload", True, f"buildUploads/{upload_id} ({version} build {build_number})")

    try:
        build = managers.builds.wait_for_processing(app["id"], build_number)
    except BuildProcessingError as exc:
        stage("processing", False, str(exc))
        return finish(False, app_id=app["id"], upload_id=upload_id)
    stage("processing", True, f"build {build['id']} is {build['attributes'].get('processingState')}")

    if group_name:
        group = managers.testflight.ensure_group(app["id"], group_name)
        managers.testflight.add_build_to_group(group["id"], build["id"])
        stage("testflight_group", True, f"build linked to group '{group_name}' ({group['id']})")

    return finish(True, build=build, app_id=app["id"], upload_id=upload_id)


def _cmd_release_sub(account, sub, args, json_mode):
    """Agent-facing release subcommands, backed by the library service layer."""
    from .. import service

    group = None
    args = list(args)
    if "--group" in args:
        idx = args.index("--group")
        group = args[idx + 1]
        del args[idx:idx + 2]
    ship = False
    if "--ship" in args:
        ship = True
        args.remove("--ship")

    if sub == "start":
        if not args:
            print("Usage: release start <ipa_path> [--group <name>] [--ship]")
            return 2
        result = service.release_start(args[0], account=account.account_id,
                                       group=group, ship=ship)
    elif sub == "poll":
        if not args:
            print("Usage: release poll <release_id>")
            return 2
        result = service.release_poll(args[0], account=account.account_id)
    elif sub == "status":
        if not args:
            print("Usage: release status <release_id>")
            return 2
        result = service.release_status(args[0])
    elif sub == "approve":
        if not args:
            print("Usage: release approve <release_id>")
            return 2
        result = service.release_approve(args[0], account=account.account_id)
    elif sub == "reset":
        if not args:
            print("Usage: release reset <release_id>")
            return 2
        result = service.release_reset_by_id(args[0])
    else:  # list
        result = service.release_list()

    if json_mode:
        print(json.dumps(result))
    else:
        _print_release_human(result)
    return 0 if result.get("ok", True) else 1


def _print_release_human(result):
    cmd = result.get("command", "release")
    if not result.get("ok", True):
        err = result.get("error", {})
        print(f"❌ {cmd}: {err.get('message', 'failed')}")
        if err.get("remediation"):
            print(f"   → {err['remediation']}")
        return
    if cmd == "release_list":
        for r in result["releases"]:
            print(f"  {r['release_id']}: {r['state']}")
        if not result["releases"]:
            print("  (no releases)")
        return
    if result.get("dry_run"):
        print(f"[DRY-RUN] {result['release_id']}: {' -> '.join(result.get('plan', []))}")
        return
    line = f"{result['release_id']}: {result['state']}"
    if result.get("retry_after"):
        line += f" (poll again in {result['retry_after']}s)"
    if result.get("build"):
        line += f" — build {result['build']['id']} {result['build'].get('processing_state', '')}"
    print(line)


def _cmd_status(account, managers, dry_run, args, json_mode=False):
    if len(args) < 2:
        print("Usage: status <bundle_id> <build_number>")
        return 2
    bundle_id, build_number = args[0], args[1]

    if dry_run:
        print(f"[DRY-RUN] Would poll processing state of build {build_number} for {bundle_id}.")
        return 0

    app = managers.apps.find_app(bundle_id)
    if app is None:
        print(f"Error: App {bundle_id} not found in App Store Connect.")
        return 1
    build = managers.builds.wait_for_processing(app["id"], build_number)
    print(f"Build {build_number}: {build['attributes']['processingState']}")
    return 0


def _cmd_testflight(account, managers, dry_run, args, json_mode=False):
    if len(args) < 3:
        print("Usage: testflight <bundle_id> <group_name> <add> [tester_emails...]")
        return 2
    bundle_id, group_name, action = args[0], args[1], args[2]
    emails = args[3:]

    if dry_run:
        print(
            f"[DRY-RUN] Would ensure group '{group_name}' on {bundle_id} "
            f"and {action} testers: {', '.join(emails) or '(none)'}"
        )
        return 0

    app = managers.apps.find_app(bundle_id)
    if app is None:
        print(f"Error: App {bundle_id} not found in App Store Connect.")
        return 1
    group = managers.testflight.ensure_group(app["id"], group_name)
    if action == "add":
        for email in emails:
            managers.testflight.add_tester(group["id"], email)
            print(f"Added tester {email} to '{group_name}'.")
    else:
        print(f"Error: Unsupported testflight action '{action}'.")
        return 2
    return 0


def _cmd_submit(account, managers, dry_run, args, json_mode=False):
    if len(args) < 2:
        print("Usage: submit <bundle_id> <version>")
        return 2
    bundle_id, version = args[0], args[1]

    if dry_run:
        print(f"[DRY-RUN] Would submit version {version} of {bundle_id} for App Review.")
        return 0

    app = managers.apps.find_app(bundle_id)
    if app is None:
        print(f"Error: App {bundle_id} not found in App Store Connect.")
        return 1
    app_store_version = managers.appstore.ensure_version(app["id"], version)

    # Apple rejects a review submission whose version has no build attached.
    build = managers.builds.latest_valid_build(app["id"])
    if build is None:
        print(
            f"Error: No VALID build found for {bundle_id}. Upload a build and wait "
            "for it to finish processing before submitting for review."
        )
        return 1
    managers.appstore.attach_build(app_store_version["id"], build["id"])

    submission = managers.appstore.submit_for_review(app["id"], app_store_version["id"])
    print(f"Review submission {submission['id']}: {submission['attributes'].get('state')}")
    return 0


COMMANDS = {
    "verify": _cmd_verify,
    "upload": _cmd_upload,
    "release": _cmd_release,
    "status": _cmd_status,
    "testflight": _cmd_testflight,
    "submit": _cmd_submit,
}


def main(argv):
    if not argv:
        print(USAGE)
        return 2

    args = list(argv)
    account_id = "primary"
    if "--account" in args:
        idx = args.index("--account")
        account_id = args[idx + 1]
        del args[idx:idx + 2]
    json_mode = "--json" in args
    if json_mode:
        args.remove("--json")

    command, command_args = args[0], args[1:]
    handler = COMMANDS.get(command)
    if handler is None:
        print(USAGE)
        print(f"Unknown command: {command}")
        return 2

    try:
        account = load_account(account_id)
    except ConfigError as exc:
        print(f"Error: {exc}")
        return 1

    dry_run = not account.is_configured()
    if dry_run and not json_mode:
        print(
            f"No real App Store Connect credentials for account '{account_id}' "
            "(placeholders detected) — running in DRY-RUN mode."
        )
        managers = None
    else:
        managers = make_managers(account)

    return handler(account, managers, dry_run, command_args, json_mode=json_mode)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
