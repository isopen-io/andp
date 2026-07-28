"""Enveloppe des commandes locales — un build ne parle pas à Apple.

En --json, stdout reste parsable même sans configuration et sans xcodebuild.
"""
import json

import pytest

from andp.asc.asc_manager import main

PROJECT = """
targets:
  defaults:
    scheme: Meeshy
  dev:
    platform: iOS
    destination: "iPhone 15"
  vision:
    platform: visionOS
    destination: "Apple Vision Pro"
"""


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ANDP_CONFIG_DIR", raising=False)
    monkeypatch.delenv("ANDP_APP_DIR", raising=False)
    monkeypatch.setenv("PATH", "")          # pas de xcodebuild → DRY-RUN
    monkeypatch.chdir(tmp_path)
    (tmp_path / "andp.yml").write_text(PROJECT)
    return tmp_path


def test_build_runs_without_credentials(capsys):
    """Aucun credential : un build ne parle pas à App Store Connect."""
    rc = main(["build", "dev", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True
    assert payload["dry_run"] is True


def test_dry_run_is_declared_never_silent(capsys):
    """Le défaut de build.sh : succès muet sans xcodebuild."""
    rc = main(["build", "dev"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "DRY-RUN" in captured.err


def test_no_asc_dry_run_banner_for_a_build(capsys):
    """Le bandeau credentials n'a rien à faire là — il induirait en erreur."""
    main(["build", "dev"])
    assert "App Store Connect credentials" not in capsys.readouterr().err


def test_all_builds_every_declared_target(capsys):
    rc = main(["build", "--all", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert [r["target"] for r in payload["results"]] == ["dev", "vision"]


def test_several_named_targets_keep_their_order(capsys):
    main(["build", "vision", "dev", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert [r["target"] for r in payload["results"]] == ["vision", "dev"]


def test_unknown_target_is_a_typed_envelope(capsys):
    rc = main(["build", "nope", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["ok"] is False
    assert payload["error"]["code"] == "target_not_found"
    assert payload["error"]["context"]["available"] == ["dev", "vision"]


def test_no_target_and_no_all_is_ambiguous(capsys):
    rc = main(["build", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"]["code"] == "ambiguous_target"


def test_all_with_a_named_target_is_refused(capsys):
    rc = main(["build", "--all", "dev", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"]["code"] == "bad_usage"


def test_value_flag_without_a_value(capsys):
    rc = main(["build", "dev", "--scheme", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"]["code"] == "bad_usage"


def test_unknown_flag_lists_the_known_ones(capsys):
    rc = main(["build", "dev", "--nope", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"]["code"] == "bad_usage"
    assert "--scheme" in payload["error"]["remediation"]


def test_targets_lists_effective_fields(capsys):
    rc = main(["targets", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    dev = [t for t in payload["targets"] if t["name"] == "dev"][0]
    assert dev["scheme"] == "Meeshy"                    # hérité de defaults
    assert dev["destination_argument"] == "platform=iOS Simulator,name=iPhone 15"
    vision = [t for t in payload["targets"] if t["name"] == "vision"][0]
    assert vision["destination_argument"] == \
        "platform=visionOS Simulator,name=Apple Vision Pro"


def test_json_stays_parsable_on_a_broken_config(isolated, capsys):
    (isolated / "andp.yml").write_text("targets:\n  a:\n    platfrom: iOS\n")
    rc = main(["build", "a", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"]["code"] == "bad_target_config"
    assert payload["error"]["context"]["unknown"] == "platfrom"


def test_human_mode_keeps_stdout_free_of_errors(capsys):
    rc = main(["build", "nope"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "nope" in captured.err


def test_test_command_shares_the_envelope(capsys):
    rc = main(["test", "--all", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["command"] == "test"
    assert len(payload["results"]) == 2


def test_overrides_reach_the_resolved_target(capsys):
    main(["targets", "--json"])
    before = json.loads(capsys.readouterr().out)
    assert before["targets"][0]["configuration"] == "Debug"
    main(["build", "dev", "--configuration", "Release", "--json"])
    # La surcharge n'est observable que par la destination/config du résultat;
    # en DRY-RUN, on vérifie au moins que la commande l'accepte sans broncher.
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True


def test_existing_asc_commands_still_require_credentials(capsys):
    """CREDENTIAL_FREE ne doit pas avoir élargi l'exemption par accident."""
    rc = main(["verify", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"]["code"] == "config_not_found"
