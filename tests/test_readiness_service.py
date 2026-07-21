"""service.readiness_testflight / readiness_appstore — the library glue that
runs verify/precheck and returns a normalized verdict (over a FakeSession)."""
from andp import service
from conftest import FakeResponse, FakeSession, make_test_managers, real_secrets_yaml


def _real(tmp_path, monkeypatch, ec_private_key_pem):
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    return session


def test_readiness_testflight_ready(tmp_path, monkeypatch, ec_private_key_pem):
    session = _real(tmp_path, monkeypatch, ec_private_key_pem)
    session.queue(FakeResponse(200, {"data": [
        {"id": "app-1", "attributes": {"name": "Demo", "bundleId": "me.app"}}]}))
    v = service.readiness_testflight("me.app")
    assert v["target"] == "testflight"
    assert v["status"] == "ready" and v["ready"] is True
    assert v["bundle_id"] == "me.app"
    assert v["app"]["name"] == "Demo"


def test_readiness_testflight_app_not_found_is_not_ready(tmp_path, monkeypatch, ec_private_key_pem):
    session = _real(tmp_path, monkeypatch, ec_private_key_pem)
    session.queue(FakeResponse(200, {"data": []}))
    v = service.readiness_testflight("me.app")
    assert v["status"] == "not_ready"
    assert v["credentials_ready"] is True
    assert v["blockers"][0]["id"] == "app_record"


def test_readiness_testflight_dry_run_is_unverified(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "secrets.yml").write_text(
        "accounts:\n  primary:\n    asc_api:\n"
        "      key_id: \"ABCDE12345\"\n      issuer_id: \"\"\n      key_content: \"\"\n")
    v = service.readiness_testflight("me.app")
    assert v["status"] == "unverified"
    assert v["credentials_ready"] is False


def test_readiness_appstore_ready(tmp_path, monkeypatch, ec_private_key_pem):
    session = _real(tmp_path, monkeypatch, ec_private_key_pem)
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),
        FakeResponse(200, {"data": [{"id": "ver-1"}]}),
        FakeResponse(200, {"data": {"id": "ver-1", "attributes": {
            "appVersionState": "PREPARE_FOR_SUBMISSION"}}}),
        FakeResponse(200, {"data": {"id": "build-77"}}),
        FakeResponse(200, {"data": [{"id": "loc-en", "attributes": {
            "locale": "en-US", "description": "Great.", "keywords": "k", "supportUrl": "https://x"}}]}),
        FakeResponse(200, {"data": [{"id": "set-1"}]}),
        FakeResponse(200, {"data": [{"id": "s1"}]}),
    )
    v = service.readiness_appstore("me.app", "1.0")
    assert v["target"] == "appstore"
    assert v["status"] == "ready" and v["version"] == "1.0"


def test_readiness_appstore_version_not_found_is_not_ready(tmp_path, monkeypatch, ec_private_key_pem):
    session = _real(tmp_path, monkeypatch, ec_private_key_pem)
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),
        FakeResponse(200, {"data": []}),  # no version
    )
    v = service.readiness_appstore("me.app", "9.9")
    assert v["status"] == "not_ready"
    assert v["blockers"][0]["id"] == "version_not_found"


def test_readiness_appstore_dry_run_is_unverified(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "secrets.yml").write_text(
        "accounts:\n  primary:\n    asc_api:\n"
        "      key_id: \"ABCDE12345\"\n      issuer_id: \"\"\n      key_content: \"\"\n")
    v = service.readiness_appstore("me.app", "1.0")
    assert v["status"] == "unverified"
    assert v["credentials_ready"] is False
