"""Invocation xcodebuild — via lanceur injecté. Aucun test ne lance xcodebuild."""
import json
import os

import pytest

from andp.errors import XcodeError
from andp.xcode import runner
from andp.xcode.targets import Target


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """$ANDP_CONFIG_DIR détournerait .andp/ hors de tmp_path."""
    monkeypatch.delenv("ANDP_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def _t(**kwargs):
    base = dict(name="dev", scheme="Meeshy", platform="iOS",
                destination="iPhone 15", configuration="Debug", os=None)
    base.update(kwargs)
    return Target(**base)


class FakeProcess(object):
    """Enregistre l'argv reçu et renvoie un code choisi."""

    def __init__(self, code=0, stdout=""):
        self.calls = []
        self.code = code
        self.stdout = stdout

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        handle = kwargs.get("stdout")
        if handle is not None and hasattr(handle, "write"):
            handle.write(self.stdout)
        return self.code


def test_build_argv_carries_scheme_configuration_and_destination(tmp_path):
    fake = FakeProcess()
    runner.build(_t(), str(tmp_path), str(tmp_path), run_process=fake)
    argv = fake.calls[0]
    assert argv[0] == "xcodebuild"
    assert argv[argv.index("-scheme") + 1] == "Meeshy"
    assert argv[argv.index("-configuration") + 1] == "Debug"
    assert argv[argv.index("-destination") + 1] == \
        "platform=iOS Simulator,name=iPhone 15"
    assert argv[-1] == "build"


def test_successful_build_result(tmp_path):
    result = runner.build(_t(), str(tmp_path), str(tmp_path),
                          run_process=FakeProcess(0))
    assert result.ok is True
    assert result.exit_code == 0
    assert result.error is None
    assert result.target == "dev"
    assert result.action == "build"
    assert result.duration >= 0


def test_failed_build_carries_a_typed_error(tmp_path):
    """Un build cassé ne lève pas: il rend un résultat portant l'erreur, pour que
    les cibles suivantes s'exécutent quand même."""
    fake = FakeProcess(65, stdout="Meeshy/App.swift:12: error: no such module\n")
    result = runner.build(_t(), str(tmp_path), str(tmp_path), run_process=fake)
    assert result.ok is False
    assert result.error.code == "build_failed"
    assert result.error.retryable is False
    assert "no such module" in result.error.context["errors"][0]
    assert result.error.context["exit_code"] == 65


def test_log_is_written_under_the_andp_namespace(tmp_path):
    fake = FakeProcess(0, stdout="compiling...\n")
    result = runner.build(_t(), str(tmp_path), str(tmp_path), run_process=fake)
    assert os.path.exists(result.log_path)
    assert ".andp" in result.log_path and "dev-build" in result.log_path
    with open(result.log_path) as handle:
        assert "compiling" in handle.read()


def test_only_the_last_ten_error_lines_are_kept(tmp_path):
    noise = "".join("f.swift:%d: error: e%d\n" % (i, i) for i in range(30))
    result = runner.build(_t(), str(tmp_path), str(tmp_path),
                          run_process=FakeProcess(65, noise))
    assert len(result.error.context["errors"]) == runner.MAX_ERROR_LINES
    assert "e29" in result.error.context["errors"][-1]


def test_lines_without_the_error_marker_are_ignored(tmp_path):
    output = "note: something\nwarning: else\nf.swift:1: error: real\n"
    result = runner.build(_t(), str(tmp_path), str(tmp_path),
                          run_process=FakeProcess(65, output))
    assert result.error.context["errors"] == ["f.swift:1: error: real"]


def test_ci_disables_code_signing(tmp_path, monkeypatch):
    monkeypatch.setenv("CI", "true")
    fake = FakeProcess()
    runner.build(_t(), str(tmp_path), str(tmp_path), run_process=fake)
    assert "CODE_SIGNING_ALLOWED=NO" in fake.calls[0]


def test_github_actions_also_disables_code_signing(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    fake = FakeProcess()
    runner.build(_t(), str(tmp_path), str(tmp_path), run_process=fake)
    assert "CODE_SIGN_IDENTITY=" in fake.calls[0]


def test_no_signing_flags_outside_ci(tmp_path):
    fake = FakeProcess()
    runner.build(_t(), str(tmp_path), str(tmp_path), run_process=fake)
    assert "CODE_SIGNING_ALLOWED=NO" not in fake.calls[0]


def test_archive_chains_archive_then_export(tmp_path):
    fake = FakeProcess()
    result = runner.build(_t(destination="generic"), str(tmp_path), str(tmp_path),
                          archive=True, run_process=fake)
    assert len(fake.calls) == 2
    assert "archive" in fake.calls[0]
    assert "-archivePath" in fake.calls[0]
    assert "-exportArchive" in fake.calls[1]
    assert result.ok is True
    assert result.action == "archive"


def test_archive_exports_where_sign_sh_reads(tmp_path):
    """sign.sh consomme .andp/build/exported — le chemin est un contrat."""
    fake = FakeProcess()
    runner.build(_t(destination="generic"), str(tmp_path), str(tmp_path),
                 archive=True, run_process=fake)
    export = fake.calls[1][fake.calls[1].index("-exportPath") + 1]
    assert export.endswith(os.path.join(".andp", "build", "exported"))


def test_archive_refuses_a_named_simulator(tmp_path):
    with pytest.raises(XcodeError) as excinfo:
        runner.build(_t(destination="iPhone 15"), str(tmp_path), str(tmp_path),
                     archive=True, run_process=FakeProcess())
    assert excinfo.value.code == "bad_target_config"


def test_archive_failure_does_not_attempt_the_export(tmp_path):
    fake = FakeProcess(65)
    result = runner.build(_t(destination="generic"), str(tmp_path), str(tmp_path),
                          archive=True, run_process=fake)
    assert len(fake.calls) == 1
    assert result.error.code == "build_failed"


def test_export_failure_has_its_own_code(tmp_path):
    class FailSecond(FakeProcess):
        def __call__(self, argv, **kwargs):
            FakeProcess.__call__(self, argv, **kwargs)
            return 0 if len(self.calls) == 1 else 70

    result = runner.build(_t(destination="generic"), str(tmp_path), str(tmp_path),
                          archive=True, run_process=FailSecond())
    assert result.error.code == "export_failed"


def test_test_action_uses_the_test_verb(tmp_path):
    fake = FakeProcess()
    result = runner.test(_t(), str(tmp_path), str(tmp_path), run_process=fake)
    assert "test" in fake.calls[0]
    assert result.action == "test"
    assert "dev-test" in result.log_path


def test_test_writes_a_result_bundle(tmp_path):
    """test-report.sh consomme le .xcresult — le chemin est un contrat."""
    fake = FakeProcess()
    result = runner.test(_t(), str(tmp_path), str(tmp_path), run_process=fake)
    argv = fake.calls[0]
    assert argv[argv.index("-resultBundlePath") + 1] == result.result_bundle
    assert result.result_bundle.endswith(os.path.join(".andp", "build",
                                                      "dev.xcresult"))


def test_a_stale_result_bundle_is_removed(tmp_path):
    """xcodebuild refuse d'écraser un bundle existant."""
    stale = runner.result_bundle_path(str(tmp_path), "dev")
    os.makedirs(stale)
    (open(os.path.join(stale, "old"), "w")).close()
    runner.test(_t(), str(tmp_path), str(tmp_path), run_process=FakeProcess())
    assert not os.path.exists(os.path.join(stale, "old"))


def test_build_has_no_result_bundle(tmp_path):
    result = runner.build(_t(), str(tmp_path), str(tmp_path),
                          run_process=FakeProcess())
    assert result.result_bundle is None


def test_failed_test_has_its_own_code(tmp_path):
    result = runner.test(_t(), str(tmp_path), str(tmp_path),
                         run_process=FakeProcess(65))
    assert result.error.code == "test_failed"


def test_parsed_output_never_merges_stderr(tmp_path):
    """xcodebuild préfixe le JSON d'avertissements sur stderr.

    Les fusionner corrompt le payload: `-showBuildSettings -json` renvoyait
    « xcodebuild: WARNING: Using the first of multiple matching destinations »
    avant le JSON, et `andp run` répondait app_not_found après un build réussi.
    """
    class Spy(FakeProcess):
        def __init__(self, *a, **kw):
            FakeProcess.__init__(self, *a, **kw)
            self.merge_flags = []

        def __call__(self, argv, **kwargs):
            self.merge_flags.append(kwargs.get("merge_stderr"))
            return FakeProcess.__call__(self, argv, **kwargs)

    spy = Spy(0, json.dumps({"project": {"schemes": ["A"]}}))
    runner.list_schemes(str(tmp_path), run_process=spy)
    assert spy.merge_flags == [False]

    spy = Spy(0, json.dumps([{"buildSettings": {"TARGET_BUILD_DIR": "/b",
                                                "FULL_PRODUCT_NAME": "A.app"}}]))
    runner.app_path(_t(), str(tmp_path), run_process=spy)
    assert spy.merge_flags == [False]


def test_build_logs_do_keep_stderr(tmp_path):
    """À l'inverse: une erreur de compilation doit atterrir dans le log."""
    class Spy(FakeProcess):
        def __init__(self, *a, **kw):
            FakeProcess.__init__(self, *a, **kw)
            self.merge_flags = []

        def __call__(self, argv, **kwargs):
            self.merge_flags.append(kwargs.get("merge_stderr", True))
            return FakeProcess.__call__(self, argv, **kwargs)

    spy = Spy()
    runner.build(_t(), str(tmp_path), str(tmp_path), run_process=spy)
    assert spy.merge_flags == [True]


def test_list_schemes_parses_a_project_payload(tmp_path):
    payload = json.dumps({"project": {"schemes": ["Meeshy", "MeeshyWatch"]}})
    assert runner.list_schemes(str(tmp_path),
                               run_process=FakeProcess(0, payload)) == \
        ["Meeshy", "MeeshyWatch"]


def test_list_schemes_reads_a_workspace_payload(tmp_path):
    payload = json.dumps({"workspace": {"schemes": ["A"]}})
    assert runner.list_schemes(str(tmp_path),
                               run_process=FakeProcess(0, payload)) == ["A"]


def test_list_schemes_without_a_project(tmp_path):
    with pytest.raises(XcodeError) as excinfo:
        runner.list_schemes(str(tmp_path), run_process=FakeProcess(66, "nope"))
    assert excinfo.value.code == "no_project"
    assert excinfo.value.context["project_dir"] == str(tmp_path)


def test_list_schemes_on_unreadable_output(tmp_path):
    with pytest.raises(XcodeError) as excinfo:
        runner.list_schemes(str(tmp_path), run_process=FakeProcess(0, "not json"))
    assert excinfo.value.code == "no_project"


def test_app_path_is_read_from_build_settings(tmp_path):
    payload = json.dumps([{"buildSettings": {"TARGET_BUILD_DIR": "/b/Debug",
                                             "FULL_PRODUCT_NAME": "Meeshy.app"}}])
    assert runner.app_path(_t(), str(tmp_path),
                           run_process=FakeProcess(0, payload)) == \
        os.path.join("/b/Debug", "Meeshy.app")


def test_app_path_without_settings_raises(tmp_path):
    with pytest.raises(XcodeError) as excinfo:
        runner.app_path(_t(), str(tmp_path), run_process=FakeProcess(1, ""))
    assert excinfo.value.code == "app_not_found"


def test_xcodebuild_available_reflects_the_path(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    assert runner.xcodebuild_available() is False
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "xcodebuild").write_text("#!/bin/sh\n")
    monkeypatch.setenv("PATH", str(fake_bin))
    assert runner.xcodebuild_available() is True
