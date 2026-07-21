"""Precheck store-config advisories: pricing / availability / age rating.

These are best-effort warnings appended to the existing precheck — a failed
advisory read must never brick the hard checks (guarded), and they never turn
ok:true into ok:false on their own.
"""
from andp.precheck import run_precheck
from conftest import FakeResponse, FakeSession, make_test_managers


def _happy_path(session):
    """Queue a clean, submittable version (no hard errors)."""
    session.queue(
        FakeResponse(200, {"data": {"id": "ver-1", "attributes": {"appVersionState": "PREPARE_FOR_SUBMISSION"}}}),
        FakeResponse(200, {"data": {"id": "build-77"}}),
        FakeResponse(200, {"data": [{"id": "loc-en", "attributes": {
            "locale": "en-US", "description": "Great app.", "keywords": "k", "supportUrl": "https://x"}}]}),
        FakeResponse(200, {"data": [{"id": "set-1"}]}),
        FakeResponse(200, {"data": [{"id": "s1"}]}),
    )


def _report(session):
    return run_precheck(make_test_managers(session), "app-9", "ver-1")


def test_warns_when_store_config_missing():
    session = FakeSession()
    _happy_path(session)
    session.queue(
        FakeResponse(200, {"data": None}),                       # get_schedule -> no price
        FakeResponse(200, {"data": None}),                       # appAvailabilityV2 -> zero territories
        FakeResponse(200, {"data": [{"id": "info", "attributes": {"state": "PREPARE_FOR_SUBMISSION"}}], "links": {}}),
        FakeResponse(200, {"data": {"id": "decl", "attributes": {}}}),  # age rating all-null -> unset
    )
    report = _report(session)
    ids = {c["id"] for c in report["checks"]}
    assert {"pricing", "availability", "age_rating"} <= ids
    assert report["ok"] is True                                  # warnings only, still passes
    assert all(c["level"] == "warning"
               for c in report["checks"] if c["id"] in {"pricing", "availability", "age_rating"})


def test_no_store_warnings_when_all_configured():
    session = FakeSession()
    _happy_path(session)
    session.queue(
        FakeResponse(200, {"data": {"id": "sched-1"}}),          # price schedule present
        FakeResponse(200, {"data": {"id": "av-1", "attributes": {}}}),   # availability present
        FakeResponse(200, {"data": [{"id": "ta", "attributes": {"available": True},
                                     "relationships": {"territory": {"data": {"id": "USA"}}}}], "links": {}}),
        FakeResponse(200, {"data": [{"id": "info", "attributes": {"state": "PREPARE_FOR_SUBMISSION"}}], "links": {}}),
        FakeResponse(200, {"data": {"id": "decl", "attributes": {"violenceCartoonOrFantasy": "NONE"}}}),
    )
    report = _report(session)
    ids = {c["id"] for c in report["checks"]}
    assert not ({"pricing", "availability", "age_rating"} & ids)


def test_store_read_failure_is_swallowed_not_a_hard_error():
    session = FakeSession()
    _happy_path(session)
    # queue a 500 for the first store read; the rest are unqueued (also swallowed)
    session.queue(FakeResponse(500, {"errors": [{"status": "500", "detail": "boom"}]}))
    report = _report(session)
    assert report["ok"] is True                                  # advisory failure never bricks
    assert report["errors"] == 0
