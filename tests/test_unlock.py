"""`andp unlock` — withdraw the pending review submission so the version
becomes editable again, then resubmit with `andp submit`.

The command also answers "when was this submitted?": the submission's
`submittedDate` is printed with a precise UTC date, and turns into an alert
line once the submission is more than an hour old — cancelling then forfeits
a queue position that was probably worth keeping.
"""
import json

import pytest

from andp import service
from andp.asc import asc_manager
from conftest import FakeResponse, FakeSession, make_test_managers, real_secrets_yaml, write_secrets

APP = {"data": [{"id": "app-9"}]}


def _version(state, vid="ver-1"):
    return {"data": [{"id": vid, "attributes": {
        "versionString": "1.0", "appVersionState": state}}]}


def _submission(submitted_at="2026-07-31T08:00:00+00:00"):
    attributes = {"state": "WAITING_FOR_REVIEW"}
    if submitted_at is not None:
        attributes["submittedDate"] = submitted_at
    return {"data": [{"id": "sub-1", "attributes": attributes}]}


def _wire(tmp_path, monkeypatch, ec_private_key_pem, *responses):
    write_secrets(tmp_path, real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    session.queue(*responses)
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    return session


# 2026-07-31T10:00:00+00:00 — two hours after the canned submittedDate above.
NOW = 1785492000.0


def test_service_unlock_cancels_and_waits_until_editable(
        tmp_path, monkeypatch, ec_private_key_pem):
    _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),                                    # find_app
        FakeResponse(200, _version("WAITING_FOR_REVIEW")),         # find_version
        FakeResponse(200, _submission()),                          # find_in_review_submission
        FakeResponse(200, {"data": {"id": "sub-1", "attributes": {"state": "CANCELING"}}}),
        FakeResponse(200, _version("WAITING_FOR_REVIEW")),         # poll 1: still locked
        FakeResponse(200, _version("DEVELOPER_REJECTED")),         # poll 2: editable
    )
    naps = []
    result = service.unlock("me.demo.app", "1.0",
                            clock=lambda: NOW, sleep=naps.append)

    assert result["ok"] is True
    assert result["command"] == "unlock"
    assert result["submission_id"] == "sub-1"
    assert result["submitted_at"] == "2026-07-31T08:00:00+00:00"
    assert result["age_seconds"] == pytest.approx(7200)
    assert result["stale"] is True                 # > 1 h in the queue
    assert result["already_editable"] is False
    assert result["version_state"] == "DEVELOPER_REJECTED"
    assert naps                                    # it polled, it did not spin


def test_service_unlock_fresh_submission_is_not_stale(
        tmp_path, monkeypatch, ec_private_key_pem):
    _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, _version("WAITING_FOR_REVIEW")),
        FakeResponse(200, _submission("2026-07-31T09:50:00+00:00")),   # 10 min ago
        FakeResponse(200, {"data": {"id": "sub-1", "attributes": {"state": "CANCELING"}}}),
        FakeResponse(200, _version("DEVELOPER_REJECTED")),
    )
    result = service.unlock("me.demo.app", "1.0",
                            clock=lambda: NOW, sleep=lambda s: None)
    assert result["ok"] is True
    assert result["age_seconds"] == pytest.approx(600)
    assert result["stale"] is False


def test_service_unlock_already_editable_is_a_noop(
        tmp_path, monkeypatch, ec_private_key_pem):
    session = _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, _version("PREPARE_FOR_SUBMISSION")),
    )
    result = service.unlock("me.demo.app", "1.0",
                            clock=lambda: NOW, sleep=lambda s: None)
    assert result["ok"] is True
    assert result["already_editable"] is True
    assert result["version_state"] == "PREPARE_FOR_SUBMISSION"
    assert not session.responses                   # no cancel was attempted


def test_service_unlock_without_live_submission_fails(
        tmp_path, monkeypatch, ec_private_key_pem):
    _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, _version("WAITING_FOR_REVIEW")),
        FakeResponse(200, {"data": []}),                           # no live submission
    )
    result = service.unlock("me.demo.app", "1.0",
                            clock=lambda: NOW, sleep=lambda s: None)
    assert result["ok"] is False
    assert result["error"]["code"] == "submission_not_found"
    assert result["error"]["retryable"] is False


def test_service_unlock_version_not_found(tmp_path, monkeypatch, ec_private_key_pem):
    _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, {"data": []}),
    )
    result = service.unlock("me.demo.app", "9.9",
                            clock=lambda: NOW, sleep=lambda s: None)
    assert result["ok"] is False
    assert result["error"]["code"] == "version_not_found"


def test_service_unlock_app_not_found(tmp_path, monkeypatch, ec_private_key_pem):
    _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, {"data": []}),
    )
    result = service.unlock("me.demo.app", "1.0",
                            clock=lambda: NOW, sleep=lambda s: None)
    assert result["ok"] is False
    assert result["error"]["code"] == "app_not_found"


def test_service_unlock_unknown_submitted_date_is_not_stale(
        tmp_path, monkeypatch, ec_private_key_pem):
    """The observed API can omit submittedDate; never claim staleness then."""
    _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, _version("WAITING_FOR_REVIEW")),
        FakeResponse(200, _submission(None)),
        FakeResponse(200, {"data": {"id": "sub-1", "attributes": {"state": "CANCELING"}}}),
        FakeResponse(200, _version("DEVELOPER_REJECTED")),
    )
    result = service.unlock("me.demo.app", "1.0",
                            clock=lambda: NOW, sleep=lambda s: None)
    assert result["ok"] is True
    assert result["submitted_at"] is None
    assert result["age_seconds"] is None
    assert result["stale"] is False


def test_service_unlock_times_out_retryably(tmp_path, monkeypatch, ec_private_key_pem):
    responses = [
        FakeResponse(200, APP),
        FakeResponse(200, _version("WAITING_FOR_REVIEW")),
        FakeResponse(200, _submission()),
        FakeResponse(200, {"data": {"id": "sub-1", "attributes": {"state": "CANCELING"}}}),
    ] + [FakeResponse(200, _version("WAITING_FOR_REVIEW"))] * 50
    _wire(tmp_path, monkeypatch, ec_private_key_pem, *responses)

    ticking = iter(range(0, 10_000, 60))           # each look at the clock = +60 s
    result = service.unlock("me.demo.app", "1.0",
                            clock=lambda: NOW + next(ticking),
                            sleep=lambda s: None, timeout=180)
    assert result["ok"] is False
    assert result["error"]["code"] == "unlock_timeout"
    assert result["error"]["retryable"] is True


def test_service_unlock_dry_run(tmp_path, monkeypatch):
    (tmp_path / "secrets.example.yml").write_text(
        'accounts:\n  primary:\n    asc_api:\n      key_id: "ABCDE12345"\n'
        '      issuer_id: "x"\n      key_content: "REPLACE_WITH"\n')
    monkeypatch.chdir(tmp_path)
    result = service.unlock("me.demo.app", "1.0")
    assert result["ok"] is True
    assert result["dry_run"] is True


# -- CLI rendering --------------------------------------------------------


def test_cli_unlock_bad_usage_exits_two(tmp_path, monkeypatch, capsys):
    (tmp_path / "secrets.example.yml").write_text(
        'accounts:\n  primary:\n    asc_api:\n      key_id: "ABCDE12345"\n'
        '      issuer_id: "x"\n      key_content: "REPLACE_WITH"\n')
    monkeypatch.chdir(tmp_path)
    assert asc_manager.main(["unlock", "me.demo.app"]) == 2


def test_cli_unlock_prints_alert_when_older_than_an_hour(monkeypatch, capsys):
    monkeypatch.setattr(service, "unlock", lambda *a, **k: {
        "command": "unlock", "ok": True, "dry_run": False,
        "bundle_id": "me.demo.app", "version": "1.0",
        "submission_id": "sub-1", "submitted_at": "2026-07-31T08:00:00+00:00",
        "age_seconds": 7754.0, "stale": True,
        "already_editable": False, "version_state": "DEVELOPER_REJECTED"})
    monkeypatch.setattr(asc_manager, "load_account", lambda a: _FakeAccount())
    monkeypatch.setattr(asc_manager, "make_managers", lambda a: None)

    code = asc_manager.main(["unlock", "me.demo.app", "1.0"])
    out = capsys.readouterr().out
    assert code == 0
    assert "⚠️" in out                              # alert log, not a plain line
    assert "2h 09m" in out
    assert "2026-07-31 08:00:00 UTC" in out         # the precise date
    assert "andp submit me.demo.app 1.0" in out     # the resubmit path


def test_cli_unlock_prints_plain_age_when_fresh(monkeypatch, capsys):
    monkeypatch.setattr(service, "unlock", lambda *a, **k: {
        "command": "unlock", "ok": True, "dry_run": False,
        "bundle_id": "me.demo.app", "version": "1.0",
        "submission_id": "sub-1", "submitted_at": "2026-07-31T09:48:00+00:00",
        "age_seconds": 720.0, "stale": False,
        "already_editable": False, "version_state": "DEVELOPER_REJECTED"})
    monkeypatch.setattr(asc_manager, "load_account", lambda a: _FakeAccount())
    monkeypatch.setattr(asc_manager, "make_managers", lambda a: None)

    code = asc_manager.main(["unlock", "me.demo.app", "1.0"])
    out = capsys.readouterr().out
    assert code == 0
    assert "⚠️" not in out
    assert "12m" in out
    assert "2026-07-31 09:48:00 UTC" in out


def test_cli_unlock_already_editable(monkeypatch, capsys):
    monkeypatch.setattr(service, "unlock", lambda *a, **k: {
        "command": "unlock", "ok": True, "dry_run": False,
        "bundle_id": "me.demo.app", "version": "1.0",
        "submission_id": None, "submitted_at": None,
        "age_seconds": None, "stale": False,
        "already_editable": True, "version_state": "PREPARE_FOR_SUBMISSION"})
    monkeypatch.setattr(asc_manager, "load_account", lambda a: _FakeAccount())
    monkeypatch.setattr(asc_manager, "make_managers", lambda a: None)

    code = asc_manager.main(["unlock", "me.demo.app", "1.0"])
    out = capsys.readouterr().out
    assert code == 0
    assert "already editable" in out


def test_cli_unlock_json_envelope_verbatim(monkeypatch, capsys):
    envelope = {
        "command": "unlock", "ok": True, "dry_run": False,
        "bundle_id": "me.demo.app", "version": "1.0",
        "submission_id": "sub-1", "submitted_at": "2026-07-31T08:00:00+00:00",
        "age_seconds": 7200.0, "stale": True,
        "already_editable": False, "version_state": "DEVELOPER_REJECTED"}
    monkeypatch.setattr(service, "unlock", lambda *a, **k: envelope)
    monkeypatch.setattr(asc_manager, "load_account", lambda a: _FakeAccount())
    monkeypatch.setattr(asc_manager, "make_managers", lambda a: None)

    code = asc_manager.main(["unlock", "me.demo.app", "1.0", "--json"])
    assert code == 0
    assert json.loads(capsys.readouterr().out) == envelope


def test_cli_unlock_dry_run(tmp_path, monkeypatch, capsys):
    (tmp_path / "secrets.example.yml").write_text(
        'accounts:\n  primary:\n    asc_api:\n      key_id: "ABCDE12345"\n'
        '      issuer_id: "x"\n      key_content: "REPLACE_WITH"\n')
    monkeypatch.chdir(tmp_path)
    code = asc_manager.main(["unlock", "me.demo.app", "1.0"])
    out = capsys.readouterr().out
    assert code == 0
    assert "[DRY-RUN]" in out


class _FakeAccount:
    account_id = "primary"

    def is_configured(self):
        return True


def test_human_age_formats():
    assert asc_manager._human_age(45) == "45s"
    assert asc_manager._human_age(720) == "12m"
    assert asc_manager._human_age(7754) == "2h 09m"
    assert asc_manager._human_age(90_000) == "25h 00m"
