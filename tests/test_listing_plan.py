"""Plan (read-only diff) and apply of the App Store listing."""
from andp.listing_plan import apply_plan, build_plan, public_changes
from listing_fakes import FakeManagers, live_state


def _desired(**overrides):
    base = {"platform": "IOS", "app": {}, "categories": {}, "app_info_localizations": {},
            "version": {}, "phased_release": None, "version_localizations": {},
            "review": {}, "review_attachments": [], "accessibility": {},
            "encryption": None, "encryption_document": None, "eula": None,
            "age_rating": None, "pricing": None, "availability": None,
            "errors": [], "warnings": []}
    base.update(overrides)
    return base


def _plan(state, desired, version="1.2.0"):
    managers = FakeManagers(state)
    plan = build_plan(managers, "APP", desired, version=version)
    return managers, plan


def _fields(plan):
    return {(c["family"], c["scope"], c["field"]): c for c in plan["changes"]}


def test_plan_reads_only_and_lists_each_changed_field():
    desired = _desired(
        app={"contentRightsDeclaration": "USES_THIRD_PARTY_CONTENT"},
        categories={"primaryCategory": "SOCIAL_NETWORKING", "secondaryCategory": "EDUCATION"},
        app_info_localizations={"fr-FR": {"subtitle": "Chat et vocaux",
                                          "name": "Acme"}},
        version={"copyright": "2026 Acme"},
        version_localizations={"fr-FR": {"description": "Une app.",
                                         "promotionalText": "Nouveau"}})
    managers, plan = _plan(live_state(), desired)
    assert managers.writes == []
    got = _fields(plan)
    assert got[("app", "app", "contentRightsDeclaration")]["desired"] == "USES_THIRD_PARTY_CONTENT"
    assert got[("categories", "app", "secondaryCategory")]["current"] is None
    assert got[("app_info_localization", "fr-FR", "subtitle")]["action"] == "update"
    assert got[("version", "1.2.0", "copyright")]["current"] == "2025 Acme"
    assert got[("version_localization", "fr-FR", "promotionalText")]["action"] == "update"
    assert ("app_info_localization", "fr-FR", "name") not in got     # unchanged
    assert ("categories", "app", "primaryCategory") not in got
    assert plan["unchanged"] == 3
    assert plan["version"] == {"id": "v1", "version": "1.2.0",
                               "state": "PREPARE_FOR_SUBMISSION", "editable": True}


def test_a_new_locale_is_a_create():
    desired = _desired(app_info_localizations={"it": {"name": "Acme"}},
                       version_localizations={"it": {"description": "Un'app."}})
    _, plan = _plan(live_state(), desired)
    got = _fields(plan)
    assert got[("app_info_localization", "it", "name")]["action"] == "create"
    assert got[("version_localization", "it", "description")]["action"] == "create"


def test_a_new_app_info_locale_without_a_name_is_an_error():
    _, plan = _plan(live_state(), _desired(app_info_localizations={"it": {"subtitle": "Chat"}}))
    assert "app_info_localization it: a new language needs a name" in plan["errors"]


def test_secrets_are_masked_in_the_public_view():
    desired = _desired(review={"demoAccountPassword": "new-secret", "notes": "Hi"})
    _, plan = _plan(live_state(), desired)
    change = _fields(plan)[("review", "1.2.0", "demoAccountPassword")]
    shown = public_changes([change])[0]
    assert shown["current"] == "<set>" and shown["desired"] == "<new value>"
    assert "new-secret" not in repr(public_changes(plan["changes"]))
    assert "old" not in repr(public_changes(plan["changes"]))


def test_unchanged_secret_is_not_a_change():
    desired = _desired(review={"demoAccountPassword": "old"})
    _, plan = _plan(live_state(), desired)
    assert plan["changes"] == []


def test_dates_compare_as_instants_not_strings():
    state = live_state()
    state["version"]["attributes"].update(releaseType="SCHEDULED",
                                          earliestReleaseDate="2026-11-01T01:00:00-07:00")
    desired = _desired(version={"releaseType": "SCHEDULED",
                                "earliestReleaseDate": "2026-11-01T08:00:00Z"})
    _, plan = _plan(state, desired)
    assert plan["changes"] == []


def test_locked_version_marks_its_changes_and_apply_refuses_them():
    state = live_state()
    state["version"]["attributes"]["appVersionState"] = "READY_FOR_DISTRIBUTION"
    managers, plan = _plan(state, _desired(version={"copyright": "2026 Acme"}))
    change = _fields(plan)[("version", "1.2.0", "copyright")]
    assert change["locked"] is True
    result = apply_plan(managers, "APP", plan)
    assert managers.writes == []
    assert result["families"]["version"]["ok"] is False


def test_locked_app_info_marks_categories_and_localizations():
    state = live_state(app_info={"id": "ai", "state": "READY_FOR_DISTRIBUTION",
                                 "editable": False})
    _, plan = _plan(state, _desired(categories={"secondaryCategory": "EDUCATION"}))
    assert _fields(plan)[("categories", "app", "secondaryCategory")]["locked"] is True


def test_no_editable_version_skips_version_families_with_a_note():
    state = live_state()
    state["version"]["attributes"]["appVersionState"] = "READY_FOR_DISTRIBUTION"
    _, plan = _plan(state, _desired(version={"copyright": "2026 Acme"}), version=None)
    assert plan["version"] is None
    assert any("no editable" in n for n in plan["notes"])
    assert plan["changes"] == []


def test_age_rating_diff_and_read_only_territory_ratings():
    desired = _desired(age_rating={"messagingAndChat": True, "socialMedia": True})
    _, plan = _plan(live_state(), desired)
    got = _fields(plan)
    assert got[("age_rating", "app", "socialMedia")]["desired"] is True
    assert ("age_rating", "app", "messagingAndChat") not in got
    assert plan["read_only"]["territory_age_ratings"] == {"THIRTEEN_PLUS": 174}


def test_accessibility_compares_with_the_published_declaration():
    state = live_state(accessibility=[
        {"id": "a1", "attributes": {"deviceFamily": "IPHONE", "state": "PUBLISHED",
                                    "supportsVoiceover": True, "supportsDarkInterface": None}}])
    desired = _desired(accessibility={"IPHONE": {"supportsVoiceover": True,
                                                 "supportsDarkInterface": True},
                                      "IPAD": {"supportsVoiceover": True}})
    _, plan = _plan(state, desired)
    got = _fields(plan)
    assert got[("accessibility", "IPHONE", "supportsDarkInterface")]["action"] == "update"
    assert ("accessibility", "IPHONE", "supportsVoiceover") not in got
    assert got[("accessibility", "IPAD", "supportsVoiceover")]["action"] == "create"


def test_encryption_declaration_matching_an_existing_one_is_unchanged():
    attrs = {"appDescription": "E2EE", "containsProprietaryCryptography": False,
             "containsThirdPartyCryptography": True, "availableOnFrenchStore": True}
    state = live_state(encryption=[{"id": "e1", "attributes": dict(
        attrs, appEncryptionDeclarationState="APPROVED")}])
    _, plan = _plan(state, _desired(encryption=attrs))
    assert plan["changes"] == []
    _, plan = _plan(live_state(), _desired(encryption=attrs))
    assert {c["action"] for c in plan["changes"]} == {"create"}


def test_phased_release_and_eula_and_attachments():
    desired = _desired(phased_release=True, eula={"standard": True},
                       review_attachments=["/tmp/demo.mov"])
    state = live_state(eula={"id": "eu", "text": "Old", "territories": {"FRA"}},
                       attachments={"other.png"})
    _, plan = _plan(state, desired)
    got = _fields(plan)
    assert got[("phased_release", "1.2.0", "phasedRelease")]["action"] == "create"
    assert got[("eula", "app", "agreement")]["action"] == "delete"
    assert got[("review_attachment", "1.2.0", "demo.mov")]["action"] == "upload"


def test_custom_eula_for_all_territories():
    state = live_state(eula={"id": "eu", "text": "Terms", "territories": {"FRA"}})
    _, plan = _plan(state, _desired(eula={"text": "Terms", "territories": "all"}))
    got = _fields(plan)
    assert got[("eula", "app", "territories")]["desired"] == ["DEU", "FRA", "USA"]
    assert ("eula", "app", "text") not in got


def test_pricing_and_availability_appear_in_the_plan():
    desired = _desired(pricing={"price": "0.99", "base_territory": "USA"},
                       availability={"territories": ["FRA", "USA"],
                                     "available_in_new_territories": False})
    _, plan = _plan(live_state(), desired)
    got = _fields(plan)
    assert got[("pricing", "USA", "pricePoint")]["desired"] == "pp-0.99"
    assert got[("availability", "app", "territories")]["desired"] == ["FRA", "USA"]
    assert got[("availability", "app", "availableInNewTerritories")]["desired"] is False


def test_apply_writes_each_family_then_a_replan_is_empty():
    desired = _desired(
        app={"contentRightsDeclaration": "USES_THIRD_PARTY_CONTENT"},
        categories={"secondaryCategory": "EDUCATION"},
        app_info_localizations={"fr-FR": {"subtitle": "Chat et vocaux"},
                                "it": {"name": "Acme"}},
        version={"copyright": "2026 Acme"},
        version_localizations={"fr-FR": {"promotionalText": "Nouveau"}},
        review={"notes": "Tap chat."},
        age_rating={"socialMedia": True})
    state = live_state()
    managers, plan = _plan(state, desired)
    result = apply_plan(managers, "APP", plan)
    assert result["ok"] is True
    kinds = [w[0] for w in managers.writes]
    assert kinds == ["update_app", "update_categories", "update_app_info_localization",
                     "create_app_info_localization", "update_age_rating", "update_version",
                     "upsert_version_localization", "save_review_detail"]
    _, replan = _plan(state, desired)
    assert replan["changes"] == []


def test_apply_creates_review_detail_then_uploads_attachments(tmp_path):
    path = tmp_path / "demo.mov"
    path.write_bytes(b"x")
    managers, plan = _plan(live_state(review=None),
                           _desired(review={"contactFirstName": "Ada"},
                                    review_attachments=[str(path)]))
    apply_plan(managers, "APP", plan)
    assert managers.writes[0][:2] == ("save_review_detail", None)
    assert managers.writes[1] == ("upload_review_attachment", "rd", str(path))


def test_apply_publishes_accessibility_with_the_full_family_declaration():
    state = live_state(accessibility=[
        {"id": "d1", "attributes": {"deviceFamily": "IPHONE", "state": "DRAFT",
                                    "supportsVoiceover": None}}])
    desired = _desired(accessibility={"IPHONE": {"supportsVoiceover": True,
                                                 "supportsDarkInterface": True}})
    managers, plan = _plan(state, desired)
    apply_plan(managers, "APP", plan)
    assert managers.writes == [("declare_accessibility", "IPHONE", "d1",
                                {"supportsVoiceover": True, "supportsDarkInterface": True})]


def test_apply_one_failing_family_does_not_stop_the_others():
    desired = _desired(app={"accessibilityUrl": "https://acme.io/a11y"},
                       version={"copyright": "2026 Acme"})
    managers, plan = _plan(live_state(), desired)

    def boom(*a, **k):
        raise RuntimeError("409 conflict")
    managers.listing.update_app = boom
    result = apply_plan(managers, "APP", plan)
    assert result["ok"] is False
    assert result["families"]["app"]["ok"] is False
    assert result["families"]["version"]["ok"] is True
