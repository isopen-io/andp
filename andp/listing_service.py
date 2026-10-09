"""`store plan` and the listing part of `store apply` — library-first.

Same contract as the rest of the service layer: pure functions returning an
envelope, never raising, dry-run aware. Without credentials the plan still
validates every field offline (limits, values, cross-field rules, files).
"""
from . import service
from .errors import AndpError
from .listing_plan import apply_plan, build_plan, public_changes
from .listing_source import load_desired

LISTING_SECTIONS = ("app", "categories", "localizations", "version", "review",
                    "accessibility", "encryption", "eula", "metadata_dir")
# Reconciled by their own service functions inside `store apply`.
_SEPARATELY_APPLIED = ("age_rating", "pricing", "availability")


def has_listing(store, metadata_dir=None):
    return bool(metadata_dir) or any(store.get(name) for name in LISTING_SECTIONS)


def _desired(store, project_root, metadata_dir):
    from .asc.agerating import validate_declaration
    desired = load_desired(store, project_root, metadata_dir=metadata_dir)
    desired["age_rating"] = None
    if store.get("age_rating"):
        try:
            config = service._resolve_age_rating_config(store["age_rating"], project_root)
        except (OSError, ValueError) as err:
            desired["errors"].append(f"store.age_rating: {err}")
            config = {}
        attrs, errors, warnings = validate_declaration(config)
        desired["age_rating"] = attrs or None
        desired["errors"].extend(f"store.age_rating: {e}" for e in errors)
        desired["warnings"].extend(f"store.age_rating: {w}" for w in warnings)
    desired["pricing"] = store.get("pricing") or None
    desired["availability"] = store.get("availability") or None
    return desired


def _summary(desired):
    """How many fields each family declares — the offline view of the plan."""
    def count(mapping):
        return sum(len(v) for v in mapping.values())
    return {
        "app": len(desired["app"]),
        "categories": len(desired["categories"]),
        "app_info_localizations": len(desired["app_info_localizations"]),
        "app_info_fields": count(desired["app_info_localizations"]),
        "version": len(desired["version"]) + (desired["phased_release"] is not None),
        "version_localizations": len(desired["version_localizations"]),
        "version_localization_fields": count(desired["version_localizations"]),
        "review": len(desired["review"]),
        "review_attachments": len(desired["review_attachments"]),
        "accessibility": sorted(desired["accessibility"]),
        "encryption": bool(desired["encryption"]),
        "eula": ("standard" if (desired["eula"] or {}).get("standard")
                 else "custom" if desired["eula"] else None),
        "age_rating": len(desired["age_rating"] or {}),
        "pricing": bool(desired["pricing"]),
        "availability": bool(desired["availability"]),
    }


def _prepare(command, bundle_id, account, metadata_dir, project_root):
    """(store, desired, managers, app_id, dry_run) or an error envelope."""
    try:
        store = service._read_store(project_root)
        managers, _cfg, dry_run = service._managers_for(account)
    except AndpError as err:
        return service._error_result(command, err)
    desired = _desired(store, project_root, metadata_dir)
    if dry_run:
        return store, desired, None, None, True
    app = managers.apps.find_app(bundle_id)
    if app is None:
        return service._app_not_found(command, bundle_id)
    return store, desired, managers, app["id"], False


def _wrap(command, run):
    from .asc.client import ASCAPIError
    from .errors import from_asc_error, from_unexpected
    try:
        return run()
    except AndpError as err:
        return service._error_result(command, err)
    except ASCAPIError as err:
        return service._error_result(command, from_asc_error(err))
    except Exception as err:
        return service._error_result(command, from_unexpected(err))


def store_plan(bundle_id, account="primary", version=None, metadata_dir=None,
               project_root="."):
    """Read-only diff between andp.yml/metadata and App Store Connect."""
    def run():
        prepared = _prepare("store_plan", bundle_id, account, metadata_dir, project_root)
        if isinstance(prepared, dict):
            return prepared
        _store, desired, managers, app_id, dry_run = prepared
        if dry_run:
            return {"command": "store_plan", "ok": not desired["errors"], "dry_run": True,
                    "written": False, "desired": _summary(desired),
                    "errors": desired["errors"], "warnings": desired["warnings"]}
        plan = build_plan(managers, app_id, desired, version=version)
        return {"command": "store_plan", "ok": not plan["errors"], "dry_run": False,
                "written": False, "bundle_id": bundle_id, "version": plan["version"],
                "changes": public_changes(plan["changes"]), "unchanged": plan["unchanged"],
                "errors": plan["errors"], "warnings": plan["warnings"],
                "notes": plan["notes"], "read_only": plan["read_only"]}
    return _wrap("store_plan", run)


def apply_listing(bundle_id, account="primary", version=None, metadata_dir=None,
                  project_root="."):
    """Write the listing diff (everything but age rating, price, territories)."""
    def run():
        prepared = _prepare("apply_listing", bundle_id, account, metadata_dir, project_root)
        if isinstance(prepared, dict):
            return prepared
        _store, desired, managers, app_id, dry_run = prepared
        if dry_run:
            return {"command": "apply_listing", "ok": not desired["errors"], "dry_run": True,
                    "changed": None, "desired": _summary(desired),
                    "errors": desired["errors"], "warnings": desired["warnings"]}
        listing_only = dict(desired, age_rating=None, pricing=None, availability=None)
        plan = build_plan(managers, app_id, listing_only, version=version)
        result = apply_plan(managers, app_id, plan)
        envelope = {"command": "apply_listing", "ok": result["ok"], "dry_run": False,
                    "changed": any(f.get("writes") for f in result["families"].values()),
                    "version": plan["version"], "families": result["families"],
                    "errors": plan["errors"], "warnings": plan["warnings"],
                    "notes": plan["notes"]}
        if result.get("error"):
            envelope["error"] = {"code": "invalid_listing", "message": result["error"],
                                 "retryable": False,
                                 "remediation": "Run `andp store plan` and fix the errors."}
        return envelope
    return _wrap("apply_listing", run)
