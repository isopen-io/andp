"""The release machine: resumable, single-effect-per-step, crash-safe.

Covers happy paths (TestFlight, with/without group), resume at every state,
crash-after-upload idempotency, retryable-vs-terminal failure semantics,
build-id pinning, ipa-changed detection, and processing budget.
"""
import plistlib
import zipfile

import pytest

from andp.core.errors import AndpError
from andp.core.release import ReleaseMachine, release_id
from andp.core.state import StateStore
from conftest import FakeResponse, FakeSession, make_test_managers


def _make_ipa(directory, name="App.ipa", bundle_id="me.demo.app", version="1.0", build="1"):
    plist = plistlib.dumps({
        "CFBundleIdentifier": bundle_id,
        "CFBundleShortVersionString": version,
        "CFBundleVersion": build,
    })
    path = directory / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Payload/App.app/Info.plist", plist)
    return str(path)


def _upload_flow():
    # POST buildUploads, POST buildUploadFiles (no chunks), PATCH commit
    return [
        FakeResponse(201, {"data": {"id": "UP1", "type": "buildUploads"}}),
        FakeResponse(201, {"data": {"id": "UPF1", "type": "buildUploadFiles",
                                    "attributes": {"uploadOperations": []}}}),
        FakeResponse(200, {"data": {"id": "UPF1", "type": "buildUploadFiles"}}),
    ]


def _app_found():
    return FakeResponse(200, {"data": [{"id": "app-9", "type": "apps",
                                        "attributes": {"name": "Demo", "bundleId": "me.demo.app"}}]})


def _build(state="VALID", bid="build-77"):
    return FakeResponse(200, {"data": [{"id": bid, "type": "builds",
                                        "attributes": {"processingState": state}}]})


@pytest.fixture
def store(tmp_path):
    return StateStore(str(tmp_path / ".andp" / "state"))


def _drive(machine, max_steps=20):
    """Run steps to completion (test helper; the machine itself never sleeps)."""
    for _ in range(max_steps):
        machine.step()
        if machine.is_terminal():
            return machine.snapshot()
    raise AssertionError("machine did not terminate")


# -- identity -------------------------------------------------------------

def test_release_id_includes_account_bundle_version_build():
    rid = release_id("primary", "me.demo.app", "1.0", "1")
    assert rid == "primary-me-demo-app-1-0-1"
    # different account => different id (no cross-account collision)
    assert release_id("secondary", "me.demo.app", "1.0", "1") != rid


# -- happy paths ----------------------------------------------------------

def test_full_testflight_path_with_group(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(
        _app_found(),
        *_upload_flow(),
        _build("VALID"),
        # ensure_group: found
        FakeResponse(200, {"data": [{"id": "grp-1", "type": "betaGroups",
                                     "attributes": {"name": "Beta"}}]}),
        FakeResponse(204, None, content=b""),  # add_build_to_group
    )
    m = ReleaseMachine.start(store, make_test_managers(session), ipa, group="Beta")

    final = _drive(m)

    assert final["state"] == "done"
    assert final["app_id"] == "app-9"
    assert final["build_id"] == "build-77"
    assert final["processing_state"] == "VALID"
    # the build linked to the group is the PINNED id
    link = session.requests[-1]
    assert "/v1/betaGroups/grp-1/relationships/builds" in link["url"]
    assert link["json"]["data"][0]["id"] == "build-77"


def test_full_testflight_path_without_group_stops_at_done(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(_app_found(), *_upload_flow(), _build("VALID"))
    m = ReleaseMachine.start(store, make_test_managers(session), ipa)

    final = _drive(m)

    assert final["state"] == "done"
    assert "group_linked" not in final.get("history", [])


# -- resume ---------------------------------------------------------------

def test_resume_at_processing_does_not_reupload(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    rid = release_id("primary", "me.demo.app", "1.0", "1")
    store.save(rid, {
        "schema_version": 1, "release_id": rid, "account": "primary",
        "bundle_id": "me.demo.app", "version": "1.0", "build_number": "1",
        "ipa_path": ipa, "ipa_sha256": ReleaseMachine._sha256(ipa),
        "state": "processing", "want_group": None, "app_id": "app-9",
        "upload_attempted": True, "upload_id": "UP1", "build_id": None,
        "processing_state": "PROCESSING", "poll_count": 0, "poll_budget": 30,
        "error": None,
    })
    session = FakeSession()
    session.queue(_build("VALID"))  # only a poll, no upload
    m = ReleaseMachine.start(store, make_test_managers(session), ipa)

    final = _drive(m)

    assert final["state"] == "done"
    # exactly one request: the processing poll — no re-upload
    assert len(session.requests) == 1
    assert "/v1/builds" in session.requests[0]["url"]


def test_resume_after_crash_before_upload_persist_finds_build(tmp_path, store):
    """Crash after upload but before persisting 'uploaded': upload_attempted is
    set, state still app_resolved. Resume must find the build, not re-upload."""
    ipa = _make_ipa(tmp_path)
    rid = release_id("primary", "me.demo.app", "1.0", "1")
    store.save(rid, {
        "schema_version": 1, "release_id": rid, "account": "primary",
        "bundle_id": "me.demo.app", "version": "1.0", "build_number": "1",
        "ipa_path": ipa, "ipa_sha256": ReleaseMachine._sha256(ipa),
        "state": "app_resolved", "want_group": None, "app_id": "app-9",
        "upload_attempted": True, "upload_id": None, "build_id": None,
        "processing_state": None, "poll_count": 0, "poll_budget": 30, "error": None,
    })
    session = FakeSession()
    # resume upload branch: look up build by (app, build_number) -> found
    session.queue(_build("PROCESSING"), _build("VALID"))
    m = ReleaseMachine.start(store, make_test_managers(session), ipa)

    final = _drive(m)

    assert final["state"] == "done"
    # no buildUploads POST happened
    assert not any(r["method"] == "POST" and "buildUploads" in r["url"]
                   for r in session.requests)


def test_resume_after_crash_upload_inconclusive_refuses(tmp_path, store):
    """upload_attempted but no build visible yet => inconclusive => the machine
    refuses to re-upload and surfaces upload_incomplete (retryable)."""
    ipa = _make_ipa(tmp_path)
    rid = release_id("primary", "me.demo.app", "1.0", "1")
    store.save(rid, {
        "schema_version": 1, "release_id": rid, "account": "primary",
        "bundle_id": "me.demo.app", "version": "1.0", "build_number": "1",
        "ipa_path": ipa, "ipa_sha256": ReleaseMachine._sha256(ipa),
        "state": "app_resolved", "want_group": None, "app_id": "app-9",
        "upload_attempted": True, "upload_id": None, "build_id": None,
        "processing_state": None, "poll_count": 0, "poll_budget": 30, "error": None,
    })
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": []}))  # no build visible
    m = ReleaseMachine.start(store, make_test_managers(session), ipa)

    with pytest.raises(AndpError) as excinfo:
        m.step()
    assert excinfo.value.code == "upload_incomplete"
    assert excinfo.value.retryable is True
    # state was NOT advanced and NOT failed
    assert store.load(rid)["state"] == "app_resolved"


def test_start_resumes_existing_state(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    m1 = ReleaseMachine.start(store, make_test_managers(session), ipa, group="Beta")
    assert m1.state == "created"
    # a second start with the same ipa loads the same machine
    m2 = ReleaseMachine.start(store, make_test_managers(FakeSession()), ipa, group="Beta")
    assert m2.release_id == m1.release_id
    assert m2.state == "created"


def test_start_refuses_when_ipa_changed(tmp_path, store):
    ipa = _make_ipa(tmp_path, version="1.0", build="1")
    ReleaseMachine.start(store, make_test_managers(FakeSession()), ipa)
    # same triple, different bytes
    with zipfile.ZipFile(ipa, "a") as zf:
        zf.writestr("extra.txt", "changed")
    with pytest.raises(AndpError) as excinfo:
        ReleaseMachine.start(store, make_test_managers(FakeSession()), ipa)
    assert excinfo.value.code == "ipa_changed"


# -- failures -------------------------------------------------------------

def test_app_not_found_is_terminal_failure(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": []}))  # find_app empty
    m = ReleaseMachine.start(store, make_test_managers(session), ipa)
    m.step()
    snap = m.snapshot()
    assert snap["state"] == "failed"
    assert snap["error"]["code"] == "app_not_found"
    assert m.is_terminal()


def test_processing_failed_is_terminal(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(_app_found(), *_upload_flow(), _build("FAILED"))
    m = ReleaseMachine.start(store, make_test_managers(session), ipa)
    final = _drive(m)  # reaches terminal 'failed'
    assert final["state"] == "failed"
    assert final["error"]["code"] == "processing_failed"
    assert final["error"]["retryable"] is False


def test_processing_still_processing_reports_retry_after(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(_app_found(), *_upload_flow(), _build("PROCESSING"))
    m = ReleaseMachine.start(store, make_test_managers(session), ipa)
    m.step()  # created -> app_resolved
    m.step()  # app_resolved -> uploaded
    m.step()  # uploaded -> processing
    snap = m.step()  # one poll: still processing
    assert snap["state"] == "processing"
    assert snap["poll_count"] == 1
    assert snap["retry_after"] == 60
    assert not m.is_terminal()


def test_processing_budget_exhaustion_times_out(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    # budget of 2 polls, both still PROCESSING
    session.queue(_app_found(), *_upload_flow(), _build("PROCESSING"), _build("PROCESSING"))
    m = ReleaseMachine.start(store, make_test_managers(session), ipa, poll_budget=2)
    m.step(); m.step(); m.step()  # -> processing
    m.step()  # poll 1
    snap = m.step()  # poll 2 -> budget exhausted
    assert snap["state"] == "failed"
    assert snap["error"]["code"] == "processing_timeout"


def test_retryable_error_keeps_state_not_failed(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    # 503 is retryable but the client does NOT auto-retry it (only 429), so it
    # surfaces to the machine cleanly.
    session.queue(_app_found(), *_upload_flow(),
                  FakeResponse(503, {"errors": [{"status": "503", "detail": "unavailable"}]}))
    m = ReleaseMachine.start(store, make_test_managers(session), ipa)
    m.step(); m.step(); m.step()  # -> processing
    with pytest.raises(AndpError) as excinfo:
        m.step()  # poll hits 503
    assert excinfo.value.code == "asc_unavailable"
    assert excinfo.value.retryable is True
    # state stays 'processing', not 'failed'
    assert m.snapshot()["state"] == "processing"


def test_terminal_step_is_noop(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(_app_found(), *_upload_flow(), _build("VALID"))
    m = ReleaseMachine.start(store, make_test_managers(session), ipa)
    _drive(m)
    before = m.snapshot()
    m.step()  # no-op on 'done'
    assert m.snapshot() == before
