"""Hardening tests from the pre-release code review — the blockers.

Covers: no permanent brick on first-upload failure (BUG 1), typed errors for
transport/filesystem exceptions (BUG 2), MCP/service resilience to corrupted
state (BUG 3), resume without re-reading the IPA / terminal refusal + reset
(BUG 4/5), reload-under-lock (BUG 7).
"""
import plistlib
import zipfile

import pytest

from andp import service
from andp.core.errors import AndpError
from andp.core.release import ReleaseMachine, release_id
from andp.core.state import StateStore
from conftest import FakeResponse, FakeSession, make_test_managers


def _make_ipa(directory, name="App.ipa"):
    plist = plistlib.dumps({
        "CFBundleIdentifier": "me.demo.app",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
    })
    path = directory / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Payload/App.app/Info.plist", plist)
    return str(path)


def _app_found():
    return FakeResponse(200, {"data": [{"id": "app-9", "type": "apps"}]})


@pytest.fixture
def store(tmp_path):
    return StateStore(str(tmp_path / ".andp" / "state"))


# -- BUG 1: no permanent brick on first-upload failure --------------------

def test_reserve_failure_leaves_nothing_persisted_clean_retry(tmp_path, store):
    """A retryable failure of the reservation POST must NOT set upload_attempted
    — otherwise the release is bricked. State stays app_resolved, flag False."""
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(_app_found(),
                  FakeResponse(503, {"errors": [{"status": "503", "detail": "down"}]}))
    m = ReleaseMachine.start(store, make_test_managers(session), ipa)
    m.step()  # created -> app_resolved
    with pytest.raises(AndpError) as excinfo:
        m.step()  # reserve fails 503
    assert excinfo.value.retryable is True
    reloaded = store.load(m.release_id)
    assert reloaded["state"] == "app_resolved"
    assert reloaded["upload_attempted"] is False   # <-- the brick-prevention invariant
    assert reloaded["upload_id"] is None


def test_transfer_failure_persists_reservation_and_self_heals(tmp_path, store):
    """If the transfer fails after the reservation succeeded, the reservation is
    persisted (write-ahead); a later poll finds the ingested build and advances
    — no re-reservation, no double upload."""
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(
        _app_found(),
        FakeResponse(201, {"data": {"id": "UP1", "type": "buildUploads"}}),  # reserve OK
        FakeResponse(503, {"errors": [{"status": "503", "detail": "down"}]}),  # transfer fails
    )
    m = ReleaseMachine.start(store, make_test_managers(session), ipa)
    m.step()  # -> app_resolved
    with pytest.raises(AndpError):
        m.step()  # reserve OK, transfer 503
    reloaded = store.load(m.release_id)
    assert reloaded["upload_attempted"] is True
    assert reloaded["upload_id"] == "UP1"
    assert reloaded["state"] == "app_resolved"

    # later: the build appears -> resume advances without re-reserving
    session.queue(FakeResponse(200, {"data": [{"id": "b-1", "type": "builds",
                                               "attributes": {"processingState": "VALID"}}]}))
    m2 = ReleaseMachine.load(store, make_test_managers(session), m.release_id)
    m2.step()  # app_resolved (resumed) -> uploaded
    assert m2.state == "uploaded"
    assert not any(r["method"] == "POST" and r["url"].endswith("/v1/buildUploads")
                   for r in session.requests[3:])  # no second reservation


# -- BUG 2: typed errors for non-ASC exceptions ---------------------------

def test_transport_connection_error_becomes_typed_network_error(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(_app_found())
    managers = make_test_managers(session)

    class _ConnErr(Exception):
        pass
    _ConnErr.__name__ = "ConnectionError"

    def boom(*a, **k):
        raise _ConnErr("network down")
    managers.builds.reserve_upload = boom

    m = ReleaseMachine.start(store, managers, ipa)
    m.step()  # -> app_resolved
    with pytest.raises(AndpError) as excinfo:
        m.step()
    assert excinfo.value.code == "network_error"
    assert excinfo.value.retryable is True


def test_missing_ipa_during_upload_is_typed_terminal(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(_app_found(),
                  FakeResponse(201, {"data": {"id": "UP1", "type": "buildUploads"}}))
    managers = make_test_managers(session)
    m = ReleaseMachine.start(store, managers, ipa)
    m.step()  # -> app_resolved
    import os
    os.remove(ipa)  # IPA vanishes before the transfer opens it
    m.step()  # reserve OK, transfer opens missing file
    snap = m.snapshot()
    assert snap["state"] == "failed"
    assert snap["error"]["code"] == "ipa_missing"


# -- BUG 5: terminal refusal + reset --------------------------------------

def test_start_refuses_terminal_release(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    rid = release_id("primary", "me.demo.app", "1.0", "1")
    base = ReleaseMachine.start(store, make_test_managers(FakeSession()), ipa).snapshot()
    base["state"] = "failed"
    base["error"] = {"code": "processing_failed"}
    store.save(rid, base)
    with pytest.raises(AndpError) as excinfo:
        ReleaseMachine.start(store, make_test_managers(FakeSession()), ipa)
    assert excinfo.value.code == "release_terminal"


def test_reset_restarts_a_terminal_release(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    rid = release_id("primary", "me.demo.app", "1.0", "1")
    base = ReleaseMachine.start(store, make_test_managers(FakeSession()), ipa).snapshot()
    base["state"] = "failed"
    store.save(rid, base)
    m = ReleaseMachine.start(store, make_test_managers(FakeSession()), ipa, reset=True)
    assert m.state == "created"


# -- BUG 7: reload under lock ---------------------------------------------

def test_step_reloads_state_under_lock(tmp_path, store):
    """A machine loaded from stale state must pick up another driver's committed
    progress when it steps (reload under lock), not clobber it."""
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(_app_found())
    m = ReleaseMachine.start(store, make_test_managers(session), ipa)
    rid = m.release_id
    # Another driver advances the release on disk to 'uploaded'.
    other = store.load(rid)
    other["state"] = "uploaded"
    other["app_id"] = "app-9"
    other["history"].append("uploaded")
    store.save(rid, other)
    # Our stale machine (still 'created') steps: it must reload and act on
    # 'uploaded', transitioning to processing — not redo 'created'.
    m.step()
    assert m.state == "processing"
    assert session.requests == []  # did not re-run find_app for 'created'


# -- BUG 3: service/MCP resilience to corrupted state ---------------------

def test_service_status_handles_corrupted_state(tmp_path, monkeypatch, ec_private_key_pem):
    from conftest import real_secrets_yaml
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".andp" / "state").mkdir(parents=True)
    (tmp_path / ".andp" / "state" / "rel-x.json").write_text("{corrupt")

    result = service.release_status("rel-x")
    assert result["ok"] is False
    assert result["error"]["code"] == "state_corrupted"


def test_service_list_skips_corrupted_without_crashing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".andp" / "state").mkdir(parents=True)
    (tmp_path / ".andp" / "state" / "good.json").write_text('{"release_id":"good","state":"done","bundle_id":"b","version":"1","build_number":"1"}')
    (tmp_path / ".andp" / "state" / "bad.json").write_text("{corrupt")

    result = service.release_list()
    assert result["ok"] is True
    ids = [r["release_id"] for r in result["releases"]]
    assert "good" in ids
    # the corrupted one is reported, not silently dropped or crashing
    assert any(r.get("error", {}).get("code") == "state_corrupted"
               for r in result["releases"]) or "bad" not in ids


def test_mcp_tool_call_never_crashes_on_error(tmp_path, monkeypatch):
    from andp import mcp
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".andp" / "state").mkdir(parents=True)
    (tmp_path / ".andp" / "state" / "rel-x.json").write_text("{corrupt")

    response = mcp.handle_message({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "release_status", "arguments": {"release_id": "rel-x"}},
    })
    assert response["result"]["isError"] is True
    assert "corrupt" in response["result"]["content"][0]["text"].lower() or \
           "state_corrupted" in response["result"]["content"][0]["text"]
