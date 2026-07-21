"""AgeRatingManager — the 2025-overhauled ageRatingDeclaration.

Reads via the EDITABLE appInfo (not appInfos[0], which may be the locked live
declaration — B3); writes via PATCH /v1/ageRatingDeclarations/{id}. validate()
is pure: taxonomy enforcement, unknown-key rejection, unknown-value passthrough.
"""
import pytest

from conftest import FakeResponse, FakeSession, make_test_managers


def _mgr(session):
    return make_test_managers(session).age_rating


# -- validate() (pure) ------------------------------------------------------

def test_validate_accepts_known_ternary_and_boolean():
    attrs, errors, warnings = _mgr(FakeSession()).validate({
        "violenceCartoonOrFantasy": "INFREQUENT_OR_MILD",
        "gambling": False,
        "unrestrictedWebAccess": True,
    })
    assert errors == []
    assert attrs["violenceCartoonOrFantasy"] == "INFREQUENT_OR_MILD"
    assert attrs["gambling"] is False and attrs["unrestrictedWebAccess"] is True


def test_validate_rejects_unknown_key():
    _, errors, _ = _mgr(FakeSession()).validate({"nonsenseField": "NONE"})
    assert any("nonsenseField" in e for e in errors)


def test_validate_passes_through_unknown_enum_value_with_warning():
    # N4: a value Apple added after this ANDP release must still go through.
    attrs, errors, warnings = _mgr(FakeSession()).validate(
        {"violenceRealistic": "BRAND_NEW_APPLE_VALUE"})
    assert errors == []
    assert attrs["violenceRealistic"] == "BRAND_NEW_APPLE_VALUE"
    assert any("violenceRealistic" in w for w in warnings)


def test_validate_enum_field_and_coerces_string_bool():
    attrs, errors, _ = _mgr(FakeSession()).validate(
        {"ageRatingOverride": "SEVENTEEN_PLUS", "lootBox": "true"})
    assert errors == []
    assert attrs["ageRatingOverride"] == "SEVENTEEN_PLUS"
    assert attrs["lootBox"] is True          # "true" coerced to bool


def test_validate_2025_boolean_fields_recognised():
    _, errors, _ = _mgr(FakeSession()).validate({
        "messagingAndChat": True, "parentalControls": False,
        "userGeneratedContent": True, "healthOrWellnessTopics": False})
    assert errors == []


# -- I/O --------------------------------------------------------------------

def test_get_declaration_picks_editable_appinfo():
    session = FakeSession()
    # two appInfos: one live (locked), one editable
    session.queue(FakeResponse(200, {"data": [
        {"id": "info-live", "attributes": {"state": "READY_FOR_DISTRIBUTION"}},
        {"id": "info-edit", "attributes": {"state": "PREPARE_FOR_SUBMISSION"}},
    ], "links": {}}))
    session.queue(FakeResponse(200, {"data": {"id": "decl-9", "attributes": {"gambling": False}}}))
    decl = _mgr(session).get_declaration("APP")
    assert decl["id"] == "decl-9"
    # the second GET must target the EDITABLE appInfo, not the live one
    assert "info-edit" in session.requests[-1]["url"]
    assert "info-live" not in session.requests[-1]["url"]


def test_get_declaration_none_when_no_appinfos():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [], "links": {}}))
    assert _mgr(session).get_declaration("APP") is None


def test_update_declaration_patches_by_id():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": {"id": "decl-9"}}))
    _mgr(session).update_declaration("decl-9", {"gambling": True})
    req = session.requests[-1]
    assert req["method"] == "PATCH"
    assert req["url"].endswith("/v1/ageRatingDeclarations/decl-9")
    assert req["json"]["data"]["attributes"]["gambling"] is True
    assert req["json"]["data"]["id"] == "decl-9"
