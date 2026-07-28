"""Agrégation multi-cibles — avec lanceur injecté, ce que main() n'expose pas."""
import pytest

from andp.xcode import commands
from andp.xcode.targets import Target


@pytest.fixture(autouse=True)
def with_xcodebuild(tmp_path, monkeypatch):
    """Un faux xcodebuild sur le PATH et un projet factice.

    Sans le premier tout part en DRY-RUN ; sans le second, ensure_project
    coupe avant la boucle — ce qui est précisément son rôle.
    """
    monkeypatch.delenv("ANDP_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "xcodebuild").write_text("#!/bin/sh\n")
    monkeypatch.setenv("PATH", str(fake_bin))
    (tmp_path / "Demo.xcodeproj").mkdir()


def _t(name, **kwargs):
    base = dict(name=name, scheme="S", platform="iOS", destination="generic",
                configuration="Debug", os=None)
    base.update(kwargs)
    return Target(**base)


class FailAfterFirst(object):
    """Réussit le premier appel, échoue tous les suivants."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        return 0 if len(self.calls) == 1 else 65


def test_execution_continues_past_a_failure(tmp_path):
    """Une cible cassée ne doit pas masquer l'état des suivantes."""
    envelope = commands.build_targets(
        [_t("a"), _t("b"), _t("c")], str(tmp_path), str(tmp_path),
        run_process=FailAfterFirst())
    assert [r["target"] for r in envelope["results"]] == ["a", "b", "c"]
    assert [r["ok"] for r in envelope["results"]] == [True, False, False]


def test_envelope_ok_is_the_conjunction(tmp_path):
    envelope = commands.build_targets([_t("a"), _t("b")], str(tmp_path),
                                      str(tmp_path), run_process=FailAfterFirst())
    assert envelope["ok"] is False


def test_all_green_yields_a_green_envelope(tmp_path):
    launcher = lambda argv, **kwargs: 0
    envelope = commands.build_targets([_t("a"), _t("b")], str(tmp_path),
                                      str(tmp_path), run_process=launcher)
    assert envelope["ok"] is True
    assert envelope["dry_run"] is False


def test_failed_entries_carry_their_error(tmp_path):
    envelope = commands.build_targets([_t("a"), _t("b")], str(tmp_path),
                                      str(tmp_path), run_process=FailAfterFirst())
    failed = envelope["results"][1]
    assert failed["error"]["code"] == "build_failed"
    assert failed["error"]["retryable"] is False
    assert failed["log"].endswith("b-build.log")


def test_successful_entries_have_no_error_key(tmp_path):
    envelope = commands.build_targets([_t("a")], str(tmp_path), str(tmp_path),
                                      run_process=lambda argv, **kw: 0)
    assert "error" not in envelope["results"][0]


def test_each_target_gets_its_own_log(tmp_path):
    envelope = commands.build_targets([_t("a"), _t("b")], str(tmp_path),
                                      str(tmp_path),
                                      run_process=lambda argv, **kw: 0)
    logs = [r["log"] for r in envelope["results"]]
    assert len(set(logs)) == 2


def test_test_targets_uses_the_test_action(tmp_path):
    envelope = commands.test_targets([_t("a")], str(tmp_path), str(tmp_path),
                                     run_process=lambda argv, **kw: 0)
    assert envelope["command"] == "test"
    assert envelope["results"][0]["log"].endswith("a-test.log")


def test_dry_run_skips_every_invocation(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    calls = []
    envelope = commands.build_targets(
        [_t("a"), _t("b")], str(tmp_path), str(tmp_path),
        run_process=lambda argv, **kw: calls.append(argv) or 0)
    assert calls == []
    assert envelope["dry_run"] is True
    assert all(r["skipped"] for r in envelope["results"])
