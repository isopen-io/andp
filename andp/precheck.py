"""Read-only pre-submission validation (deliver-`precheck` parity).

Catches the problems Apple rejects *before* the irreversible submit. It never
mutates. Errors are strictly the hard, reliably-detectable requirements;
everything else is a warning. The listing fields App Review requires (content
rights, primary category, app name and privacy policy per language, copyright,
App Review contact and demo account, every age rating answer, Apple's length
limits) are errors too — `definition_checks`. `ok:true` is still not a
guarantee: App Privacy, the EU trader status and per-device screenshot sizes
are not readable through the API, and Apple stays the final authority.
"""
import re

from .asc.appstore import EDITABLE_VERSION_STATES, version_state

_CROSS_PLATFORM = re.compile(r"\b(android|google play|play store)\b", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"\b(lorem ipsum|todo|fixme|sample text|placeholder)\b", re.IGNORECASE)


def _content_warnings(text):
    warnings = []
    if not text:
        return warnings
    if _CROSS_PLATFORM.search(text):
        warnings.append({"id": "cross_platform_mention", "level": "warning",
                         "message": "Text mentions another platform (Android / Play Store) — "
                                    "a common App Review rejection."})
    if _PLACEHOLDER.search(text):
        warnings.append({"id": "placeholder_text", "level": "warning",
                         "message": "Text looks like a placeholder (lorem ipsum / TODO / …)."})
    return warnings


def _summary(checks):
    errors = sum(1 for c in checks if c["level"] == "error")
    warnings = sum(1 for c in checks if c["level"] == "warning")
    return {
        "ok": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "note": ("ok does not guarantee acceptance: App Privacy answers, the EU trader "
                 "status and per-device screenshot sizes are not readable through the "
                 "API and are not checked."),
    }


def run_precheck(managers, app_id, version_id):
    """Validate the version for submission. Returns a structured report."""
    appstore = managers.appstore
    checks = []

    version = appstore.get_version(version_id)
    state = version_state(version or {})
    if state not in EDITABLE_VERSION_STATES:
        checks.append({"id": "version_editable", "level": "error",
                       "message": f"Version is in state {state!r}; not editable/submittable."})

    if appstore.get_version_build(version_id) is None:
        checks.append({"id": "build_attached", "level": "error",
                       "message": "No build is attached to this version."})

    localizations = appstore.list_version_localizations(version_id)
    if not localizations:
        checks.append({"id": "localizations", "level": "error",
                       "message": "The version has no localizations."})

    for loc in localizations:
        attrs = loc.get("attributes", {}) or {}
        locale = attrs.get("locale", "?")

        if not (attrs.get("description") or "").strip():
            checks.append({"id": "description", "level": "error",
                           "message": f"[{locale}] description is empty."})
        # whatsNew: "" (settable, an update) warns; null (first version) does not.
        if attrs.get("whatsNew") == "":
            checks.append({"id": "whatsNew", "level": "warning",
                           "message": f"[{locale}] 'What's New' is empty."})
        if not (attrs.get("keywords") or "").strip():
            checks.append({"id": "keywords", "level": "warning",
                           "message": f"[{locale}] keywords are empty."})
        if not (attrs.get("supportUrl") or "").strip():
            checks.append({"id": "supportUrl", "level": "warning",
                           "message": f"[{locale}] support URL is empty."})

        # Screenshots: count actual appScreenshots (a set can exist empty).
        total = 0
        for sset in appstore.localization_screenshot_sets(loc["id"]):
            total += managers.screenshots.count_screenshots(sset["id"])
        if total == 0:
            checks.append({"id": "screenshots", "level": "error",
                           "message": f"[{locale}] has no screenshots."})

        # Content rules on the reviewer-visible text.
        text = " ".join(filter(None, [
            attrs.get("description"), attrs.get("whatsNew"),
            attrs.get("promotionalText"), attrs.get("keywords")]))
        for w in _content_warnings(text):
            checks.append({**w, "message": f"[{locale}] {w['message']}"})

    store_checks, declaration = _store_checks(managers, app_id)
    checks.extend(store_checks)
    checks.extend(definition_checks(
        managers, app_id, version or {"id": version_id},
        [loc.get("attributes", {}) or {} for loc in localizations], declaration))
    return _summary(checks)


def _age_rating_unset(declaration):
    """True if no age rating declaration exists, or every content descriptor is
    still unanswered (null) — the real submission blocker, vs. mere existence."""
    if not declaration:
        return True
    from .asc.agerating import TERNARY_FIELDS
    attrs = declaration.get("attributes", {}) or {}
    return all(attrs.get(field) is None for field in TERNARY_FIELDS)


def _store_checks(managers, app_id):
    """Advisory store-configuration checks (pricing / availability / age rating).

    Each is best-effort: an advisory read must never turn a precheck into a hard
    error, so a failed read simply skips that one check (the hard checks above
    still stand). All warnings — Apple stays the final authority at submit."""
    checks, declaration = [], None
    try:
        if managers.pricing.get_schedule(app_id) is None:
            checks.append({"id": "pricing", "level": "warning",
                           "message": "No price schedule set (Apple requires a price "
                                      "or Free selection before submission)."})
    except Exception:
        pass
    try:
        if not managers.availability.list_available_territories(app_id):
            checks.append({"id": "availability", "level": "warning",
                           "message": "App is available in zero territories."})
    except Exception:
        pass
    try:
        declaration = managers.age_rating.get_declaration(app_id)
        if _age_rating_unset(declaration):
            checks.append({"id": "age_rating", "level": "warning",
                           "message": "Age rating declaration appears unset/incomplete."})
    except Exception:
        pass
    return checks, declaration


def _error(id_, message):
    return {"id": id_, "level": "error", "message": message}


def _guarded(checks, run):
    """A failed read skips its own check, never the others (advisory read)."""
    try:
        checks.extend(run())
    except Exception:
        pass


def _app_checks(managers, app_id):
    attrs = (managers.listing.app(app_id) or {}).get("attributes") or {}
    if not attrs.get("contentRightsDeclaration"):
        return [_error("content_rights", "Content rights declaration is unanswered "
                       "(App Information → Content Rights).")]
    return []


def _app_info_checks(managers, app_id, locales):
    from .listing_spec import APP_INFO_LOCALIZATION_FIELDS, coerce
    checks = []
    info, _editable = managers.listing.editable_app_info(app_id)
    if info is None:
        return [_error("app_info", "The app has no appInfo record.")]
    if not managers.listing.categories(info["id"]).get("primaryCategory"):
        checks.append(_error("primary_category", "No primary category is set."))
    live = managers.listing.app_info_localizations(info["id"])
    for locale in locales:
        attrs = (live.get(locale) or {}).get("attributes") or {}
        if not (attrs.get("name") or "").strip():
            checks.append(_error("app_name", f"[{locale}] has no app name "
                                 "(appInfoLocalization missing or empty)."))
        if not (attrs.get("privacyPolicyUrl") or "").strip():
            checks.append(_error("privacy_policy_url",
                                 f"[{locale}] privacy policy URL is empty."))
    for locale, record in live.items():
        attrs = record.get("attributes") or {}
        for field in APP_INFO_LOCALIZATION_FIELDS:
            _value, problem = coerce(field, attrs.get(field.api))
            if problem and field.max_len:
                checks.append({"id": "field_length", "level": "error",
                               "message": f"[{locale}] {problem}"})
    return checks


def _version_checks(version, localizations):
    from .listing_spec import VERSION_LOCALIZATION_FIELDS, coerce
    checks = []
    attrs = version.get("attributes") or {}
    # The live API always returns these keys (null when unset); a key absent
    # from the response is a field this record does not carry — not a gap.
    if "copyright" in attrs and not (attrs.get("copyright") or "").strip():
        checks.append(_error("copyright", "The version has no copyright."))
    if attrs.get("releaseType") == "SCHEDULED" and not attrs.get("earliestReleaseDate"):
        checks.append(_error("release_date", "releaseType is SCHEDULED without "
                             "an earliestReleaseDate."))
    for loc in localizations:
        locale = loc.get("locale", "?")
        for field in VERSION_LOCALIZATION_FIELDS:
            if not (field.max_len or field.max_bytes):
                continue
            _value, problem = coerce(field, loc.get(field.api))
            if problem:
                checks.append({"id": "field_length", "level": "error",
                               "message": f"[{locale}] {problem}"})
    return checks


def _review_checks(managers, version_id):
    record = managers.listing.review_detail(version_id)
    if record is None:
        return [_error("review_contact", "No App Review information: contactFirstName, "
                       "contactLastName, contactPhone, contactEmail are required.")]
    attrs = record.get("attributes") or {}
    checks = []
    missing = [f for f in ("contactFirstName", "contactLastName", "contactPhone",
                           "contactEmail") if not (attrs.get(f) or "").strip()]
    if missing:
        checks.append(_error("review_contact",
                             f"App Review contact incomplete: {', '.join(missing)}."))
    phone = attrs.get("contactPhone") or ""
    if phone and not phone.startswith("+"):
        checks.append({"id": "review_phone", "level": "warning",
                       "message": "App Review phone should be international (+country code)."})
    if attrs.get("demoAccountRequired") and not (
            attrs.get("demoAccountName") and attrs.get("demoAccountPassword")):
        checks.append(_error("demo_account", "demoAccountRequired is true but the demo "
                             "account name or password is empty."))
    return checks


def _age_checks(declaration):
    from .asc.agerating import missing_answers
    if declaration is None:
        return []
    attrs = declaration.get("attributes") or {}
    # Only questions the API returned (always all of them, null when
    # unanswered) — an absent key is not asked of this app.
    missing = [f for f in missing_answers(attrs) if f in attrs]
    if missing:
        return [_error("age_rating_answers",
                       f"Age rating questions unanswered: {', '.join(missing)}.")]
    return []


def definition_checks(managers, app_id, version, localizations, declaration):
    """The listing fields App Review requires — errors, each read best-effort."""
    checks = []
    locales = [loc.get("locale") for loc in localizations if loc.get("locale")]
    _guarded(checks, lambda: _app_checks(managers, app_id))
    _guarded(checks, lambda: _app_info_checks(managers, app_id, locales))
    _guarded(checks, lambda: _version_checks(version, localizations))
    _guarded(checks, lambda: _review_checks(managers, version["id"]))
    _guarded(checks, lambda: _age_checks(declaration))
    return checks
