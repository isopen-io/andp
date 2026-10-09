"""Precheck: the listing fields App Review requires at submission are ERRORS.

Each check is read best-effort (a failed read never bricks the hard checks),
but a field read as missing blocks: content rights, primary category, app name
and privacy policy URL per language, copyright, a scheduled release without its
date, App Review contact and demo account, unanswered age rating questions,
Apple's length limits.
"""
from andp.precheck import definition_checks
from listing_fakes import FakeManagers, live_state

_COMPLETE_AGE = {f: "NONE" for f in (
    "alcoholTobaccoOrDrugUseOrReferences", "contests", "gamblingSimulated",
    "gunsOrOtherWeapons", "horrorOrFearThemes", "matureOrSuggestiveThemes",
    "medicalOrTreatmentInformation", "profanityOrCrudeHumor",
    "sexualContentGraphicAndNudity", "sexualContentOrNudity", "violenceCartoonOrFantasy",
    "violenceRealistic", "violenceRealisticProlongedGraphicOrSadistic")}
_COMPLETE_AGE.update({b: False for b in (
    "gambling", "unrestrictedWebAccess", "lootBox", "advertising", "ageAssurance",
    "healthOrWellnessTopics", "messagingAndChat", "parentalControls",
    "userGeneratedContent", "socialMedia")})


def _ready_state(**overrides):
    state = live_state(age_rating=dict(_COMPLETE_AGE))
    state.update(overrides)
    return state


def _errors(state, locales=("fr-FR",), declaration=None):
    managers = FakeManagers(state)
    version = {"id": "v1", "attributes": state["version"]["attributes"]}
    loc_attrs = [dict(state["version_localizations"].get(l, {}), locale=l) for l in locales]
    checks = definition_checks(managers, "APP", version, loc_attrs,
                               declaration if declaration is not None
                               else managers.age_rating.get_declaration("APP"))
    return {c["id"]: c for c in checks if c["level"] == "error"}, checks


def test_a_complete_listing_has_no_definition_error():
    errors, _ = _errors(_ready_state())
    assert errors == {}


def test_missing_content_rights_blocks():
    state = _ready_state()
    state["app"]["contentRightsDeclaration"] = None
    assert "content_rights" in _errors(state)[0]


def test_missing_primary_category_blocks():
    state = _ready_state(categories={"primaryCategory": None})
    assert "primary_category" in _errors(state)[0]


def test_each_version_language_needs_a_name_and_a_privacy_policy():
    state = _ready_state()
    state["version_localizations"]["it"] = {"description": "Un'app."}
    state["app_info_localizations"]["fr-FR"]["privacyPolicyUrl"] = None
    errors, checks = _errors(state, locales=("fr-FR", "it"))
    messages = " ".join(c["message"] for c in checks)
    assert "app_name" in errors and "[it]" in messages
    assert "privacy_policy_url" in errors and "[fr-FR]" in messages


def test_empty_copyright_and_scheduled_release_without_date_block():
    state = _ready_state()
    state["version"]["attributes"].update(copyright="", releaseType="SCHEDULED",
                                          earliestReleaseDate=None)
    errors, _ = _errors(state)
    assert "copyright" in errors and "release_date" in errors


def test_review_contact_and_demo_account_are_required():
    state = _ready_state()
    state["review"]["attributes"].update(contactPhone="", demoAccountPassword=None)
    errors, _ = _errors(state)
    assert "review_contact" in errors and "demo_account" in errors
    assert "contactPhone" in errors["review_contact"]["message"]


def test_no_review_detail_at_all_blocks():
    assert "review_contact" in _errors(_ready_state(review=None))[0]


def test_unanswered_age_rating_questions_block_and_are_named():
    partial = dict(_COMPLETE_AGE, socialMedia=None, advertising=None)
    state = _ready_state(age_rating=partial)
    errors, _ = _errors(state)
    assert "socialMedia" in errors["age_rating_answers"]["message"]
    assert "advertising" in errors["age_rating_answers"]["message"]


def test_lengths_over_apple_limits_block():
    state = _ready_state()
    state["version_localizations"]["fr-FR"]["keywords"] = "é" * 60
    state["version_localizations"]["fr-FR"]["promotionalText"] = "p" * 171
    state["app_info_localizations"]["fr-FR"]["subtitle"] = "s" * 31
    errors, checks = _errors(state)
    lengths = [c["message"] for c in checks if c["id"] == "field_length"]
    assert any("keywords" in m for m in lengths)
    assert any("promotionalText" in m for m in lengths)
    assert any("subtitle" in m for m in lengths)


def test_a_phone_without_country_code_is_a_warning():
    state = _ready_state()
    state["review"]["attributes"]["contactPhone"] = "0612345678"
    _, checks = _errors(state)
    assert any(c["id"] == "review_phone" and c["level"] == "warning" for c in checks)


def test_a_failed_read_skips_only_that_check():
    managers = FakeManagers(_ready_state())

    def boom(*a, **k):
        raise RuntimeError("500")
    managers.listing.app = boom
    version = {"id": "v1", "attributes": {"copyright": ""}}
    checks = definition_checks(managers, "APP", version, [], None)
    ids = {c["id"] for c in checks}
    assert "content_rights" not in ids and "copyright" in ids
