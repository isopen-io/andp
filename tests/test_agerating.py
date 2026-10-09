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


# -- API 4.5 (2025-2026 questionnaire) ----------------------------------------

from andp.asc.agerating import missing_answers, validate_declaration


def test_validate_accepts_social_media_questions():
    attrs, errors, warnings = validate_declaration(
        {"socialMedia": True, "socialMediaAgeRestricted": "false"})
    assert errors == [] and warnings == []
    assert attrs == {"socialMedia": True, "socialMediaAgeRestricted": False}


def test_validate_override_v2_accepts_the_new_tiers_without_warning():
    attrs, errors, warnings = validate_declaration({"ageRatingOverrideV2": "EIGHTEEN_PLUS"})
    assert errors == [] and warnings == []
    assert attrs["ageRatingOverrideV2"] == "EIGHTEEN_PLUS"


def test_validate_deprecated_override_warns_towards_v2():
    _, errors, warnings = validate_declaration({"ageRatingOverride": "THIRTEEN_PLUS"})
    assert errors == []
    assert any("ageRatingOverrideV2" in w for w in warnings)


def test_validate_korea_override_knows_the_new_values():
    _, errors, warnings = validate_declaration(
        {"koreaAgeRatingOverride": "TWELVE_PLUS"})
    assert errors == [] and warnings == []


def test_validate_removed_seventeen_plus_is_dropped_with_a_warning():
    attrs, errors, warnings = validate_declaration({"seventeenPlus": False})
    assert errors == []
    assert "seventeenPlus" not in attrs        # sending it would be refused by the API
    assert any("seventeenPlus" in w for w in warnings)


def test_validate_developer_info_url_must_be_an_http_url():
    attrs, errors, _ = validate_declaration(
        {"developerAgeRatingInfoUrl": "https://example.com/age",
         "gracRatingClassificationNumber": "CC-OB-240101-001"})
    assert errors == []
    assert attrs["developerAgeRatingInfoUrl"] == "https://example.com/age"
    _, errors, _ = validate_declaration({"developerAgeRatingInfoUrl": "not a url"})
    assert any("developerAgeRatingInfoUrl" in e for e in errors)


def test_validate_legacy_frequency_values_pass_with_a_warning():
    attrs, errors, warnings = validate_declaration({"contests": "FREQUENT"})
    assert errors == [] and attrs["contests"] == "FREQUENT"
    assert any("contests" in w for w in warnings)


def test_missing_answers_lists_every_unanswered_required_question():
    answered = {f: "NONE" for f in (
        "alcoholTobaccoOrDrugUseOrReferences", "contests", "gamblingSimulated",
        "gunsOrOtherWeapons", "horrorOrFearThemes", "matureOrSuggestiveThemes",
        "medicalOrTreatmentInformation", "profanityOrCrudeHumor",
        "sexualContentGraphicAndNudity", "sexualContentOrNudity",
        "violenceCartoonOrFantasy", "violenceRealistic",
        "violenceRealisticProlongedGraphicOrSadistic")}
    answered.update({b: False for b in (
        "gambling", "unrestrictedWebAccess", "lootBox", "advertising",
        "ageAssurance", "healthOrWellnessTopics", "messagingAndChat",
        "parentalControls", "userGeneratedContent", "socialMedia")})
    assert missing_answers(answered) == []
    gap = dict(answered, advertising=None)
    assert missing_answers(gap) == ["advertising"]


def test_missing_answers_asks_for_the_age_restriction_only_with_social_media():
    base = {"socialMedia": True, "socialMediaAgeRestricted": None}
    assert "socialMediaAgeRestricted" in missing_answers(base)
    assert "socialMediaAgeRestricted" not in missing_answers(
        {"socialMedia": False, "socialMediaAgeRestricted": None})
