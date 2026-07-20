"""Tests for infrastructure/asc/config.py — chargement des secrets multi-comptes."""
import pytest

from config import AccountConfig, ConfigError, load_account


SECRETS_REAL = """
accounts:
  primary:
    asc_api:
      key_id: "REALKEY001"
      issuer_id: "11111111-2222-3333-4444-555555555555"
      key_content: |
        -----BEGIN PRIVATE KEY-----
        MIGTAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBHkwdwIBAQQg
        -----END PRIVATE KEY-----
    signing:
      development_team: "TEAM123456"
"""

SECRETS_PLACEHOLDER = """
accounts:
  primary:
    asc_api:
      key_id: "ABCDE12345"
      issuer_id: "69a6dead-beef-4de4-8344-0123456789ab"
      key_content: |
        -----BEGIN PRIVATE KEY-----
        PRIMARY_KEY_CONTENT
        -----END PRIVATE KEY-----
"""


def _write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content)
    return str(path)


def test_load_account_reads_asc_api_fields(tmp_path):
    secrets = _write(tmp_path, "secrets.yml", SECRETS_REAL)
    account = load_account("primary", secrets_file=secrets)

    assert isinstance(account, AccountConfig)
    assert account.key_id == "REALKEY001"
    assert account.issuer_id == "11111111-2222-3333-4444-555555555555"
    assert "BEGIN PRIVATE KEY" in account.key_content
    assert account.team_id == "TEAM123456"


def test_unknown_account_raises(tmp_path):
    secrets = _write(tmp_path, "secrets.yml", SECRETS_REAL)
    with pytest.raises(ConfigError, match="unknown-account"):
        load_account("unknown-account", secrets_file=secrets)


def test_missing_file_falls_back_to_example(tmp_path, monkeypatch):
    """Sans secrets.yml, on retombe sur secrets.example.yml (mode CI)."""
    _write(tmp_path, "secrets.example.yml", SECRETS_PLACEHOLDER)
    monkeypatch.chdir(tmp_path)
    account = load_account("primary")
    assert account.key_id == "ABCDE12345"


def test_no_secrets_at_all_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        load_account("primary")


def test_placeholder_account_is_not_configured(tmp_path):
    secrets = _write(tmp_path, "secrets.yml", SECRETS_PLACEHOLDER)
    account = load_account("primary", secrets_file=secrets)
    assert account.is_configured() is False


def test_real_account_is_configured(tmp_path):
    secrets = _write(tmp_path, "secrets.yml", SECRETS_REAL)
    account = load_account("primary", secrets_file=secrets)
    assert account.is_configured() is True


def test_placeholder_issuer_with_real_key_is_not_configured(tmp_path):
    """A real .p8 key with a REPLACE_WITH_* issuer must stay in DRY-RUN."""
    secrets = _write(
        tmp_path,
        "secrets.yml",
        SECRETS_REAL.replace(
            'issuer_id: "11111111-2222-3333-4444-555555555555"',
            'issuer_id: "REPLACE_WITH_ISSUER_ID"',
        ),
    )
    account = load_account("primary", secrets_file=secrets)
    assert account.is_configured() is False
