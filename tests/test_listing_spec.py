"""The listing field registry: limits, kinds and cross-field rules (pure)."""
import datetime

from andp import listing_spec as spec


def test_name_and_subtitle_are_capped_at_thirty_characters():
    attrs, errors, _ = spec.pick(spec.APP_INFO_LOCALIZATION_FIELDS,
                                 {"name": "x" * 30, "subtitle": "y" * 31})
    assert attrs == {"name": "x" * 30}
    assert errors == ["subtitle: 31 characters, the App Store allows 30"]


def test_version_text_limits_follow_app_store_connect():
    limits = {f.api: f.max_len for f in spec.VERSION_LOCALIZATION_FIELDS}
    assert limits["promotionalText"] == 170
    assert limits["description"] == 4000 and limits["whatsNew"] == 4000


def test_deliver_and_api_keys_set_the_same_field():
    attrs, errors, _ = spec.pick(spec.VERSION_LOCALIZATION_FIELDS,
                                 {"release_notes": "Fixes", "support_url": "https://x.io/help"})
    assert errors == []
    assert attrs == {"whatsNew": "Fixes", "supportUrl": "https://x.io/help"}


def test_two_keys_disagreeing_on_one_field_is_an_error():
    _, errors, _ = spec.pick(spec.VERSION_LOCALIZATION_FIELDS,
                             {"whatsNew": "A", "release_notes": "B"})
    assert errors == ["whatsNew is set twice with different values"]


def test_unknown_key_is_rejected_as_a_typo():
    _, errors, _ = spec.pick(spec.APP_FIELDS, {"content_right": "X"}, where="store.app")
    assert errors == ["store.app: unknown field 'content_right'"]


def test_enum_url_and_bool_are_validated():
    attrs, errors, _ = spec.pick(spec.APP_FIELDS, {
        "content_rights": "USES_THIRD_PARTY_CONTENT",
        "accessibility_url": "meeshy.me/a11y",
        "streamlined_purchasing": "yes"})
    assert attrs == {"contentRightsDeclaration": "USES_THIRD_PARTY_CONTENT",
                     "streamlinedPurchasingEnabled": True}
    assert errors == ["accessibilityUrl: expected an http(s) URL, got 'meeshy.me/a11y'"]
    _, errors, _ = spec.pick(spec.APP_FIELDS, {"content_rights": "MAYBE"})
    assert "contentRightsDeclaration" in errors[0]


def test_deprecated_field_passes_with_a_warning():
    attrs, errors, warnings = spec.pick(spec.VERSION_FIELDS, {"uses_idfa": False})
    assert errors == [] and attrs == {"usesIdfa": False}
    assert warnings and "usesIdfa" in warnings[0]


def test_crlf_and_outer_whitespace_are_normalized():
    attrs, _, _ = spec.pick(spec.VERSION_FIELDS, {"copyright": "  2026 Acme\r\n"})
    assert attrs == {"copyright": "2026 Acme"}


def test_scheduled_release_needs_a_future_date():
    now = datetime.datetime(2026, 10, 9, tzinfo=datetime.timezone.utc)
    assert spec.version_rules({"releaseType": "SCHEDULED"}, now=now) == [
        "earliestReleaseDate is required when releaseType is SCHEDULED"]
    assert spec.version_rules({"releaseType": "SCHEDULED",
                               "earliestReleaseDate": "2026-11-01T08:00:00Z"}, now=now) == []
    assert "in the past" in spec.version_rules(
        {"releaseType": "SCHEDULED", "earliestReleaseDate": "2026-01-01T08:00:00Z"},
        now=now)[0]
    assert spec.version_rules({"releaseType": "MANUAL",
                               "earliestReleaseDate": "2026-11-01T08:00:00Z"}, now=now)


def test_release_date_without_time_zone_is_refused():
    _, errors, _ = spec.pick(spec.VERSION_FIELDS, {"earliest_release_date": "2026-11-01"})
    assert errors and "ISO 8601" in errors[0]


def test_demo_account_required_needs_its_credentials():
    assert spec.review_rules({"demoAccountRequired": True, "demoAccountName": "u"}) == [
        "demoAccountPassword is required when demoAccountRequired is true"]
    assert spec.review_rules({"demoAccountRequired": False}) == []


def test_review_contact_and_demo_credentials_are_never_printed():
    secret = {f.api for f in spec.REVIEW_FIELDS if f.secret}
    assert secret == {"contactPhone", "contactEmail", "demoAccountName", "demoAccountPassword"}


def test_categories_are_checked_against_the_known_list_and_their_parent():
    assert spec.category_warnings({"primaryCategory": "SOCIAL_NETWORKING",
                                   "secondaryCategory": "EDUCATION"}) == []
    assert spec.category_warnings({"primaryCategory": "GAMES",
                                   "primarySubcategoryOne": "GAMES_PUZZLE"}) == []
    warns = spec.category_warnings({"primaryCategory": "EDUCATION",
                                    "primarySubcategoryOne": "GAMES_PUZZLE"})
    assert warns and "only GAMES and STICKERS" in warns[0]
    assert spec.category_warnings({"primaryCategory": "SOCIAL"})


def test_keywords_are_counted_in_characters_as_the_api_does():
    # The Help page says "100 bytes", the API disagrees — observed 2026-10-09 on
    # me.meeshy.app: live de-DE keywords of 100 characters / 101 UTF-8 bytes and
    # ar-SA keywords of 70 characters / 129 bytes, both accepted. The observed
    # contract wins: 100 characters.
    ok, errors, _ = spec.pick(spec.VERSION_LOCALIZATION_FIELDS, {"keywords": "ü" * 100})
    assert errors == [] and ok["keywords"] == "ü" * 100
    _, errors, _ = spec.pick(spec.VERSION_LOCALIZATION_FIELDS, {"keywords": "k" * 101})
    assert errors == ["keywords: 101 characters, the App Store allows 100"]


def test_review_notes_are_counted_in_bytes_too():
    _, errors, _ = spec.pick(spec.REVIEW_FIELDS, {"notes": "à" * 2001})
    assert errors == ["notes: 4002 bytes, the App Store allows 4000"]


def test_review_phone_must_be_international():
    assert spec.review_rules({"contactPhone": "+33 6 12 34 56 78"}) == []
    assert spec.review_rules({"contactPhone": "06 12 34 56 78"}) == [
        "contactPhone must be in international format, starting with +"]
