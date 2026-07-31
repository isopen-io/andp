"""En --json, stdout est TOUJOURS du JSON — sur toutes les commandes.

Six handlers imprimaient de la prose sur stdout en mode --json : erreurs
d'usage, IPA manquante, comptes rendus DRY-RUN. Un agent n'y trouvait ni code,
ni retryable, ni remediation, et ne pouvait même pas distinguer une action
planifiée d'une action effectuée.

Ce fichier fige l'invariant pour l'ensemble de la surface CLI.
"""
import json

import pytest

from andp.asc.asc_manager import COMMANDS, main

# Credentials incomplets → DRY-RUN, le mode où les handlers parlent le plus.
PARTIAL_CREDENTIALS = """
accounts:
  primary:
    asc_api:
      key_id: "AAA"
"""

INVOCATIONS = [
    ["verify"],
    ["verify", "me.app"],
    ["upload"],
    ["upload", "app.ipa"],
    ["release"],
    ["release", "app.ipa"],
    ["status"],
    ["status", "me.app", "42"],
    ["submit"],
    ["submit", "me.app", "1.0"],
    ["unlock"],
    ["unlock", "me.app", "1.0"],
    ["version"],
    ["version", "list", "me.app"],
    ["version", "set", "me.app", "1.0.0", "--platform", "MAC_OS"],
    ["publish", "app.ipa"],
    ["precheck", "me.app", "1.0"],
    ["readiness", "testflight", "me.app"],
    ["readiness", "appstore", "me.app", "1.0"],
    ["store", "apply", "me.app"],
    ["store", "pricing", "me.app"],
    ["testflight", "me.app", "grp", "add", "a@b.c"],
    ["testflight", "me.app", "grp", "remove"],
    ["build-number", "--strategy", "timestamp"],
    ["config"],
    ["targets"],
    ["build", "--all"],
    ["test", "--all"],
    ["run", "solo"],
]


@pytest.fixture(autouse=True)
def dry_run_project(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ANDP_CONFIG_DIR", raising=False)
    monkeypatch.delenv("ANDP_APP_DIR", raising=False)
    monkeypatch.setenv("PATH", "")            # pas de xcodebuild → DRY-RUN outillage
    monkeypatch.chdir(tmp_path)
    andp_dir = tmp_path / ".andp"
    andp_dir.mkdir()
    (andp_dir / "secrets.yml").write_text(PARTIAL_CREDENTIALS)
    (tmp_path / "andp.yml").write_text("targets:\n  solo:\n    scheme: Solo\n")


@pytest.mark.parametrize("argv", INVOCATIONS,
                         ids=[" ".join(a) for a in INVOCATIONS])
def test_stdout_is_always_parsable_json(argv, capsys):
    main(argv + ["--json"])
    payload = json.loads(capsys.readouterr().out)      # ne doit pas lever
    assert isinstance(payload, dict)
    assert payload.get("command")
    # `readiness` porte son verdict dans `ready` (contrat historique, codes de
    # sortie 0/1/3 documentés) ; partout ailleurs c'est `ok`.
    assert "ok" in payload or "ready" in payload


@pytest.mark.parametrize("argv", INVOCATIONS,
                         ids=[" ".join(a) for a in INVOCATIONS])
def test_a_failure_always_carries_a_typed_error(argv, capsys):
    """`ok: false` sans erreur exploitable laisse un agent sans quoi décider."""
    main(argv + ["--json"])
    payload = json.loads(capsys.readouterr().out)
    if payload.get("ok") is False and "error" in payload:
        error = payload["error"]
        assert error["code"]
        assert isinstance(error["retryable"], bool)


def test_every_command_is_covered():
    """Une commande ajoutée sans entrée ici échapperait à l'invariant."""
    exercised = set(argv[0] for argv in INVOCATIONS)
    assert exercised == set(COMMANDS), (
        "commandes non couvertes : %s" % (set(COMMANDS) - exercised))


def test_dry_run_reports_are_flagged_not_prose(capsys):
    """Une action planifiée doit être distinguable d'une action effectuée."""
    main(["submit", "me.app", "1.0", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["bundle_id"] == "me.app"
    assert payload["version"] == "1.0"


# Les commandes outillage sont les seules à lire le bloc `targets:` d'andp.yml.
XCODE_INVOCATIONS = [["targets"], ["build", "--all"], ["test", "--all"],
                     ["run", "solo"]]


@pytest.mark.parametrize("argv", XCODE_INVOCATIONS,
                         ids=[" ".join(a) for a in XCODE_INVOCATIONS])
@pytest.mark.parametrize("body", ["targets:\n  dev:\n   - [\n", "- a\n- b\n"],
                         ids=["yaml-malforme", "yaml-non-mapping"])
def test_a_broken_andp_yml_still_answers_in_json(argv, body, tmp_path, capsys):
    """Un andp.yml illisible remontait une trace Python et rien sur stdout.

    L'agent perdait l'enveloppe au moment précis où il en avait besoin : celui
    où sa configuration est cassée et où le message doit lui dire quoi réparer.
    """
    (tmp_path / "andp.yml").write_text(body)
    assert main(argv + ["--json"]) == 1
    payload = json.loads(capsys.readouterr().out)      # ne doit pas lever
    assert payload["ok"] is False
    assert payload["error"]["code"] == "bad_config"
    assert payload["error"]["remediation"]


def test_usage_errors_keep_their_exit_code(capsys):
    """L'enveloppe ne doit pas écraser le 2 qui distingue l'usage de l'échec."""
    assert main(["upload", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "bad_usage"
    assert main(["upload", "absent.ipa", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "ipa_missing"
