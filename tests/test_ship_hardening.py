"""Hardening from the v1.1 code review — the App Store path blockers.

BUG 1: write-ahead submission_id -> never double-submit to App Review.
BUG 2: allow_submit is read live (policy revocation stops in-flight releases).
BUG 3: approval is bound to the plan (plan_changed) + approved_ts.
BUG 4: blocking `release <ipa> --ship` is rejected, not silently ignored.
BUG 5: needs_approval surfaces in the agent view.
BUG 6: an unknown/absent version state is rejected defensively.
"""
import plistlib
import zipfile

import pytest

from andp.core.errors import AndpError
from andp.core.release import ReleaseMachine, release_id
from andp.core.state import StateStore
from conftest import FakeResponse, FakeSession, make_test_managers


def _make_ipa(directory, encryption=False):
    info = {"CFBundleIdentifier": "me.demo.app", "CFBundleShortVersionString": "1.0",
            "CFBundleVersion": "1"}
    if encryption is not None:
        info["ITSAppUsesNonExemptEncryption"] = encryption
    path = directory / "App.ipa"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Payload/App.app/Info.plist", plistlib.dumps(info))
    return str(path)


@pytest.fixture
def store(tmp_path):
    return StateStore(str(tmp_path / ".andp" / "state"))


def _awaiting_state(store, ipa, **overrides):
    rid = release_id("primary", "me.demo.app", "1.0", "1")
    base = ReleaseMachine.start(store, make_test_managers(FakeSession()), ipa,
                                ship=True, allow_submit=True).snapshot()
    base.update({"state": "awaiting_approval", "app_id": "app-9",
                 "build_id": "build-77", "version_id": "ver-1"})
    base.update(overrides)
    base["history"].append("awaiting_approval")
    store.save(rid, base)
    return rid


# -- BUG 1: no double submission ------------------------------------------

def test_submission_id_is_write_ahead_and_resume_uses_get_by_id(store, tmp_path):
    ipa = _make_ipa(tmp_path)
    rid = _awaiting_state(store, ipa)

    # First attempt: create succeeds (submission_id must be persisted), then
    # mark_submitted fails with a retryable 503.
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": []}),                                   # find_open -> none
        FakeResponse(201, {"data": {"id": "sub-1", "type": "reviewSubmissions"}}),  # create
        FakeResponse(201, {"data": {"id": "it-1"}}),                       # add item
        FakeResponse(503, {"errors": [{"status": "503", "detail": "down"}]}),  # mark_submitted fails
    )
    m = ReleaseMachine.load(store, make_test_managers(session), rid)
    with pytest.raises(AndpError):
        m.step()
    persisted = store.load(rid)
    assert persisted["submission_id"] == "sub-1"   # write-ahead survived the failure
    assert persisted["state"] == "awaiting_approval"

    # Resume: must reuse sub-1 via GET by id, NOT create a second submission.
    session2 = FakeSession()
    session2.queue(
        FakeResponse(200, {"data": {"id": "sub-1", "type": "reviewSubmissions",
                                    "attributes": {"state": "READY_FOR_REVIEW"}}}),  # get by id
        FakeResponse(200, {"data": [{"id": "it-1", "type": "reviewSubmissionItems",
                                     "relationships": {"appStoreVersion": {"data": {"id": "ver-1"}}}}]}),
        FakeResponse(200, {"data": {"id": "sub-1"}}),                       # mark_submitted
    )
    m2 = ReleaseMachine.load(store, make_test_managers(session2), rid)
    final = m2.step()
    assert final["state"] in ("submitted", "done")
    assert not any(r["method"] == "POST" and r["url"].endswith("/v1/reviewSubmissions")
                   for r in session2.requests)   # no second create


def test_resume_submitted_submission_is_treated_as_done(store, tmp_path):
    ipa = _make_ipa(tmp_path)
    rid = _awaiting_state(store, ipa, submission_id="sub-1")
    session = FakeSession()
    session.queue(
        # get by id -> already WAITING_FOR_REVIEW (submit already happened)
        FakeResponse(200, {"data": {"id": "sub-1", "type": "reviewSubmissions",
                                    "attributes": {"state": "WAITING_FOR_REVIEW"}}}),
    )
    m = ReleaseMachine.load(store, make_test_managers(session), rid)
    final = m.step()
    assert final["state"] in ("submitted", "done")
    # only the GET happened — no re-submit
    assert all(r["method"] == "GET" for r in session.requests)


# -- BUG 2: live allow_submit ---------------------------------------------

def test_gate_reads_allow_submit_live(store, tmp_path):
    ipa = _make_ipa(tmp_path)
    rid = _awaiting_state(store, ipa, allow_submit=False, approved=False)
    live = {"allow": False}
    session = FakeSession()
    m = ReleaseMachine.load(store, make_test_managers(session), rid,
                            allow_submit_fn=lambda: live["allow"])
    snap = m.step()
    assert snap["state"] == "awaiting_approval"   # gate closed live
    assert not session.requests

    live["allow"] = True   # policy flipped on
    session.queue(
        FakeResponse(200, {"data": []}),
        FakeResponse(201, {"data": {"id": "sub-1"}}),
        FakeResponse(200, {"data": {"id": "sub-1", "attributes": {"state": "READY_FOR_REVIEW"}}}),
        FakeResponse(200, {"data": []}),
        FakeResponse(201, {"data": {"id": "it-1"}}),
        FakeResponse(200, {"data": {"id": "sub-1"}}),
    )
    m2 = ReleaseMachine.load(store, make_test_managers(session), rid,
                             allow_submit_fn=lambda: live["allow"])
    m2.step()
    assert m2.state in ("submitted", "done")


# -- BUG 3: approval bound to plan ----------------------------------------

def test_approve_records_timestamp_and_plan_hash(store, tmp_path):
    ipa = _make_ipa(tmp_path)
    rid = _awaiting_state(store, ipa, allow_submit=False)
    m = ReleaseMachine.load(store, make_test_managers(FakeSession()), rid,
                            clock=lambda: 1234.0)
    m.approve()
    raw = store.load(rid)
    assert raw["approved"] is True
    assert raw["approved_ts"] == 1234.0
    assert raw["plan_hash"] == "build-77:ver-1"


def test_plan_changed_invalidates_approval(store, tmp_path):
    ipa = _make_ipa(tmp_path)
    rid = _awaiting_state(store, ipa, allow_submit=False)
    m = ReleaseMachine.load(store, make_test_managers(FakeSession()), rid)
    m.approve()
    # tamper: the pinned build changed since approval
    raw = store.load(rid)
    raw["build_id"] = "build-OTHER"
    store.save(rid, raw)
    m2 = ReleaseMachine.load(store, make_test_managers(FakeSession()), rid)
    final = m2.step()
    assert final["state"] == "failed"
    assert final["error"]["code"] == "plan_changed"


# -- BUG 6: defensive unknown version state -------------------------------

def test_absent_version_state_is_rejected(store, tmp_path):
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9", "type": "apps"}]}),
        FakeResponse(201, {"data": {"id": "UP1"}}),
        FakeResponse(201, {"data": {"id": "UPF1", "attributes": {"uploadOperations": []}}}),
        FakeResponse(200, {"data": {"id": "UPF1"}}),
        FakeResponse(200, {"data": [{"id": "build-77", "attributes": {"processingState": "VALID"}}]}),
        # ensure_version returns a version with NO state attribute
        FakeResponse(200, {"data": [{"id": "ver-1", "type": "appStoreVersions", "attributes": {}}]}),
    )
    m = ReleaseMachine.start(store, make_test_managers(session), ipa,
                             ship=True, allow_submit=True, uses_non_exempt_encryption=False)
    for _ in range(15):
        m.step()
        if m.is_terminal():
            break
    snap = m.snapshot()
    assert snap["state"] == "failed"
    assert snap["error"]["code"] == "version_not_editable"


# -- BUG 4: blocking release --ship is rejected, not silently ignored -----

def test_blocking_release_ship_is_rejected(tmp_path, monkeypatch, ec_private_key_pem, capsys):
    from conftest import real_secrets_yaml
    from andp.asc import asc_manager
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    ipa = _make_ipa(tmp_path)
    code = asc_manager.main(["release", ipa, "--ship"])
    out = capsys.readouterr().out
    assert code == 2
    assert "release start --ship" in out


# -- BUG 5: needs_approval surfaces in the agent view ---------------------

def test_snapshot_view_exposes_needs_approval(tmp_path, monkeypatch, ec_private_key_pem):
    from conftest import real_secrets_yaml, FakeSession, make_test_managers
    from andp import service
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    (tmp_path / "andp.yml").write_text("policy:\n  allow_submit: false\n")
    monkeypatch.chdir(tmp_path)
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),
        FakeResponse(201, {"data": {"id": "UP1"}}),
        FakeResponse(201, {"data": {"id": "UPF1", "attributes": {"uploadOperations": []}}}),
        FakeResponse(200, {"data": {"id": "UPF1"}}),
        FakeResponse(200, {"data": [{"id": "build-77", "attributes": {"processingState": "VALID"}}]}),
        FakeResponse(200, {"data": [{"id": "ver-1", "attributes": {"appVersionState": "PREPARE_FOR_SUBMISSION"}}]}),
        FakeResponse(204, None, content=b""),
        FakeResponse(200, {"data": {"id": "build-77"}}),
    )
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    rid = service.release_start(ipa, ship=True, skip_precheck=True)["release_id"]
    result = None
    for _ in range(12):
        result = service.release_poll(rid)
        if result.get("needs_approval") or result["terminal"]:
            break
    assert result["state"] == "awaiting_approval"
    assert result["needs_approval"] is True
    assert result["terminal"] is False
    assert "next_action" in result
