"""Tests for infrastructure/asc/asc_manager.py — CLI d'orchestration.

Sans credentials réels (secrets.example.yml), la CLI doit basculer en dry-run :
aucun appel réseau, sortie explicite, code retour 0 — c'est ce qui garde la CI verte.
"""
import os

import pytest

import asc_manager

PLACEHOLDER_SECRETS = """
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


@pytest.fixture
def ci_like_dir(tmp_path, monkeypatch):
    """Répertoire de travail façon CI : secrets d'exemple + fichiers de version."""
    (tmp_path / "secrets.example.yml").write_text(PLACEHOLDER_SECRETS)
    (tmp_path / "VERSION").write_text("1.2.0\n")
    (tmp_path / "BUILD_NUMBER").write_text("42\n")
    (tmp_path / "Meeshy.ipa").write_bytes(b"fake-ipa")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_upload_dry_run_exits_zero_without_network(ci_like_dir, capsys):
    exit_code = asc_manager.main(["upload", "Meeshy.ipa", "--account", "primary"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "DRY-RUN" in output
    assert "Meeshy.ipa" in output


def test_upload_dry_run_reads_version_files(ci_like_dir, capsys):
    asc_manager.main(["upload", "Meeshy.ipa"])

    output = capsys.readouterr().out
    assert "1.2.0" in output
    assert "42" in output


def test_upload_missing_ipa_exits_one(ci_like_dir, capsys):
    exit_code = asc_manager.main(["upload", "missing.ipa"])
    assert exit_code == 1


def test_unknown_command_exits_two(ci_like_dir, capsys):
    exit_code = asc_manager.main(["frobnicate"])
    assert exit_code == 2
    assert "Usage" in capsys.readouterr().out


def test_no_command_exits_two(ci_like_dir):
    assert asc_manager.main([]) == 2


def test_testflight_dry_run(ci_like_dir, capsys):
    exit_code = asc_manager.main(
        ["testflight", "me.meeshy.app", "Beta Externe", "add", "jc@sylorion.com"]
    )
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "DRY-RUN" in output
    assert "Beta Externe" in output
    assert "jc@sylorion.com" in output


def test_status_dry_run(ci_like_dir, capsys):
    exit_code = asc_manager.main(["status", "me.meeshy.app", "42"])
    assert exit_code == 0
    assert "DRY-RUN" in capsys.readouterr().out


def test_make_managers_wires_real_stack(ec_private_key_pem):
    """Avec des credentials réels, la CLI assemble la pile complète auth→client→managers."""
    from config import AccountConfig

    account = AccountConfig(
        account_id="primary",
        key_id="REALKEY001",
        issuer_id="11111111-2222-3333-4444-555555555555",
        key_content=ec_private_key_pem,
    )
    managers = asc_manager.make_managers(account)

    assert managers.apps is not None
    assert managers.builds is not None
    assert managers.testflight is not None
    assert managers.appstore is not None
    # le token JWT est réellement généré (signé ES256)
    assert managers.client.auth.token().count(".") == 2
