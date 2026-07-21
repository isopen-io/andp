"""The --ship App Store path: version -> attach build -> compliance ->
awaiting_approval (gate) -> submit, with idempotent submission recovery.
"""
import plistlib
import zipfile

import pytest

from andp.core.errors import AndpError
from andp.core.release import ReleaseMachine, release_id
from andp.core.state import StateStore
from conftest import FakeResponse, FakeSession, make_test_managers


def _make_ipa(directory, name="App.ipa", encryption=None):
    info = {
        "CFBundleIdentifier": "me.demo.app",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
    }
    if encryption is not None:
        info["ITSAppUsesNonExemptEncryption"] = encryption
    path = directory / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Payload/App.app/Info.plist", plistlib.dumps(info))
    return str(path)


def _app_found():
    return FakeResponse(200, {"data": [{"id": "app-9", "type": "apps"}]})


def _upload_flow():
    return [
        FakeResponse(201, {"data": {"id": "UP1", "type": "buildUploads"}}),
        FakeResponse(201, {"data": {"id": "UPF1", "type": "buildUploadFiles",
                                    "attributes": {"uploadOperations": []}}}),
        FakeResponse(200, {"data": {"id": "UPF1", "type": "buildUploadFiles"}}),
    ]


def _build_valid():
    return FakeResponse(200, {"data": [{"id": "build-77", "type": "builds",
                                        "attributes": {"processingState": "VALID"}}]})


def _version(state="PREPARE_FOR_SUBMISSION"):
    return FakeResponse(200, {"data": [{"id": "ver-1", "type": "appStoreVersions",
                                        "attributes": {"appVersionState": state}}]})


@pytest.fixture
def store(tmp_path):
    return StateStore(str(tmp_path / ".andp" / "state"))


def _drive(m, max_steps=30):
    for _ in range(max_steps):
        m.step()
        if m.is_terminal():
            return m.snapshot()
        if m.snapshot().get("needs_approval"):
            return m.snapshot()
    raise AssertionError("did not settle")


# -- happy path: policy pre-authorises submit -----------------------------

def test_full_ship_with_allow_submit(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(
        _app_found(), *_upload_flow(), _build_valid(),
        _version("PREPARE_FOR_SUBMISSION"),          # ensure_version
        FakeResponse(204, None, content=b""),         # attach_build
        FakeResponse(200, {"data": {"id": "build-77", "type": "builds"}}),  # set compliance
        FakeResponse(200, {"data": []}),              # find_open_review_submission -> none
        FakeResponse(201, {"data": {"id": "sub-1", "type": "reviewSubmissions"}}),  # create
        FakeResponse(201, {"data": {"id": "item-1", "type": "reviewSubmissionItems"}}),  # add item
        FakeResponse(200, {"data": {"id": "sub-1", "type": "reviewSubmissions",
                                    "attributes": {"state": "WAITING_FOR_REVIEW"}}}),  # submit
    )
    m = ReleaseMachine.start(store, make_test_managers(session), ipa,
                             ship=True, allow_submit=True,
                             uses_non_exempt_encryption=False)
    final = _drive(m)
    assert final["state"] == "done"
    assert final["version_id"] == "ver-1"
    assert final["submission_id"] == "sub-1"
    assert "submitted" in final["history"]
    # the build relationship was attached before submission
    attach = [r for r in session.requests
              if r["method"] == "PATCH" and "appStoreVersions/ver-1/relationships/build" in r["url"]]
    assert len(attach) == 1


# -- the approval gate ----------------------------------------------------

def test_gate_blocks_without_approval_then_proceeds(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(
        _app_found(), *_upload_flow(), _build_valid(),
        _version("PREPARE_FOR_SUBMISSION"),
        FakeResponse(204, None, content=b""),         # attach_build
        FakeResponse(200, {"data": {"id": "build-77"}}),  # compliance
    )
    m = ReleaseMachine.start(store, make_test_managers(session), ipa,
                             ship=True, allow_submit=False,
                             uses_non_exempt_encryption=False)
    snap = _drive(m)
    # stops at the gate — no submission created, poll never crosses it
    assert snap["state"] == "awaiting_approval"
    assert snap["needs_approval"] is True
    assert not any("reviewSubmissions" in r["url"] for r in session.requests)

    # human approves out of band, then it submits
    m.approve()
    session.queue(
        FakeResponse(200, {"data": []}),
        FakeResponse(201, {"data": {"id": "sub-1", "type": "reviewSubmissions"}}),
        FakeResponse(201, {"data": {"id": "item-1", "type": "reviewSubmissionItems"}}),
        FakeResponse(200, {"data": {"id": "sub-1", "type": "reviewSubmissions"}}),
    )
    final = _drive(m)
    assert final["state"] == "done"


# -- version editability --------------------------------------------------

def test_ship_rejects_non_editable_version(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(_app_found(), *_upload_flow(), _build_valid(),
                  _version("READY_FOR_SALE"))
    m = ReleaseMachine.start(store, make_test_managers(session), ipa,
                             ship=True, allow_submit=True,
                             uses_non_exempt_encryption=False)
    final = _drive(m)
    assert final["state"] == "failed"
    assert final["error"]["code"] == "version_not_editable"


def test_ready_for_review_is_editable(tmp_path, store):
    """A pre-filled app auto-advances to READY_FOR_REVIEW — must be accepted."""
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(
        _app_found(), *_upload_flow(), _build_valid(),
        _version("READY_FOR_REVIEW"),
        FakeResponse(204, None, content=b""),
        FakeResponse(200, {"data": {"id": "build-77"}}),
        FakeResponse(200, {"data": []}),
        FakeResponse(201, {"data": {"id": "sub-1"}}),
        FakeResponse(201, {"data": {"id": "item-1"}}),
        FakeResponse(200, {"data": {"id": "sub-1"}}),
    )
    m = ReleaseMachine.start(store, make_test_managers(session), ipa,
                             ship=True, allow_submit=True,
                             uses_non_exempt_encryption=False)
    assert _drive(m)["state"] == "done"


# -- compliance -----------------------------------------------------------

def test_compliance_undeclared_fails_early(tmp_path, store):
    """No andp.yml value and no ITSAppUsesNonExemptEncryption in the plist."""
    ipa = _make_ipa(tmp_path, encryption=None)
    session = FakeSession()
    session.queue(_app_found(), *_upload_flow(), _build_valid(),
                  _version("PREPARE_FOR_SUBMISSION"),
                  FakeResponse(204, None, content=b""))  # attach_build
    m = ReleaseMachine.start(store, make_test_managers(session), ipa,
                             ship=True, allow_submit=True,
                             uses_non_exempt_encryption=None)
    final = _drive(m)
    assert final["state"] == "failed"
    assert final["error"]["code"] == "compliance_undeclared"


def test_compliance_from_info_plist_skips_api(tmp_path, store):
    """The plist declares compliance -> no PATCH /v1/builds needed."""
    ipa = _make_ipa(tmp_path, encryption=False)
    session = FakeSession()
    session.queue(
        _app_found(), *_upload_flow(), _build_valid(),
        _version("PREPARE_FOR_SUBMISSION"),
        FakeResponse(204, None, content=b""),      # attach_build
        FakeResponse(200, {"data": []}),           # find_open (no compliance PATCH before this)
        FakeResponse(201, {"data": {"id": "sub-1"}}),
        FakeResponse(201, {"data": {"id": "item-1"}}),
        FakeResponse(200, {"data": {"id": "sub-1"}}),
    )
    m = ReleaseMachine.start(store, make_test_managers(session), ipa,
                             ship=True, allow_submit=True,
                             uses_non_exempt_encryption=None)
    final = _drive(m)
    assert final["state"] == "done"
    # no PATCH to /v1/builds/ for compliance (plist already declares it)
    assert not any(r["method"] == "PATCH" and "/v1/builds/build-77" in r["url"]
                   for r in session.requests)


# -- submission recovery --------------------------------------------------

def test_recovery_open_submission_with_our_version_resubmits(tmp_path, store):
    """Resume at awaiting_approval where an open submission already holds our
    version -> just (re-)submit, don't create a second submission."""
    ipa = _make_ipa(tmp_path)
    rid = release_id("primary", "me.demo.app", "1.0", "1")
    base = ReleaseMachine.start(store, make_test_managers(FakeSession()), ipa,
                                ship=True, allow_submit=True).snapshot()
    base.update({"state": "awaiting_approval", "app_id": "app-9", "build_id": "build-77",
                 "version_id": "ver-1"})
    base["history"].append("awaiting_approval")
    store.save(rid, base)

    session = FakeSession()
    session.queue(
        # find_open_review_submission -> an open one exists
        FakeResponse(200, {"data": [{"id": "sub-9", "type": "reviewSubmissions"}]}),
        # its items reference our version
        FakeResponse(200, {"data": [{"id": "it-1", "type": "reviewSubmissionItems",
                                     "relationships": {"appStoreVersion": {"data": {"id": "ver-1"}}}}]}),
        # mark_submitted
        FakeResponse(200, {"data": {"id": "sub-9"}}),
    )
    m = ReleaseMachine.load(store, make_test_managers(session), rid)
    final = _drive(m)
    assert final["state"] == "done"
    assert final["submission_id"] == "sub-9"
    # did NOT create a new submission
    assert not any(r["method"] == "POST" and r["url"].endswith("/v1/reviewSubmissions")
                   for r in session.requests)


def test_recovery_open_submission_other_version_escalates(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    rid = release_id("primary", "me.demo.app", "1.0", "1")
    base = ReleaseMachine.start(store, make_test_managers(FakeSession()), ipa,
                                ship=True, allow_submit=True).snapshot()
    base.update({"state": "awaiting_approval", "app_id": "app-9", "build_id": "build-77",
                 "version_id": "ver-1"})
    base["history"].append("awaiting_approval")
    store.save(rid, base)

    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "sub-9", "type": "reviewSubmissions"}]}),
        FakeResponse(200, {"data": [{"id": "it-1", "type": "reviewSubmissionItems",
                                     "relationships": {"appStoreVersion": {"data": {"id": "ver-OTHER"}}}}]}),
    )
    m = ReleaseMachine.load(store, make_test_managers(session), rid)
    final = _drive(m)
    assert final["state"] == "failed"
    assert final["error"]["code"] == "review_submission_conflict"


def test_ship_with_metadata_pushes_before_approval(tmp_path, store):
    import os as _os
    ipa = _make_ipa(tmp_path)
    root = str(tmp_path / "meta")
    _os.makedirs(_os.path.join(root, "en-US"))
    with open(_os.path.join(root, "en-US", "whatsNew.txt"), "w") as f:
        f.write("Notes.\n")
    session = FakeSession()
    session.queue(
        _app_found(), *_upload_flow(), _build_valid(),
        _version("PREPARE_FOR_SUBMISSION"),           # ensure_version
        FakeResponse(204, None, content=b""),          # attach_build
        FakeResponse(200, {"data": {"id": "build-77"}}),   # compliance
        # metadata push: pinned version_id -> no ensure_version; loc GET+PATCH
        FakeResponse(200, {"data": [{"id": "loc-en", "attributes": {"locale": "en-US"}}]}),
        FakeResponse(200, {"data": {"id": "loc-en"}}),
        # submit
        FakeResponse(200, {"data": []}),
        FakeResponse(201, {"data": {"id": "sub-1"}}),
        FakeResponse(201, {"data": {"id": "it-1"}}),
        FakeResponse(200, {"data": {"id": "sub-1"}}),
    )
    m = ReleaseMachine.start(store, make_test_managers(session), ipa,
                             ship=True, allow_submit=True,
                             uses_non_exempt_encryption=False, metadata_dir=root)
    final = _drive(m)
    assert final["state"] == "done"
    assert "metadata_pending" in final["history"]
