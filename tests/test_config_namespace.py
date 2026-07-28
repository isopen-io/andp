"""Résolution .andp/ — et surtout: plus jamais de bascule DRY-RUN silencieuse."""
import pytest

from andp.asc.config import load_account
from andp.errors import ConfigError
from conftest import real_secrets_yaml, write_secrets

PLACEHOLDERS = """
accounts:
  primary:
    asc_api:
      key_id: "ABCDE12345"
      issuer_id: "REPLACE_WITH_ISSUER_ID"
      key_content: "PRIMARY_KEY_CONTENT"
"""


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ANDP_CONFIG_DIR", raising=False)
    return home


def test_reads_from_the_project_namespace(tmp_path, monkeypatch, ec_private_key_pem):
    write_secrets(tmp_path, real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    account = load_account("primary")
    assert account.is_configured() is True
    assert account.origin == "project"


def test_reads_from_the_global_namespace(tmp_path, monkeypatch, isolated_home,
                                         ec_private_key_pem):
    write_secrets(isolated_home, real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    account = load_account("primary")
    assert account.is_configured() is True
    assert account.origin == "global"


def test_root_secrets_never_silently_falls_back_to_template(tmp_path, monkeypatch,
                                                            ec_private_key_pem):
    """Le bug d'origine: 15 min de build, puis un upload en DRY-RUN silencieux."""
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    (tmp_path / "secrets.example.yml").write_text(PLACEHOLDERS)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigError) as excinfo:
        load_account("primary")
    assert excinfo.value.code == "config_misplaced"
    assert excinfo.value.remediation


def test_misplaced_is_raised_even_when_another_level_resolves(tmp_path, monkeypatch,
                                                              ec_private_key_pem):
    """Deux fichiers concurrents: on signale plutôt que de trancher en silence."""
    write_secrets(tmp_path, real_secrets_yaml(ec_private_key_pem))
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigError) as excinfo:
        load_account("primary")
    assert excinfo.value.code == "config_misplaced"


def test_nothing_anywhere_raises_config_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError) as excinfo:
        load_account("primary")
    assert excinfo.value.code == "config_not_found"


def test_error_context_lists_the_searched_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError) as excinfo:
        load_account("primary")
    context = excinfo.value.to_dict()["context"]
    assert context["resolved"] is None
    assert any(p.endswith(".andp/secrets.yml") for p in context["searched"])


def test_template_still_yields_a_dry_run_account(tmp_path, monkeypatch):
    """Les PR de fork restent vertes: le template garde son rôle."""
    (tmp_path / "secrets.example.yml").write_text(PLACEHOLDERS)
    monkeypatch.chdir(tmp_path)
    account = load_account("primary")
    assert account.is_configured() is False
    assert account.origin == "template"


def test_explicit_secrets_file_bypasses_the_cascade(tmp_path, ec_private_key_pem):
    path = tmp_path / "anywhere.yml"
    path.write_text(real_secrets_yaml(ec_private_key_pem))
    account = load_account("primary", secrets_file=str(path))
    assert account.is_configured() is True
