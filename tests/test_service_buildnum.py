"""service.build_number — dispatch over the three strategies + error envelopes."""
from datetime import datetime, timezone

from andp import service
from conftest import FakeResponse, FakeSession, make_test_managers, real_secrets_yaml


def _clock():
    return datetime(2026, 7, 22, 18, 30, tzinfo=timezone.utc)


def test_timestamp_needs_no_creds():
    r = service.build_number("timestamp", clock=_clock)
    assert r["ok"] is True
    assert r["strategy"] == "timestamp"
    assert r["build_number"] == "202607221830"
    assert r["monotonic"] is True


def test_commit_from_arg():
    r = service.build_number("commit", sha="deadbeefcafe", digits=7)
    assert r["ok"] is True
    assert r["build_number"] == str(int("deadbee", 16))
    assert r["monotonic"] is False


def test_commit_from_env_sha(monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", "abcdef1234")
    r = service.build_number("commit")
    assert r["build_number"] == str(int("abcdef1", 16))


def test_commit_no_sha_is_error(monkeypatch):
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    r = service.build_number("commit")
    assert r["ok"] is False
    assert r["error"]["code"] == "bad_input"


def test_fastlane_floor_wins(tmp_path, monkeypatch, ec_private_key_pem):
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),
        FakeResponse(200, {"data": [{"attributes": {"version": "1200"}}], "links": {}}),
    )
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    r = service.build_number("fastlane", bundle_id="me.app", floor=1254)
    assert r["ok"] is True
    assert r["build_number"] == "1255"        # max(1254, 1200) + 1
    assert r["monotonic"] is True


def test_fastlane_asc_wins(tmp_path, monkeypatch, ec_private_key_pem):
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),
        FakeResponse(200, {"data": [{"attributes": {"version": "1300"}}], "links": {}}),
    )
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    r = service.build_number("fastlane", bundle_id="me.app", floor=0)
    assert r["build_number"] == "1301"        # max(0, 1300) + 1


def test_fastlane_dry_run_is_no_credentials(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "secrets.yml").write_text(
        "accounts:\n  primary:\n    asc_api:\n"
        "      key_id: \"ABCDE12345\"\n      issuer_id: \"\"\n      key_content: \"\"\n")
    r = service.build_number("fastlane", bundle_id="me.app")
    assert r["ok"] is False
    assert r["error"]["code"] == "no_credentials"


def test_fastlane_app_not_found(tmp_path, monkeypatch, ec_private_key_pem):
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": []}))
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    r = service.build_number("fastlane", bundle_id="me.app")
    assert r["ok"] is False
    assert r["error"]["code"] == "app_not_found"


def test_fastlane_non_int_floor_is_envelope_not_crash():
    r = service.build_number("fastlane", bundle_id="me.app", floor="oops")
    assert r["ok"] is False
    assert r["error"]["code"] == "bad_input"


def test_commit_string_digits_coerced():
    r = service.build_number("commit", sha="deadbeef", digits="5")
    assert r["ok"] is True
    assert r["build_number"] == str(int("deadb", 16))


def test_commit_bad_digits_is_envelope_not_crash():
    r = service.build_number("commit", sha="deadbeef", digits="junk")
    assert r["ok"] is False
    assert r["error"]["code"] == "bad_input"


def test_fastlane_warns_when_dotted_versions_skipped(tmp_path, monkeypatch, ec_private_key_pem):
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),
        FakeResponse(200, {"data": [{"attributes": {"version": "1.0.3"}}], "links": {}}),
    )
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    r = service.build_number("fastlane", bundle_id="me.app")
    assert r["ok"] is True
    assert r["build_number"] == "1"           # all dotted skipped -> latest 0
    assert "warning" in r                     # ...but the risk is surfaced


def test_unknown_strategy_is_error():
    r = service.build_number("sideways")
    assert r["ok"] is False
