"""Read-only pre-submission validation (deliver-`precheck` parity).

Catches the problems Apple rejects *before* the irreversible submit. It never
mutates. Errors are strictly the hard, reliably-detectable requirements;
everything else is a warning. `ok:true` is not a guarantee of acceptance —
age rating, app name/subtitle, pricing and per-device screenshot sizes are not
checked, and Apple stays the final authority at submit.
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
        "note": ("ok does not guarantee acceptance: age rating, app name/subtitle, "
                 "pricing, and per-device screenshot sizes are not checked."),
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

    checks.extend(_store_checks(managers, app_id))
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
    checks = []
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
        if _age_rating_unset(managers.age_rating.get_declaration(app_id)):
            checks.append({"id": "age_rating", "level": "warning",
                           "message": "Age rating declaration appears unset/incomplete."})
    except Exception:
        pass
    return checks
