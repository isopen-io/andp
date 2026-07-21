"""Pre-submission precheck (read-only): catch what Apple rejects before submit.

Errors are strictly hard, reliably-detectable requirements (editable version,
attached build, non-empty description, >=1 screenshot, at least one locale).
Everything else is a warning. run_precheck never mutates.
"""
from andp.precheck import run_precheck, _content_warnings
from conftest import FakeResponse, FakeSession, make_test_managers


def _version(state="PREPARE_FOR_SUBMISSION"):
    return FakeResponse(200, {"data": {"id": "ver-1", "type": "appStoreVersions",
                                        "attributes": {"appVersionState": state}}})


def _build(present=True):
    return FakeResponse(200, {"data": {"id": "build-77"} if present else None})


def _locs(items):
    return FakeResponse(200, {"data": items})


def _loc(lid, locale="en-US", description="A great app.", whats_new=None,
         keywords="k", support_url="https://x"):
    attrs = {"locale": locale, "description": description, "keywords": keywords,
             "supportUrl": support_url}
    if whats_new is not None:
        attrs["whatsNew"] = whats_new
    return {"id": lid, "type": "appStoreVersionLocalizations", "attributes": attrs}


def _sets(items):
    return FakeResponse(200, {"data": items})


def _shots(n):
    return FakeResponse(200, {"data": [{"id": f"s{i}"} for i in range(n)]})


def _report(session):
    managers = make_test_managers(session)
    return run_precheck(managers, "app-9", "ver-1")


# -- happy path -----------------------------------------------------------

def test_clean_version_passes(tmp_path):
    session = FakeSession()
    session.queue(
        _version("PREPARE_FOR_SUBMISSION"),
        _build(True),
        _locs([_loc("loc-en")]),
        _sets([{"id": "set-1"}]),      # localization's screenshot sets
        _shots(3),                      # count for set-1 -> 3
    )
    report = _report(session)
    assert report["ok"] is True
    assert report["errors"] == 0


# -- hard errors ----------------------------------------------------------

def test_non_editable_version_is_error(tmp_path):
    session = FakeSession()
    session.queue(_version("READY_FOR_SALE"), _build(True),
                  _locs([_loc("loc-en")]), _sets([{"id": "s"}]), _shots(1))
    report = _report(session)
    assert report["ok"] is False
    assert any(c["id"] == "version_editable" and c["level"] == "error" for c in report["checks"])


def test_no_build_attached_is_error(tmp_path):
    session = FakeSession()
    session.queue(_version(), _build(False),
                  _locs([_loc("loc-en")]), _sets([{"id": "s"}]), _shots(1))
    report = _report(session)
    assert report["ok"] is False
    assert any(c["id"] == "build_attached" and c["level"] == "error" for c in report["checks"])


def test_empty_description_is_error(tmp_path):
    session = FakeSession()
    session.queue(_version(), _build(True),
                  _locs([_loc("loc-en", description="")]),
                  _sets([{"id": "s"}]), _shots(1))
    report = _report(session)
    assert report["ok"] is False
    assert any(c["id"] == "description" and c["level"] == "error" for c in report["checks"])


def test_zero_screenshots_is_error_even_with_empty_set(tmp_path):
    session = FakeSession()
    session.queue(_version(), _build(True), _locs([_loc("loc-en")]),
                  _sets([{"id": "set-1"}]),   # a set exists...
                  _shots(0))                   # ...but it is EMPTY
    report = _report(session)
    assert report["ok"] is False
    assert any(c["id"] == "screenshots" and c["level"] == "error" for c in report["checks"])


def test_no_localizations_is_error(tmp_path):
    session = FakeSession()
    session.queue(_version(), _build(True), _locs([]))
    report = _report(session)
    assert report["ok"] is False
    assert any(c["id"] == "localizations" and c["level"] == "error" for c in report["checks"])


# -- warnings (never block) -----------------------------------------------

def test_empty_whatsnew_string_warns_but_null_does_not(tmp_path):
    # whatsNew "" (settable, update) -> warning
    session = FakeSession()
    session.queue(_version(), _build(True),
                  _locs([_loc("loc-en", whats_new="")]),
                  _sets([{"id": "s"}]), _shots(1))
    report = _report(session)
    assert report["ok"] is True   # warning only
    assert any(c["id"] == "whatsNew" and c["level"] == "warning" for c in report["checks"])


def test_null_whatsnew_does_not_warn(tmp_path):
    # whatsNew absent/null (first version) -> no warning
    session = FakeSession()
    session.queue(_version(), _build(True),
                  _locs([_loc("loc-en", whats_new=None)]),
                  _sets([{"id": "s"}]), _shots(1))
    report = _report(session)
    assert not any(c["id"] == "whatsNew" for c in report["checks"])


def test_cross_platform_and_placeholder_are_warnings():
    warnings = _content_warnings("Also on Android! TODO finish this. lorem ipsum")
    ids = {w["id"] for w in warnings}
    assert "cross_platform_mention" in ids
    assert "placeholder_text" in ids
    assert all(w["level"] == "warning" for w in warnings)


def test_missing_support_url_and_keywords_warn(tmp_path):
    session = FakeSession()
    session.queue(_version(), _build(True),
                  _locs([_loc("loc-en", keywords="", support_url="")]),
                  _sets([{"id": "s"}]), _shots(1))
    report = _report(session)
    assert report["ok"] is True
    ids = {c["id"] for c in report["checks"] if c["level"] == "warning"}
    assert "keywords" in ids
    assert "supportUrl" in ids
