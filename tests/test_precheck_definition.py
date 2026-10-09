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
    state["version_localizations"]["fr-FR"]["keywords"] = "é" * 101
    state["version_localizations"]["fr-FR"]["promotionalText"] = "p" * 171
    state["app_info_localizations"]["fr-FR"]["subtitle"] = "s" * 31
    errors, checks = _errors(state)
    lengths = [c["message"] for c in checks if c["id"] == "field_length"]
    assert any("keywords" in m for m in lengths)
    assert any("promotionalText" in m for m in lengths)
    assert any("subtitle" in m for m in lengths)


def test_a_phone_without_country_code_blocks():
    # App Store Connect, 2026-08-19: the App Review phone must be international.
    state = _ready_state()
    state["review"]["attributes"]["contactPhone"] = "0612345678"
    errors, _ = _errors(state)
    assert "+" in errors["review_phone"]["message"]


def test_a_failed_read_skips_only_that_check():
    managers = FakeManagers(_ready_state())

    def boom(*a, **k):
        raise RuntimeError("500")
    managers.listing.app = boom
    version = {"id": "v1", "attributes": {"copyright": ""}}
    checks = definition_checks(managers, "APP", version, [], None)
    ids = {c["id"] for c in checks}
    assert "content_rights" not in ids and "copyright" in ids


# -- visuals: iPhone Duo (App Asset Library) ----------------------------------

import datetime  # noqa: E402

from andp.precheck import visual_checks  # noqa: E402
from listing_fakes import media_managers  # noqa: E402


def _placement(group, ptype="APP_SCREENSHOT"):
    return {"id": f"p-{group}", "placementType": ptype, "placementGroup": group,
            "mediaType": "IMAGE", "mediaId": "i", "fileName": "01.png", "fileSize": 1}


def _visual(placements, legacy_total=1, today=datetime.date(2026, 10, 9),
            platform="IOS"):
    managers = media_managers(live_state(placements={"vl-fr-FR": placements}))
    version = {"id": "v1", "attributes": {"platform": platform}}
    return visual_checks(managers, version, [("vl-fr-FR", "fr-FR", legacy_total)], today=today)


def test_missing_iphone_duo_screenshots_warn_before_april_2027():
    checks = _visual([_placement("IPHONE_DYNAMIC_ISLAND_LARGE_PROFILE")])
    duo = [c for c in checks if c["id"] == "iphone_duo_screenshots"]
    assert duo and duo[0]["level"] == "warning" and "2027-04-01" in duo[0]["message"]


def test_missing_iphone_duo_screenshots_block_from_april_2027():
    checks = _visual([_placement("IPHONE_DYNAMIC_ISLAND_LARGE_PROFILE")],
                     today=datetime.date(2027, 4, 1))
    assert [c["level"] for c in checks if c["id"] == "iphone_duo_screenshots"] == ["error"]


def test_iphone_duo_placements_satisfy_the_check():
    checks = _visual([_placement("IPHONE_DUO_PROFILE")], today=datetime.date(2027, 5, 1))
    assert not [c for c in checks if c["id"] == "iphone_duo_screenshots"]


def test_a_mac_version_is_not_asked_for_iphone_duo_screenshots():
    assert _visual([], platform="MAC_OS", legacy_total=1) == []


def test_asset_library_screenshots_count_when_the_legacy_sets_are_empty():
    assert not [c for c in _visual([_placement("IPHONE_DUO_PROFILE")], legacy_total=0)
                if c["id"] == "screenshots"]
    checks = _visual([], legacy_total=0)
    assert [c["level"] for c in checks if c["id"] == "screenshots"] == ["error"]


def test_screenshots_error_stands_when_placements_cannot_be_read():
    managers = media_managers(live_state())

    def boom(*a):
        raise RuntimeError("500")
    managers.asset_library.placements = boom
    checks = visual_checks(managers, {"id": "v1", "attributes": {}},
                           [("vl-fr-FR", "fr-FR", 0)], today=datetime.date(2026, 10, 9))
    assert [c["id"] for c in checks] == ["screenshots"]
