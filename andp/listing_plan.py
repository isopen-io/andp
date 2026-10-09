"""Plan and apply the App Store listing: read live state, diff, write the diff.

`build_plan` only reads (GET) and returns one entry per field that would
change — family, scope (app / locale / version / device family), field, current
value, desired value, action. `apply_plan` writes exactly those entries, family
by family, best effort: a failing family is reported and the others still run;
a re-plan after a successful apply is empty.

Secrets (review contact and demo account) are compared but never shown:
`public_changes` masks them for any output.
"""
import datetime

from . import listing_spec as spec
from .asc.appstore import EDITABLE_VERSION_STATES, version_state

_FIELDS = {f.api: f for f in (
    spec.APP_FIELDS + spec.CATEGORY_FIELDS + spec.APP_INFO_LOCALIZATION_FIELDS
    + spec.VERSION_FIELDS + spec.VERSION_LOCALIZATION_FIELDS + spec.REVIEW_FIELDS
    + spec.ACCESSIBILITY_FIELDS + spec.ENCRYPTION_FIELDS)}
_SECRET = {api for api, f in _FIELDS.items() if f.secret}
_DEAD_ENCRYPTION_STATES = {"REJECTED", "INVALID", "EXPIRED"}
# Editable at any time, even on a version that is live or in review.
_ALWAYS_EDITABLE = {("version_localization", "promotionalText")}

FAMILY_ORDER = (
    "app", "categories", "app_info_localization", "age_rating", "version",
    "phased_release", "version_localization", "review", "review_attachment",
    "accessibility", "encryption", "eula", "pricing", "availability",
)


def _instant(value):
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _same(api, current, desired):
    field = _FIELDS.get(api)
    if field is not None and field.kind == spec.DATETIME:
        return current is not None and _instant(current) == _instant(desired)
    if isinstance(desired, str):
        return (spec.normalize_text(current) or "") == desired
    return current == desired


def _change(family, scope, field, current, desired, action, locked=False):
    return {"family": family, "scope": scope, "field": field, "current": current,
            "desired": desired, "action": action, "locked": locked,
            "secret": field in _SECRET}


class _Plan:
    def __init__(self):
        self.changes, self.unchanged = [], 0
        self.errors, self.warnings, self.notes = [], [], []

    def compare(self, family, scope, desired, current, action="update", locked=False):
        for api, value in desired.items():
            now = (current or {}).get(api)
            if current is not None and _same(api, now, value):
                self.unchanged += 1
                continue
            is_locked = locked and (family, api) not in _ALWAYS_EDITABLE
            self.changes.append(_change(family, scope, api, now, value,
                                        action if current is not None else "create",
                                        is_locked))


# -- reads ----------------------------------------------------------------------------

def _pick_version(managers, app_id, version, platform, notes):
    if version:
        found = managers.appstore.find_version(app_id, version, platform)
        if found is None:
            notes.append(f"version {version} ({platform}) not found — version fields skipped")
        return found
    for candidate in managers.appstore.list_versions(app_id, platform):
        if version_state(candidate) in EDITABLE_VERSION_STATES:
            return candidate
    notes.append(f"no editable {platform} version — version fields skipped "
                 "(create one with `andp version set`)")
    return None


def _version_view(resource):
    attrs = resource.get("attributes") or {}
    state = version_state(resource)
    return {"id": resource["id"], "version": attrs.get("versionString"), "state": state,
            "editable": state in EDITABLE_VERSION_STATES}


def _attrs(resource):
    return dict((resource or {}).get("attributes") or {})


# -- families -------------------------------------------------------------------------

def _plan_app_info(plan, managers, app_id, desired, ctx):
    wants = (desired["categories"] or desired["app_info_localizations"]
             or desired.get("age_rating"))
    if not wants:
        return
    info, editable = managers.listing.editable_app_info(app_id)
    if info is None:
        plan.errors.append("the app has no appInfo record")
        return
    ctx["app_info_id"] = info["id"]
    locked = not editable
    if locked:
        plan.notes.append("no editable appInfo (categories, names, age rating lock "
                          "until a new version is created)")
    if desired["categories"]:
        plan.compare("categories", "app", desired["categories"],
                     managers.listing.categories(info["id"]), locked=locked)
    if desired["app_info_localizations"]:
        live = managers.listing.app_info_localizations(info["id"])
        ctx["app_info_localizations"] = {loc: r["id"] for loc, r in live.items()}
        for locale, wanted in sorted(desired["app_info_localizations"].items()):
            if locale not in live and "name" not in wanted:
                plan.errors.append(f"app_info_localization {locale}: a new language needs a name")
                continue
            plan.compare("app_info_localization", locale, wanted,
                         _attrs(live[locale]) if locale in live else None, locked=locked)
    if desired.get("age_rating"):
        declaration = managers.age_rating.get_declaration(app_id)
        if declaration is None:
            plan.errors.append("no age rating declaration found")
        else:
            ctx["age_rating_id"] = declaration["id"]
            plan.compare("age_rating", "app", desired["age_rating"], _attrs(declaration),
                         locked=locked)
        ctx["read_only"]["territory_age_ratings"] = \
            managers.listing.territory_age_ratings(info["id"])


def _plan_version(plan, managers, app_id, desired, version_res):
    view = _version_view(version_res)
    scope, locked = view["version"], not view["editable"]
    if desired["version"]:
        plan.compare("version", scope, desired["version"], _attrs(version_res), locked=locked)
    if desired["phased_release"] is not None:
        live = managers.listing.phased_release(view["id"])
        state = _attrs(live).get("phasedReleaseState")
        if desired["phased_release"] and live is None:
            plan.changes.append(_change("phased_release", scope, "phasedRelease", False, True,
                                        "create", locked))
        elif not desired["phased_release"] and live is not None:
            if state == "INACTIVE":
                plan.changes.append(_change("phased_release", scope, "phasedRelease", True,
                                            False, "delete", locked))
            else:
                plan.notes.append(f"phased release is {state}: it cannot be removed")
        else:
            plan.unchanged += 1
    if desired["version_localizations"]:
        live = {(_attrs(r)).get("locale"): _attrs(r)
                for r in managers.appstore.list_version_localizations(view["id"])}
        for locale, wanted in sorted(desired["version_localizations"].items()):
            plan.compare("version_localization", locale, wanted, live.get(locale),
                         locked=locked)
    review = None
    if desired["review"] or desired["review_attachments"]:
        review = managers.listing.review_detail(view["id"])
    if desired["review"]:
        plan.compare("review", scope, desired["review"],
                     _attrs(review) if review else None)
    if desired["review_attachments"]:
        names = managers.listing.review_attachment_names(review["id"]) if review else set()
        for path in desired["review_attachments"]:
            name = path.replace("\\", "/").rsplit("/", 1)[-1]
            if name in names:
                plan.unchanged += 1
            else:
                plan.changes.append(_change("review_attachment", scope, name, None, path,
                                            "upload"))
    return view, (review or {}).get("id")


def _plan_accessibility(plan, managers, app_id, desired, ctx):
    if not desired["accessibility"]:
        return
    published, drafts = {}, {}
    for record in managers.listing.accessibility_declarations(app_id):
        attrs = _attrs(record)
        family = attrs.get("deviceFamily")
        if attrs.get("state") == "PUBLISHED":
            published[family] = attrs
        elif attrs.get("state") == "DRAFT":
            drafts[family] = record["id"]
    ctx["accessibility"] = {"published": published, "drafts": drafts}
    for family, wanted in sorted(desired["accessibility"].items()):
        current = published.get(family)
        before = len(plan.changes)
        plan.compare("accessibility", family, wanted, current)
        if current is None and family in drafts:
            for change in plan.changes[before:]:
                change["action"] = "update"


def _plan_encryption(plan, managers, app_id, desired):
    wanted = desired["encryption"]
    if not wanted:
        return
    for record in managers.listing.encryption_declarations(app_id):
        attrs = _attrs(record)
        if attrs.get("appEncryptionDeclarationState") in _DEAD_ENCRYPTION_STATES:
            continue
        if all(_same(k, attrs.get(k), v) for k, v in wanted.items()):
            plan.unchanged += len(wanted)
            return
    for api, value in wanted.items():
        plan.changes.append(_change("encryption", "app", api, None, value, "create"))


def _plan_eula(plan, managers, app_id, desired, ctx):
    wanted = desired["eula"]
    if not wanted:
        return
    live = managers.listing.eula(app_id)
    ctx["eula_id"] = live and live["id"]
    if wanted.get("standard"):
        if live is None:
            plan.unchanged += 1
        else:
            plan.changes.append(_change("eula", "app", "agreement", "custom", "standard",
                                        "delete"))
        return
    territories = wanted["territories"]
    if territories == "all":
        territories = sorted(managers.availability.list_all_territories())
    ctx["eula_territories"] = territories
    current = None if live is None else {"text": live["text"],
                                         "territories": sorted(live["territories"])}
    plan.compare("eula", "app", {"text": wanted["text"], "territories": territories}, current)


def _plan_store(plan, managers, app_id, desired, ctx):
    pricing = desired.get("pricing")
    if pricing:
        from .service import _is_free
        base = pricing.get("base_territory") or "USA"
        point_id = pricing.get("price_point_id")
        if point_id is None:
            point = (managers.pricing.find_free_price_point(app_id, base)
                     if _is_free(pricing.get("price"))
                     else managers.pricing.find_price_point(app_id, base, pricing.get("price")))
            point_id = point and point["id"]
        if point_id is None:
            plan.errors.append(f"pricing: no price point for {pricing.get('price')!r} in {base}")
        else:
            current = managers.pricing.current_base_price_point_id(app_id, base)
            if current == point_id:
                plan.unchanged += 1
            else:
                change = _change("pricing", base, "pricePoint", current, point_id, "update")
                change["price"] = pricing.get("price")
                plan.changes.append(change)
    availability = desired.get("availability")
    if availability and availability.get("territories") is not None:
        snapshot = managers.availability.availability_snapshot(app_id) or {
            "territories": set(), "available_in_new_territories": None}
        territories = availability["territories"]
        target = (managers.availability.list_all_territories()
                  if str(territories).strip().lower() in ("all", "['all']")
                  else {str(t).strip().upper() for t in territories})
        plan.compare("availability", "app", {"territories": sorted(target)},
                     {"territories": sorted(snapshot["territories"])})
        new = availability.get("available_in_new_territories")
        if new is not None:
            plan.compare("availability", "app", {"availableInNewTerritories": bool(new)},
                         {"availableInNewTerritories":
                          snapshot["available_in_new_territories"]})


def build_plan(managers, app_id, desired, version=None):
    """Read-only. Returns the plan; nothing is written."""
    plan = _Plan()
    plan.errors.extend(desired.get("errors") or [])
    plan.warnings.extend(desired.get("warnings") or [])
    ctx = {"read_only": {}}
    platform = desired.get("platform") or "IOS"

    if desired["app"]:
        app = managers.listing.app(app_id)
        attrs = _attrs(app)
        ctx["read_only"]["isOrEverWasMadeForKids"] = attrs.get("isOrEverWasMadeForKids")
        plan.compare("app", "app", desired["app"], attrs)
    _plan_app_info(plan, managers, app_id, desired, ctx)

    version_view, review_id = None, None
    wants_version = (desired["version"] or desired["version_localizations"]
                     or desired["review"] or desired["review_attachments"]
                     or desired["phased_release"] is not None)
    if wants_version:
        version_res = _pick_version(managers, app_id, version, platform, plan.notes)
        if version_res is not None:
            version_view, review_id = _plan_version(plan, managers, app_id, desired,
                                                    version_res)
    _plan_accessibility(plan, managers, app_id, desired, ctx)
    _plan_encryption(plan, managers, app_id, desired)
    _plan_eula(plan, managers, app_id, desired, ctx)
    _plan_store(plan, managers, app_id, desired, ctx)

    rank = {name: i for i, name in enumerate(FAMILY_ORDER)}
    plan.changes.sort(key=lambda c: rank.get(c["family"], len(rank)))
    ctx["review_id"] = review_id
    return {"version": version_view, "changes": plan.changes, "unchanged": plan.unchanged,
            "errors": plan.errors, "warnings": plan.warnings, "notes": plan.notes,
            "read_only": ctx.pop("read_only"), "_context": {**ctx, "desired": desired}}


def public_changes(changes):
    """The printable form: secrets replaced by a presence marker."""
    shown = []
    for change in changes:
        view = {k: v for k, v in change.items() if k != "secret"}
        if change.get("secret"):
            view["current"] = "<set>" if change["current"] else "<unset>"
            view["desired"] = "<new value>"
        shown.append(view)
    return shown


# -- apply ----------------------------------------------------------------------------

def _by_family(changes):
    groups = {}
    for change in changes:
        groups.setdefault(change["family"], []).append(change)
    return groups


def _values(changes):
    return {c["field"]: c["desired"] for c in changes}


def _scopes(changes):
    scopes = {}
    for change in changes:
        scopes.setdefault(change["scope"], []).append(change)
    return scopes


def _write_family(name, changes, managers, app_id, plan):
    ctx, desired = plan["_context"], plan["_context"]["desired"]
    version_id = (plan.get("version") or {}).get("id")
    listing = managers.listing
    writes = 0
    if name == "app":
        listing.update_app(app_id, _values(changes))
        return 1
    if name == "categories":
        listing.update_categories(ctx["app_info_id"], _values(changes))
        return 1
    if name == "app_info_localization":
        ids = ctx.get("app_info_localizations", {})
        for locale, group in _scopes(changes).items():
            if locale in ids:
                listing.update_app_info_localization(ids[locale], _values(group))
            else:
                listing.create_app_info_localization(
                    ctx["app_info_id"], locale, desired["app_info_localizations"][locale])
            writes += 1
        return writes
    if name == "age_rating":
        managers.age_rating.update_declaration(ctx["age_rating_id"], _values(changes))
        return 1
    if name == "version":
        listing.update_version(version_id, _values(changes))
        return 1
    if name == "phased_release":
        if changes[0]["action"] == "create":
            listing.create_phased_release(version_id)
        else:
            listing.delete_phased_release(listing.phased_release(version_id)["id"])
        return 1
    if name == "version_localization":
        for locale, group in _scopes(changes).items():
            values = (desired["version_localizations"][locale]
                      if group[0]["action"] == "create" else _values(group))
            managers.appstore.upsert_version_localization(version_id, locale, values)
            writes += 1
        return writes
    if name == "review":
        review_id = ctx.get("review_id")
        values = desired["review"] if review_id is None else _values(changes)
        saved = listing.save_review_detail(version_id, review_id, values)
        ctx["review_id"] = (saved or {}).get("id") or review_id
        return 1
    if name == "review_attachment":
        review_id = ctx.get("review_id")
        if review_id is None:
            saved = listing.save_review_detail(version_id, None, {})
            review_id = ctx["review_id"] = saved["id"]
            writes += 1
        for change in changes:
            listing.upload_review_attachment(review_id, change["desired"])
            writes += 1
        return writes
    if name == "accessibility":
        state = ctx.get("accessibility", {"published": {}, "drafts": {}})
        for family in _scopes(changes):
            published = {k: v for k, v in state["published"].get(family, {}).items()
                         if k.startswith("supports") and v is not None}
            values = {**published, **desired["accessibility"][family]}
            listing.declare_accessibility(app_id, family, state["drafts"].get(family), values)
            writes += 1
        return writes
    if name == "encryption":
        created = listing.create_encryption_declaration(app_id, desired["encryption"])
        writes = 1
        if desired.get("encryption_document"):
            listing.upload_encryption_document(created["id"], desired["encryption_document"])
            writes += 1
        return writes
    if name == "eula":
        if changes[0]["action"] == "delete":
            listing.delete_eula(ctx["eula_id"])
        else:
            listing.save_eula(app_id, ctx.get("eula_id"), desired["eula"]["text"],
                              ctx["eula_territories"])
        return 1
    return 0


def apply_plan(managers, app_id, plan, families=None):
    """Write the plan's changes. Refuses a plan carrying validation errors.

    `families` restricts the write to those families (pricing and availability
    are reconciled by their own service functions, never here)."""
    if plan["errors"]:
        return {"ok": False, "families": {},
                "error": "the plan has validation errors; nothing was written"}
    results, ok = {}, True
    for name, changes in _by_family(plan["changes"]).items():
        if name in ("pricing", "availability") or (families and name not in families):
            continue
        writable = [c for c in changes if not c["locked"]]
        locked = [c for c in changes if c["locked"]]
        result = {"ok": True, "writes": 0}
        try:
            if writable:
                result["writes"] = _write_family(name, writable, managers, app_id, plan)
        except Exception as exc:  # one family never aborts the others
            result = {"ok": False, "writes": 0, "error": str(exc)}
        if locked:
            result["ok"] = False
            result["locked"] = sorted({c["field"] for c in locked})
            result.setdefault("error", "the record is not editable in its current state")
        results[name] = result
        ok = ok and result["ok"]
    return {"ok": ok, "families": results}
