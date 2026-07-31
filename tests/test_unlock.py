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
    result = service.unlock("me.demo.app", "1.0", assume_yes=True,
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
    result = service.unlock("me.demo.app", "1.0", assume_yes=True,
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


# -- stale gate: cancelling a >1 h submission needs explicit consent ------


def test_service_unlock_stale_without_consent_refuses_before_cancelling(
        tmp_path, monkeypatch, ec_private_key_pem):
    """Non-interactive surfaces (--json, piped stdin) get a typed refusal —
    and the cancel request is never sent."""
    session = _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, _version("WAITING_FOR_REVIEW")),
        FakeResponse(200, _submission()),                          # 2 h old
    )
    result = service.unlock("me.demo.app", "1.0",
                            clock=lambda: NOW, sleep=lambda s: None)
    assert result["ok"] is False
    assert result["error"]["code"] == "stale_submission_unconfirmed"
    assert result["error"]["retryable"] is False
    assert result["error"]["context"]["submitted_at"] == "2026-07-31T08:00:00+00:00"
    assert not session.responses or all(
        r is not None for r in session.responses)  # queue untouched past the find
    assert len(session.requests) == 3              # no PATCH went out


def test_service_unlock_stale_confirm_yes_proceeds(
        tmp_path, monkeypatch, ec_private_key_pem):
    _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, _version("WAITING_FOR_REVIEW")),
        FakeResponse(200, _submission()),
        FakeResponse(200, {"data": {"id": "sub-1", "attributes": {"state": "CANCELING"}}}),
        FakeResponse(200, _version("DEVELOPER_REJECTED")),
    )
    seen = []
    result = service.unlock("me.demo.app", "1.0",
                            confirm=lambda facts: seen.append(facts) or True,
                            clock=lambda: NOW, sleep=lambda s: None)
    assert result["ok"] is True
    assert seen and seen[0]["submission_id"] == "sub-1"
    assert seen[0]["age_seconds"] == pytest.approx(7200)


def test_service_unlock_stale_confirm_no_aborts(
        tmp_path, monkeypatch, ec_private_key_pem):
    session = _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, _version("WAITING_FOR_REVIEW")),
        FakeResponse(200, _submission()),
    )
    result = service.unlock("me.demo.app", "1.0",
                            confirm=lambda facts: False,
                            clock=lambda: NOW, sleep=lambda s: None)
    assert result["ok"] is False
    assert result["error"]["code"] == "stale_submission_unconfirmed"
    assert len(session.requests) == 3              # nothing was cancelled


def test_service_unlock_fresh_never_asks(tmp_path, monkeypatch, ec_private_key_pem):
    _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, _version("WAITING_FOR_REVIEW")),
        FakeResponse(200, _submission("2026-07-31T09:50:00+00:00")),   # 10 min
        FakeResponse(200, {"data": {"id": "sub-1", "attributes": {"state": "CANCELING"}}}),
        FakeResponse(200, _version("DEVELOPER_REJECTED")),
    )
    asked = []
    result = service.unlock("me.demo.app", "1.0",
                            confirm=lambda facts: asked.append(facts) or False,
                            clock=lambda: NOW, sleep=lambda s: None)
    assert result["ok"] is True
    assert not asked                               # fresh → the gate stays silent


def test_cli_unlock_yes_flag_bypasses_the_prompt(monkeypatch, capsys):
    captured = {}

    def fake_unlock(bundle_id, version, **kwargs):
        captured.update(kwargs)
        return {"command": "unlock", "ok": True, "dry_run": False,
                "bundle_id": bundle_id, "version": version,
                "submission_id": "sub-1",
                "submitted_at": "2026-07-31T08:00:00+00:00",
                "age_seconds": 7754.0, "stale": True,
                "already_editable": False, "version_state": "DEVELOPER_REJECTED"}

    monkeypatch.setattr(service, "unlock", fake_unlock)
    monkeypatch.setattr(asc_manager, "load_account", lambda a: _FakeAccount())
    monkeypatch.setattr(asc_manager, "make_managers", lambda a: None)

    assert asc_manager.main(["unlock", "me.demo.app", "1.0", "-y"]) == 0
    assert captured["assume_yes"] is True
    assert captured["confirm"] is None
    out = capsys.readouterr().out
    assert "⚠️" in out                              # consented, but still told


def test_cli_unlock_prompt_accepts_yes(monkeypatch, capsys):
    def fake_unlock(bundle_id, version, assume_yes=False, confirm=None, **kwargs):
        assert confirm is not None
        assert confirm({"submission_id": "sub-1",
                        "submitted_at": "2026-07-31T08:00:00+00:00",
                        "age_seconds": 7754.0}) is True
        return {"command": "unlock", "ok": True, "dry_run": False,
                "bundle_id": bundle_id, "version": version,
                "submission_id": "sub-1",
                "submitted_at": "2026-07-31T08:00:00+00:00",
                "age_seconds": 7754.0, "stale": True,
                "already_editable": False, "version_state": "DEVELOPER_REJECTED"}

    monkeypatch.setattr(service, "unlock", fake_unlock)
    monkeypatch.setattr(asc_manager, "load_account", lambda a: _FakeAccount())
    monkeypatch.setattr(asc_manager, "make_managers", lambda a: None)
    monkeypatch.setattr(asc_manager, "_stdin_is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")

    assert asc_manager.main(["unlock", "me.demo.app", "1.0"]) == 0
    out = capsys.readouterr().out
    # The alert lived in the prompt; the epilogue must not repeat it.
    assert out.count("⚠️") == 0
    assert "canceled" in out


def test_cli_unlock_prompt_defaults_to_no(monkeypatch, capsys):
    def fake_unlock(bundle_id, version, assume_yes=False, confirm=None, **kwargs):
        assert confirm is not None
        if not confirm({"submission_id": "sub-1",
                        "submitted_at": "2026-07-31T08:00:00+00:00",
                        "age_seconds": 7754.0}):
            return {"command": "unlock", "ok": False,
                    "error": {"code": "stale_submission_unconfirmed",
                              "message": "declined", "retryable": False,
                              "remediation": "Re-run with --yes."}}
        raise AssertionError("an empty answer must mean No")

    monkeypatch.setattr(service, "unlock", fake_unlock)
    monkeypatch.setattr(asc_manager, "load_account", lambda a: _FakeAccount())
    monkeypatch.setattr(asc_manager, "make_managers", lambda a: None)
    monkeypatch.setattr(asc_manager, "_stdin_is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "")

    assert asc_manager.main(["unlock", "me.demo.app", "1.0"]) == 1


def test_cli_unlock_json_mode_never_prompts(monkeypatch, capsys):
    captured = {}

    def fake_unlock(bundle_id, version, **kwargs):
        captured.update(kwargs)
        return {"command": "unlock", "ok": False,
                "error": {"code": "stale_submission_unconfirmed",
                          "message": "needs consent", "retryable": False,
                          "remediation": "Re-run with --yes."}}

    monkeypatch.setattr(service, "unlock", fake_unlock)
    monkeypatch.setattr(asc_manager, "load_account", lambda a: _FakeAccount())
    monkeypatch.setattr(asc_manager, "make_managers", lambda a: None)
    monkeypatch.setattr(asc_manager, "_stdin_is_interactive", lambda: True)

    code = asc_manager.main(["unlock", "me.demo.app", "1.0", "--json"])
    assert code == 1
    assert captured["confirm"] is None             # an agent is never prompted
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "stale_submission_unconfirmed"


# -- MCP: agent-first surface ---------------------------------------------
# The tool is exposed library-first, WITHOUT the consent bypass: assume_yes
# stays in a shell where the host prompts on the command (same doctrine as
# --replace-in-review). A stale submission therefore always comes back as the
# typed refusal — the agent surfaces it, a human decides.


def _mcp_call(name, arguments):
    from andp import mcp
    return mcp.handle_message({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments}})


def test_mcp_lists_unlock_with_destructive_annotation():
    from andp import mcp
    response = mcp.handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = {t["name"]: t for t in response["result"]["tools"]}
    assert "unlock" in tools
    assert tools["unlock"]["annotations"]["destructiveHint"] is True
    assert tools["unlock"]["annotations"]["idempotentHint"] is True
    assert "bundle_id" in tools["unlock"]["inputSchema"]["properties"]


def test_mcp_unlock_never_carries_the_consent_bypass(monkeypatch):
    captured = {}

    def fake_unlock(bundle_id, version, **kwargs):
        captured.update(kwargs, bundle_id=bundle_id, version=version)
        return {"command": "unlock", "ok": True, "dry_run": False,
                "bundle_id": bundle_id, "version": version,
                "submission_id": "sub-1",
                "submitted_at": "2026-07-31T09:50:00+00:00",
                "age_seconds": 600.0, "stale": False,
                "already_editable": False, "version_state": "DEVELOPER_REJECTED"}

    monkeypatch.setattr(service, "unlock", fake_unlock)
    response = _mcp_call("unlock", {"bundle_id": "me.demo.app", "version": "1.0"})
    result = response["result"]
    assert result.get("isError") is not True
    assert result["structuredContent"]["ok"] is True
    assert captured["bundle_id"] == "me.demo.app"
    assert not captured.get("assume_yes")           # the bypass stays in the shell
    assert captured.get("confirm") is None          # and no prompt can reach stdio


def test_mcp_unlock_stale_refusal_is_a_typed_error(monkeypatch):
    monkeypatch.setattr(service, "unlock", lambda *a, **k: {
        "command": "unlock", "ok": False,
        "error": {"code": "stale_submission_unconfirmed",
                  "message": "needs a human", "retryable": False,
                  "remediation": "Run `andp unlock --yes` in a shell."}})
    response = _mcp_call("unlock", {"bundle_id": "me.demo.app", "version": "1.0"})
    result = response["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "stale_submission_unconfirmed"


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
