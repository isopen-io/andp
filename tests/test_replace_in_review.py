"""Replacing the build of a version that is already in review.

Until now a version sitting in WAITING_FOR_REVIEW was a dead end: the machine
saw IN_REVIEW_VERSION_STATES, concluded "a submission already exists", and
transitioned straight to `done`. That guard is right by default — creating a
second submission is an error — but it left no way to say "that submission is
stale, replace its build with this one", which is exactly what happens when a
release is cut, rejected for packaging, fixed, and rebuilt.

Doing it by hand means cancelling the submission, waiting for the version to
fall back to an editable state, re-attaching the build and resubmitting. This
suite pins that sequence into the machine, behind an explicit opt-in.
"""
import plistlib
import zipfile

import pytest

from andp.core.release import ReleaseMachine
from andp.core.state import StateStore
from conftest import (
    FakeResponse, FakeSession, make_test_managers, real_secrets_yaml, write_secrets,
)


def _make_ipa(directory, name="App.ipa"):
    path = directory / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Payload/App.app/Info.plist", plistlib.dumps({
            "CFBundleIdentifier": "me.demo.app",
            "CFBundleShortVersionString": "1.0",
            "CFBundleVersion": "1",
            "ITSAppUsesNonExemptEncryption": False,
        }))
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


def _version(state):
    return FakeResponse(200, {"data": [{"id": "ver-1", "type": "appStoreVersions",
                                        "attributes": {"appVersionState": state}}]})


def _submission(state="WAITING_FOR_REVIEW", sid="sub-old"):
    return {"id": sid, "type": "reviewSubmissions", "attributes": {"state": state}}


@pytest.fixture
def store(tmp_path):
    return StateStore(str(tmp_path / ".andp" / "state"))


def _drive(m, max_steps=40):
    for _ in range(max_steps):
        m.step()
        if m.is_terminal() or m.snapshot().get("needs_approval"):
            return m.snapshot()
    raise AssertionError("did not settle")


# -- the API surface the manoeuvre needs ----------------------------------

def test_find_in_review_submission_returns_the_submitted_one():
    # find_open_review_submission only matches READY_FOR_REVIEW — a submission
    # that has actually been sent is WAITING_FOR_REVIEW and was invisible.
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [_submission("WAITING_FOR_REVIEW")]}))
    managers = make_test_managers(session)

    found = managers.appstore.find_in_review_submission("app-9")

    assert found["id"] == "sub-old"


def test_find_in_review_submission_returns_none_when_nothing_is_pending():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": []}))
    managers = make_test_managers(session)

    assert managers.appstore.find_in_review_submission("app-9") is None


def test_cancel_review_submission_patches_canceled():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": _submission("CANCELING")}))
    managers = make_test_managers(session)

    managers.appstore.cancel_review_submission("sub-old")

    sent = session.requests[-1]
    assert sent["method"] == "PATCH"
    assert sent["url"].endswith("/v1/reviewSubmissions/sub-old")
    assert sent["json"]["data"]["attributes"] == {"canceled": True}


# -- the machine ----------------------------------------------------------

def test_a_version_in_review_is_still_left_alone_by_default(tmp_path, store):
    # The default must not change: without the opt-in, an in-review version is
    # reported done and no submission is touched.
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(
        _app_found(), *_upload_flow(), _build_valid(),
        _version("WAITING_FOR_REVIEW"),
    )
    m = ReleaseMachine.start(store, make_test_managers(session), ipa,
                             ship=True, allow_submit=True)

    final = _drive(m)

    assert final["state"] == "done"
    assert not any(r["method"] == "PATCH" and "reviewSubmissions" in r["url"]
                   for r in session.requests)


def test_replace_in_review_cancels_then_reattaches_and_submits(tmp_path, store):
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(
        _app_found(), *_upload_flow(), _build_valid(),
        _version("WAITING_FOR_REVIEW"),                       # ensure_version
        FakeResponse(200, {"data": [_submission()]}),          # find_in_review_submission
        FakeResponse(200, {"data": _submission("CANCELING")}),  # cancel
        _version("DEVELOPER_REJECTED"),                        # now editable
        FakeResponse(204, None, content=b""),                  # attach_build
        # No compliance call: the IPA already declares
        # ITSAppUsesNonExemptEncryption, so the machine skips that mutation.
        FakeResponse(200, {"data": []}),                       # no open submission
        FakeResponse(201, {"data": {"id": "sub-new", "type": "reviewSubmissions"}}),
        FakeResponse(201, {"data": {"id": "item-1", "type": "reviewSubmissionItems"}}),
        FakeResponse(200, {"data": {"id": "sub-new", "type": "reviewSubmissions",
                                    "attributes": {"state": "WAITING_FOR_REVIEW"}}}),
    )
    m = ReleaseMachine.start(store, make_test_managers(session), ipa,
                             ship=True, allow_submit=True, skip_precheck=True,
                             replace_in_review=True)

    final = _drive(m)

    assert final["state"] == "done"
    assert final["submission_id"] == "sub-new"
    assert final["replaced_submission_id"] == "sub-old"
    # The old submission was cancelled before the new one was created.
    patched = [i for i, r in enumerate(session.requests)
               if r["method"] == "PATCH" and r["url"].endswith("/reviewSubmissions/sub-old")]
    created = [i for i, r in enumerate(session.requests)
               if r["method"] == "POST" and r["url"].endswith("/v1/reviewSubmissions")]
    assert patched and created and patched[0] < created[0]


def test_replace_waits_while_the_cancellation_settles(tmp_path, store):
    # Cancelling is not instant: ASC reports CANCELING, and the version only
    # falls back to an editable state a moment later. The machine must poll
    # rather than charge ahead and fail on a still-locked version.
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(
        _app_found(), *_upload_flow(), _build_valid(),
        _version("WAITING_FOR_REVIEW"),
        FakeResponse(200, {"data": [_submission()]}),
        FakeResponse(200, {"data": _submission("CANCELING")}),
        _version("WAITING_FOR_REVIEW"),   # not settled yet
    )
    m = ReleaseMachine.start(store, make_test_managers(session), ipa,
                             ship=True, allow_submit=True, replace_in_review=True)

    for _ in range(7):
        m.step()
        if m.snapshot()["state"] == "review_canceling":
            m.step()   # the wait itself: re-read the version, find it still locked
            break

    snap = m.snapshot()
    assert snap["state"] == "review_canceling"
    assert not m.is_terminal()
    assert snap.get("retry_after")


def test_replace_fails_clearly_when_no_submission_is_pending(tmp_path, store):
    # The version says in-review but no submission is pending: that is a state
    # we do not understand, so refuse rather than guess.
    ipa = _make_ipa(tmp_path)
    session = FakeSession()
    session.queue(
        _app_found(), *_upload_flow(), _build_valid(),
        _version("WAITING_FOR_REVIEW"),
        FakeResponse(200, {"data": []}),   # nothing pending
    )
    m = ReleaseMachine.start(store, make_test_managers(session), ipa,
                             ship=True, allow_submit=True, replace_in_review=True)

    final = _drive(m)

    assert final["state"] == "failed"
    assert final["error"]["code"] == "submission_not_found"


# -- the flag reaches the machine from the command line -------------------

def test_cli_passes_replace_in_review_through_to_the_service(
        tmp_path, monkeypatch, ec_private_key_pem):
    """`release start --replace-in-review` must reach ReleaseMachine.start.

    A manoeuvre that forfeits a slot in Apple's review queue is worthless if it
    is only reachable from Python: the operator hitting this situation is at a
    terminal.
    """
    from andp.asc import asc_manager
    from andp import service

    write_secrets(tmp_path, real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    seen = {}

    def _capture(ipa_path, **kwargs):
        seen.update(kwargs)
        return {"command": "release_start", "ok": True, "release_id": "rid", "state": "created"}

    monkeypatch.setattr(service, "release_start", _capture)
    assert asc_manager.main(
        ["release", "start", "App.ipa", "--ship", "--replace-in-review", "--json"]) == 0
    assert seen["replace_in_review"] is True
    assert seen["ship"] is True


def test_cli_leaves_replace_off_by_default(tmp_path, monkeypatch, ec_private_key_pem):
    from andp.asc import asc_manager
    from andp import service

    write_secrets(tmp_path, real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    seen = {}
    monkeypatch.setattr(service, "release_start",
                        lambda ipa_path, **kw: (seen.update(kw), {
                            "command": "release_start", "ok": True,
                            "release_id": "rid", "state": "created"})[1])
    assert asc_manager.main(["release", "start", "App.ipa", "--ship", "--json"]) == 0
    assert seen["replace_in_review"] is False
