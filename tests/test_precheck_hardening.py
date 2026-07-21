"""Hardening from the v1.3 code review: the prechecked state must NEVER become
terminal on a precheck read error (that would brick the release into a
re-upload). Retryable errors re-raise; non-retryable stay in prechecked.
"""
import plistlib
import zipfile

import pytest

from andp.core.errors import AndpError
from andp.core.release import ReleaseMachine, release_id
from andp.core.state import StateStore
from conftest import FakeResponse, FakeSession, make_test_managers


def _ipa(tmp_path):
    p = tmp_path / "App.ipa"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("Payload/App.app/Info.plist", plistlib.dumps(
            {"CFBundleIdentifier": "me.demo.app", "CFBundleShortVersionString": "1.0",
             "CFBundleVersion": "1"}))
    return str(p)


@pytest.fixture
def store(tmp_path):
    return StateStore(str(tmp_path / ".andp" / "state"))


def _prechecked_state(store, ipa, allow_submit=True):
    rid = release_id("primary", "me.demo.app", "1.0", "1")
    base = ReleaseMachine.start(store, make_test_managers(FakeSession()), ipa,
                                ship=True, allow_submit=allow_submit).snapshot()
    base.update({"state": "prechecked", "app_id": "app-9", "build_id": "build-77",
                 "version_id": "ver-1"})
    base["history"].append("prechecked")
    store.save(rid, base)
    return rid


def _ok_precheck():
    return [
        FakeResponse(200, {"data": {"id": "ver-1", "attributes": {"appVersionState": "PREPARE_FOR_SUBMISSION"}}}),
        FakeResponse(200, {"data": {"id": "build-77"}}),
        FakeResponse(200, {"data": [{"id": "loc-en", "attributes": {
            "locale": "en-US", "description": "Great.", "keywords": "k", "supportUrl": "https://x"}}]}),
        FakeResponse(200, {"data": [{"id": "set-1"}]}),
        FakeResponse(200, {"data": [{"id": "s1"}]}),
    ]


def test_non_retryable_api_error_during_precheck_stays_prechecked(store, tmp_path):
    ipa = _ipa(tmp_path)
    rid = _prechecked_state(store, ipa)
    session = FakeSession()
    session.queue(FakeResponse(404, {"errors": [{"status": "404", "detail": "gone"}]}))  # get_version 404
    m = ReleaseMachine.load(store, make_test_managers(session), rid)
    snap = m.step()
    # MUST NOT be terminal — the release stays recoverable
    assert snap["state"] == "prechecked"
    assert snap["needs_precheck_fix"] is True
    assert m.is_terminal() is False


def test_retryable_api_error_during_precheck_reraises_no_fix_flag(store, tmp_path):
    ipa = _ipa(tmp_path)
    rid = _prechecked_state(store, ipa)
    session = FakeSession()
    session.queue(FakeResponse(503, {"errors": [{"status": "503", "detail": "down"}]}))
    m = ReleaseMachine.load(store, make_test_managers(session), rid)
    with pytest.raises(AndpError) as exc:
        m.step()
    assert exc.value.retryable is True
    reloaded = store.load(rid)
    assert reloaded["state"] == "prechecked"
    assert reloaded.get("needs_precheck_fix") is not True   # not flagged as a fixable error


def test_precheck_recovers_after_fix(store, tmp_path):
    ipa = _ipa(tmp_path)
    rid = _prechecked_state(store, ipa)
    # first poll: no build -> precheck error -> stays prechecked
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": {"id": "ver-1", "attributes": {"appVersionState": "PREPARE_FOR_SUBMISSION"}}}),
        FakeResponse(200, {"data": None}),   # no build -> error
        FakeResponse(200, {"data": [{"id": "loc-en", "attributes": {"locale": "en-US", "description": "x"}}]}),
        FakeResponse(200, {"data": [{"id": "set-1"}]}),
        FakeResponse(200, {"data": [{"id": "s1"}]}),
    )
    m = ReleaseMachine.load(store, make_test_managers(session), rid)
    m.step()
    assert m.snapshot()["needs_precheck_fix"] is True
    assert m.state == "prechecked"

    # second poll after the human fixes it: precheck ok -> awaiting_approval,
    # flag cleared.
    session2 = FakeSession()
    session2.queue(*_ok_precheck())
    m2 = ReleaseMachine.load(store, make_test_managers(session2), rid)
    snap = m2.step()
    assert snap["state"] == "awaiting_approval"
    assert "needs_precheck_fix" not in snap


def test_precheck_report_is_overwritten_not_accumulated(store, tmp_path):
    ipa = _ipa(tmp_path)
    rid = _prechecked_state(store, ipa)
    session = FakeSession()
    # two failing runs; the report must reflect only the latest, not grow
    for _ in range(2):
        session.queue(
            FakeResponse(200, {"data": {"id": "ver-1", "attributes": {"appVersionState": "PREPARE_FOR_SUBMISSION"}}}),
            FakeResponse(200, {"data": None}),
            FakeResponse(200, {"data": [{"id": "loc-en", "attributes": {"locale": "en-US", "description": "x"}}]}),
            FakeResponse(200, {"data": [{"id": "set-1"}]}),
            FakeResponse(200, {"data": [{"id": "s1"}]}),
        )
    m = ReleaseMachine.load(store, make_test_managers(session), rid)
    m.step()
    first = m.snapshot()["precheck_report"]["errors"]
    m.step()
    second = m.snapshot()["precheck_report"]["errors"]
    assert first == second == 1   # not 2 (overwritten, not accumulated)


def test_screenshot_count_sums_across_sets(tmp_path):
    """set A empty + set B with 2 -> total 2 -> no error."""
    from andp.precheck import run_precheck
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": {"id": "ver-1", "attributes": {"appVersionState": "PREPARE_FOR_SUBMISSION"}}}),
        FakeResponse(200, {"data": {"id": "build-77"}}),
        FakeResponse(200, {"data": [{"id": "loc-en", "attributes": {
            "locale": "en-US", "description": "x", "keywords": "k", "supportUrl": "u"}}]}),
        FakeResponse(200, {"data": [{"id": "set-A"}, {"id": "set-B"}]}),   # two sets
        FakeResponse(200, {"data": []}),                                   # set-A -> 0
        FakeResponse(200, {"data": [{"id": "s1"}, {"id": "s2"}]}),         # set-B -> 2
    )
    report = run_precheck(make_test_managers(session), "app-9", "ver-1")
    assert not any(c["id"] == "screenshots" for c in report["checks"])   # total 2 -> ok


def test_empty_body_get_does_not_crash(tmp_path):
    """A 204/empty-body GET must not AttributeError (get_version defensive)."""
    from andp.asc.managers import Managers
    from andp.asc.client import ASCClient

    class _Auth:
        def token(self):
            return "t"

    session = FakeSession()
    session.queue(FakeResponse(204, None, content=b""))   # empty body
    managers = Managers(ASCClient(auth=_Auth(), session=session, sleep=lambda s: None))
    assert managers.appstore.get_version("ver-1") is None
