"""`andp config` — expose la résolution au shell et diagnostique sans credentials."""
import json
import os
import stat

import pytest

from andp.asc.asc_manager import main
from conftest import real_secrets_yaml, write_secrets


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ANDP_CONFIG_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_path_secrets_prints_only_the_path(isolated, capsys, ec_private_key_pem):
    write_secrets(isolated, real_secrets_yaml(ec_private_key_pem))
    rc = main(["config", "path", "secrets"])
    captured = capsys.readouterr()
    assert rc == 0
    # Relatif au cwd — utilisable tel quel en substitution shell, et lisible.
    assert captured.out.strip() == os.path.join(".", ".andp", "secrets.yml")
    assert os.path.exists(captured.out.strip())


def test_path_secrets_exits_1_when_unresolved(isolated, capsys):
    rc = main(["config", "path", "secrets"])
    assert rc == 1
    assert capsys.readouterr().out.strip() == ""


def test_path_policy_has_no_cascade(isolated, capsys):
    rc = main(["config", "path", "policy"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == os.path.join(".", "andp.yml")


def test_path_rejects_an_unknown_target(isolated, capsys):
    assert main(["config", "path", "nope"]) == 2


def test_dir_prints_the_runtime_directory(isolated, capsys):
    rc = main(["config", "dir"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == os.path.join(".", ".andp")


def test_dir_honours_the_env_var(isolated, monkeypatch, capsys):
    monkeypatch.setenv("ANDP_CONFIG_DIR", "/custom/place")
    main(["config", "dir"])
    assert capsys.readouterr().out.strip() == "/custom/place"


def test_config_runs_without_any_credentials(isolated, capsys):
    """Comme build-number: diagnostiquer une config absente ne peut pas exiger
    une config présente."""
    rc = main(["config"])
    assert rc == 0
    assert "secrets" in capsys.readouterr().out


def test_json_diagnostic_reports_origin(isolated, capsys, ec_private_key_pem):
    write_secrets(isolated, real_secrets_yaml(ec_private_key_pem))
    main(["config", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["secrets"]["origin"] == "project"
    assert payload["secrets"]["configured"] is True


def test_migrate_moves_the_file_with_safe_modes(isolated, capsys, ec_private_key_pem):
    legacy = isolated / "secrets.yml"
    legacy.write_text(real_secrets_yaml(ec_private_key_pem))
    rc = main(["config", "migrate"])
    target = isolated / ".andp" / "secrets.yml"

    assert rc == 0
    assert not legacy.exists()
    assert target.exists()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE((isolated / ".andp").stat().st_mode) == 0o700


def test_migrate_refuses_to_overwrite(isolated, capsys, ec_private_key_pem):
    (isolated / "secrets.yml").write_text("legacy\n")
    write_secrets(isolated, real_secrets_yaml(ec_private_key_pem))
    rc = main(["config", "migrate"])
    assert rc == 1
    assert (isolated / "secrets.yml").exists()      # rien n'a été détruit


def test_migrate_is_idempotent(isolated, capsys):
    assert main(["config", "migrate"]) == 0
    assert main(["config", "migrate"]) == 0
