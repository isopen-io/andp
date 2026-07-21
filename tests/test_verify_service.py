"""service.verify_checks (pure core) + service.verify (loader).

The verify preflight logic is extracted from the CLI into a library function so
the readiness gates (and, later, MCP) can drive it without scraping stdout. The
existing CLI verify tests (test_asc_verify.py) are the regression guard that the
human output is unchanged; these tests pin the library envelope.
"""
from andp import service
from andp.asc.client import ASCAPIError
from andp.asc.config import AccountConfig
from conftest import FakeResponse, FakeSession, make_test_managers, real_secrets_yaml


def _configured():
    return AccountConfig("primary", "TESTKEY001",
                         "11111111-2222-3333-4444-555555555555",
                         "-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----")


def test_verify_checks_dry_run_names_missing_fields():
    account = AccountConfig("primary", "TESTKEY001", None, None)  # issuer+key missing
    result = service.verify_checks(account, None, None)
    assert result["command"] == "verify"
    assert result["ok"] is False
    cred = result["checks"][0]
    assert cred["name"] == "credentials" and cred["ok"] is False
    assert set(cred["missing"]) == {"issuer_id", "key_content"}
    assert "app" not in result


def test_verify_checks_no_bundle_authenticates_against_apps():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [{"id": "app-1"}]}))
    managers = make_test_managers(session)

    result = service.verify_checks(_configured(), managers, None)

    assert result["ok"] is True
    names = [c["name"] for c in result["checks"]]
    assert names == ["credentials", "jwt", "api_auth"]
    assert "/v1/apps" in session.requests[0]["url"]


def test_verify_checks_finds_app_by_bundle_id():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [
        {"id": "app-42", "attributes": {"name": "Dekonect", "bundleId": "app.d.mvp"}}]}))
    managers = make_test_managers(session)

    result = service.verify_checks(_configured(), managers, "app.d.mvp")

    assert result["ok"] is True
    assert result["app"] == {"id": "app-42", "name": "Dekonect", "bundle_id": "app.d.mvp"}
    assert [c["name"] for c in result["checks"]] == \
        ["credentials", "jwt", "api_auth", "app_record"]


def test_verify_checks_app_not_found_blocks():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": []}))
    managers = make_test_managers(session)

    result = service.verify_checks(_configured(), managers, "app.d.mvp")

    assert result["ok"] is False
    last = result["checks"][-1]
    assert last["name"] == "app_record" and last["ok"] is False
    assert "app.d.mvp" in last["detail"]
    assert "app" not in result


def test_verify_checks_api_rejection_is_not_retryable():
    session = FakeSession()
    session.queue(FakeResponse(401, {"errors": [{"detail": "bad key"}]}))
    managers = make_test_managers(session)

    result = service.verify_checks(_configured(), managers, "app.d.mvp")

    assert result["ok"] is False
    auth = result["checks"][-1]
    assert auth["name"] == "api_auth" and auth["ok"] is False
    assert auth.get("retryable") is False
    assert "401" in auth["detail"]


def test_verify_checks_rate_limited_is_retryable():
    session = FakeSession()
    managers = make_test_managers(session)

    def _boom(_bundle):
        raise ASCAPIError(429, [{"detail": "slow down"}])
    managers.apps.find_app = _boom

    result = service.verify_checks(_configured(), managers, "app.d.mvp")

    assert result["ok"] is False
    auth = result["checks"][-1]
    assert auth["name"] == "api_auth" and auth["ok"] is False
    assert auth["retryable"] is True


def test_verify_checks_network_error_is_retryable_not_raised():
    """A transient network failure must NOT escape verify_checks; it becomes a
    retryable api_auth blocker (so readiness classifies it 'unverified')."""
    session = FakeSession()
    managers = make_test_managers(session)

    def _network(_bundle):
        raise ConnectionError("dns temporarily unavailable")
    managers.apps.find_app = _network

    result = service.verify_checks(_configured(), managers, "app.d.mvp")

    assert result["ok"] is False
    auth = result["checks"][-1]
    assert auth["name"] == "api_auth" and auth["ok"] is False
    assert auth["retryable"] is True


def test_verify_checks_jwt_failure_blocks():
    session = FakeSession()
    managers = make_test_managers(session)

    from andp.asc.auth import ASCAuthError

    class _BadAuth:
        def token(self):
            raise ASCAuthError("unusable key")
    managers.client.auth = _BadAuth()

    result = service.verify_checks(_configured(), managers, None)

    assert result["ok"] is False
    jwt = result["checks"][-1]
    assert jwt["name"] == "jwt" and jwt["ok"] is False


def test_service_verify_loader_dry_run(tmp_path, monkeypatch):
    """service.verify loads creds itself; placeholders => failed credentials."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "secrets.yml").write_text(
        "accounts:\n  primary:\n    asc_api:\n"
        "      key_id: \"ABCDE12345\"\n      issuer_id: \"\"\n      key_content: \"\"\n")
    result = service.verify("app.d.mvp")
    assert result["command"] == "verify"
    assert result["ok"] is False
    assert result["checks"][0]["name"] == "credentials"


def test_service_verify_loader_hits_api(tmp_path, monkeypatch, ec_private_key_pem):
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [{"id": "app-1"}]}))
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))

    result = service.verify()
    assert result["ok"] is True
