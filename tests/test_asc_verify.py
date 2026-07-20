"""Tests for the 'verify' preflight command of asc_manager.py.

'verify' proves the tool can really publish to App Store Connect: unlike the
other commands it must FAIL (exit 1) when credentials are placeholders, and
with real credentials it must hit the API and report auth + app lookup status.
"""
import pytest

from andp.asc import asc_manager
from conftest import FakeResponse, FakeSession

PARTIAL_SECRETS = """
accounts:
  primary:
    asc_api:
      key_id: "TESTKEY001"
      issuer_id: "REPLACE_WITH_ISSUER_ID"
      key_content: |
        -----BEGIN PRIVATE KEY-----
        PRIMARY_KEY_CONTENT
        -----END PRIVATE KEY-----
"""


@pytest.fixture
def partial_secrets_dir(tmp_path, monkeypatch):
    """secrets.yml exists but issuer_id and key are still template placeholders."""
    (tmp_path / "secrets.yml").write_text(PARTIAL_SECRETS)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_verify_unconfigured_fails_and_names_missing_fields(partial_secrets_dir, capsys):
    exit_code = asc_manager.main(["verify"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "PREFLIGHT FAILED" in output
    assert "issuer_id" in output
    assert "key_content" in output
    # key_id is real (not a placeholder) and must not be flagged as missing
    assert "missing: key_id" not in output


def test_verify_authenticates_against_api_without_bundle_id(
    configured_dir, fake_transport, capsys
):
    fake_transport.queue(FakeResponse(200, {"data": [{"id": "app-1", "type": "apps"}]}))

    exit_code = asc_manager.main(["verify"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "PREFLIGHT PASSED" in output
    assert len(fake_transport.requests) == 1
    request = fake_transport.requests[0]
    assert "/v1/apps" in request["url"]
    assert request["headers"]["Authorization"].startswith("Bearer ")


def test_verify_finds_app_by_bundle_id(configured_dir, fake_transport, capsys):
    fake_transport.queue(
        FakeResponse(
            200,
            {
                "data": [
                    {
                        "id": "app-42",
                        "type": "apps",
                        "attributes": {"name": "Dekonect", "bundleId": "app.deconnect.mvp"},
                    }
                ]
            },
        )
    )

    exit_code = asc_manager.main(["verify", "app.deconnect.mvp"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "PREFLIGHT PASSED" in output
    assert "Dekonect" in output
    assert "app.deconnect.mvp" in fake_transport.requests[0].get("params", {}).get(
        "filter[bundleId]", ""
    )


def test_verify_app_not_found_fails(configured_dir, fake_transport, capsys):
    fake_transport.queue(FakeResponse(200, {"data": []}))

    exit_code = asc_manager.main(["verify", "app.deconnect.mvp"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "PREFLIGHT FAILED" in output
    assert "app.deconnect.mvp" in output


def test_verify_rejected_credentials_fail(configured_dir, fake_transport, capsys):
    fake_transport.queue(
        FakeResponse(
            401,
            {"errors": [{"status": "401", "title": "NOT_AUTHORIZED", "detail": "bad key"}]},
        )
    )

    exit_code = asc_manager.main(["verify"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "PREFLIGHT FAILED" in output
    assert "401" in output


def test_verify_unusable_private_key_fails(tmp_path, monkeypatch, capsys):
    (tmp_path / "secrets.yml").write_text(
        """
accounts:
  primary:
    asc_api:
      key_id: "REALKEY001"
      issuer_id: "11111111-2222-3333-4444-555555555555"
      key_content: |
        -----BEGIN PRIVATE KEY-----
        not-a-real-key
        -----END PRIVATE KEY-----
"""
    )
    monkeypatch.chdir(tmp_path)

    exit_code = asc_manager.main(["verify"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "PREFLIGHT FAILED" in output
    assert "JWT" in output
