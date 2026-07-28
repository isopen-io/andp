"""En --json, stdout est toujours du JSON — y compris sans configuration.

Un agent qui ne peut pas parser stdout perd le code, retryable et la remediation:
il ne sait ni ce qui a échoué, ni s'il doit réessayer.
"""
import json

import pytest

from andp.asc.asc_manager import main


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ANDP_CONFIG_DIR", raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("argv", [
    ["verify"],
    ["upload", "app.ipa"],
    ["status", "me.app", "42"],
    ["submit", "me.app", "1.0"],
    ["precheck", "me.app", "1.0"],
    ["readiness", "testflight", "me.app"],
    ["store", "apply", "me.app"],
])
def test_json_stays_parsable_without_any_config(argv, capsys):
    rc = main(argv + ["--json"])
    payload = json.loads(capsys.readouterr().out)      # ne doit pas lever
    assert rc == 1
    assert payload["ok"] is False
    assert payload["error"]["code"] == "config_not_found"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["remediation"]


def test_json_envelope_for_a_misplaced_file(tmp_path, capsys):
    (tmp_path / "secrets.yml").write_text("accounts: {}\n")
    rc = main(["verify", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"]["code"] == "config_misplaced"
    assert payload["error"]["context"]["misplaced"].endswith("secrets.yml")


def test_human_mode_keeps_stdout_clean(capsys):
    """Le message humain va sur stderr — stdout reste réservé aux données."""
    rc = main(["verify"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "config" in captured.err.lower() or "secrets" in captured.err.lower()


def test_build_number_still_runs_without_credentials(capsys):
    """L'exception existante ne doit pas être régressée par l'enveloppe."""
    rc = main(["build-number", "--strategy", "timestamp"])
    assert rc == 0
    assert capsys.readouterr().out.strip().isdigit()
