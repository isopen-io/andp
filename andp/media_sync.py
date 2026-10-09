"""Plan and apply the listing visuals through the App Asset Library.

`plan_media` only reads. Per locale × placement type × placement group it
compares the files of the metadata folder (in name order) with the placements
of the version localization:

- a file not placed yet → `upload` (new to the library) or `place` (the library
  already holds the same file name and size);
- placed files in the wrong order → one `reorder`;
- placements absent from the folder → kept and reported, or `remove` with prune.

`apply_media` writes exactly that. When the app has no Asset Library (the
lookup fails), the legacy appScreenshotSets / appPreviewSets path is planned
for the groups it can express; IPHONE_DUO and the creative assets exist only in
the Asset Library and are refused with a clear error.
"""
import os

from .asc.assetlibrary import media_type_of
from .media_spec import legacy_type_for

_DEAD = {"FAILED", "ARCHIVED", "REJECTED"}
_SCREENSHOT_LIKE = {"APP_SCREENSHOT", "IMESSAGE_APP_SCREENSHOT"}


def _category(placement_type, ref):
    accepted = ref["categories"].get(placement_type) or ["APP_SCREENSHOTS_AND_PREVIEWS"]
    return accepted[0]


def _change(scope, field, current, desired, action, locked):
    return {"family": "media", "scope": scope, "field": field, "current": current,
            "desired": desired, "action": action, "locked": locked, "secret": False}


def _scope(locale, placement_type, group):
    return f"{locale} · {placement_type} · {group}"


def _localization_ids(managers, version_id):
    return {(r.get("attributes") or {}).get("locale"): r["id"]
            for r in managers.appstore.list_version_localizations(version_id)}


def _library(managers, app_id):
    try:
        library_id = managers.asset_library.library_id(app_id)
    except Exception:
        return None
    return library_id or None


def plan_media(managers, app_id, version_id, tree, locked=False, prune=False,
               localizations=None):
    """Read-only. {backend, changes, unchanged, errors, notes, ctx}."""
    result = {"backend": None, "changes": [], "unchanged": 0, "errors": [], "notes": [],
              "ctx": {"localizations": {}, "library_id": None, "assets": {}, "prune": prune}}
    if not tree:
        return result
    ids = localizations if localizations is not None else _localization_ids(managers, version_id)
    library_id = _library(managers, app_id)
    result["backend"] = "asset_library" if library_id else "legacy"
    result["ctx"]["library_id"] = library_id
    if library_id:
        ref = managers.asset_library.ref_data()
        result["ctx"]["ref"] = ref
        library = {}
        for media_type in ("IMAGE", "VIDEO"):
            for asset in managers.asset_library.assets(library_id, media_type):
                if asset.get("state") not in _DEAD:
                    library[(asset["fileName"], asset["fileSize"])] = asset
        result["ctx"]["assets"] = library
    for locale, groups in sorted(tree.items()):
        loc_id = ids.get(locale)
        if loc_id is None:
            result["errors"].append(f"media {locale}: the version has no {locale} "
                                    "localization yet (add its texts first)")
            continue
        result["ctx"]["localizations"][locale] = loc_id
        if library_id:
            _plan_library_locale(result, managers, locale, loc_id, groups, locked, prune)
        else:
            _plan_legacy_locale(result, managers, locale, loc_id, groups, locked)
    return result


def _plan_library_locale(result, managers, locale, loc_id, groups, locked, prune):
    placed = managers.asset_library.placements(loc_id)
    library = result["ctx"]["assets"]
    for (placement_type, group), paths in sorted(groups.items()):
        scope = _scope(locale, placement_type, group)
        current = [p for p in placed
                   if p["placementType"] == placement_type and p["placementGroup"] == group]
        current_names = [p["fileName"] for p in current]
        wanted = [os.path.basename(p) for p in paths]
        result["ctx"].setdefault("orders", {})[scope] = wanted
        for path, name in zip(paths, wanted):
            if name in current_names:
                result["unchanged"] += 1
                continue
            known = library.get((name, os.path.getsize(path)))
            result["changes"].append(_change(scope, name, None, path,
                                             "place" if known else "upload", locked))
        extras = [p for p in current if p["fileName"] not in wanted]
        for extra in extras:
            if prune:
                result["changes"].append(_change(scope, extra["fileName"], extra["fileName"],
                                                 None, "remove", locked))
            else:
                result["notes"].append(f"{scope}: {extra['fileName']} is placed but not in "
                                       "the folder — kept (prune to remove it)")
        kept = [n for n in current_names if n in wanted]
        if kept and kept != [n for n in wanted if n in kept]:
            result["changes"].append(_change(scope, "order", current_names, wanted,
                                             "reorder", locked))


def _plan_legacy_locale(result, managers, locale, loc_id, groups, locked):
    for (placement_type, group), paths in sorted(groups.items()):
        scope = _scope(locale, placement_type, group)
        legacy = legacy_type_for(placement_type, group)
        if legacy is None:
            result["errors"].append(f"{scope}: requires the App Asset Library, which this "
                                    "app does not expose — no legacy display type exists")
            continue
        manager = managers.previews if placement_type == "APP_PREVIEW" else managers.screenshots
        ensure = (manager.ensure_preview_set if placement_type == "APP_PREVIEW"
                  else manager.ensure_screenshot_set)
        existing = manager.existing_filenames(ensure(loc_id, legacy)["id"])
        for path in paths:
            name = os.path.basename(path)
            if name in existing:
                result["unchanged"] += 1
            else:
                change = _change(scope, name, None, path, "upload", locked)
                change["legacy_type"] = legacy
                result["changes"].append(change)


def apply_media(managers, plan):
    """Write the media changes of `plan_media`. Returns the number of writes."""
    if plan.get("errors"):
        return 0
    ctx = plan["ctx"]
    writes = 0
    by_scope = {}
    for change in plan["changes"]:
        if change["locked"]:
            continue
        by_scope.setdefault(change["scope"], []).append(change)
    for scope, changes in by_scope.items():
        locale, placement_type, group = scope.split(" · ")
        loc_id = ctx["localizations"][locale]
        if plan["backend"] == "legacy":
            writes += _apply_legacy(managers, loc_id, placement_type, changes)
        else:
            writes += _apply_library(managers, ctx, loc_id, placement_type, group, changes)
    return writes


def _apply_legacy(managers, loc_id, placement_type, changes):
    manager = managers.previews if placement_type == "APP_PREVIEW" else managers.screenshots
    writes = 0
    for change in changes:
        if placement_type == "APP_PREVIEW":
            set_id = manager.ensure_preview_set(loc_id, change["legacy_type"])["id"]
            manager.upload_preview_to_set(set_id, change["desired"])
        else:
            set_id = manager.ensure_screenshot_set(loc_id, change["legacy_type"])["id"]
            manager.upload_screenshot_to_set(set_id, change["desired"])
        writes += 1
    return writes


def _apply_library(managers, ctx, loc_id, placement_type, group, changes):
    library = managers.asset_library
    writes = 0
    for change in changes:
        if change["action"] == "remove":
            placed = [p for p in library.placements(loc_id)
                      if p["placementType"] == placement_type
                      and p["placementGroup"] == group and p["fileName"] == change["field"]]
            for p in placed:
                library.unplace(p["id"])
                writes += 1
            continue
        if change["action"] not in ("upload", "place"):
            continue
        path = change["desired"]
        key = (os.path.basename(path), os.path.getsize(path))
        asset = ctx["assets"].get(key)
        if asset is None:
            asset = library.upload(ctx["library_id"], path,
                                   _category(placement_type, ctx["ref"]))
            ctx["assets"][key] = asset
            writes += 1
        library.place(loc_id, placement_type, group, media_type_of(path), asset["id"])
        writes += 1
    wanted = ctx.get("orders", {}).get(f"{_scope_locale(ctx, loc_id)} · {placement_type} · {group}")
    if wanted:
        current = [p for p in library.placements(loc_id)
                   if p["placementType"] == placement_type and p["placementGroup"] == group]
        rank = {name: i for i, name in enumerate(wanted)}
        ordered = sorted(current, key=lambda p: (rank.get(p["fileName"], len(rank)),
                                                 current.index(p)))
        if [p["id"] for p in ordered] != [p["id"] for p in current]:
            library.order(loc_id, group, [p["id"] for p in ordered])
            writes += 1
    return writes


def _scope_locale(ctx, loc_id):
    return next(locale for locale, lid in ctx["localizations"].items() if lid == loc_id)


def media_summary(plan, writes):
    """Counters for `publish`: what went where."""
    summary = {"backend": plan["backend"], "screenshots": 0, "previews": 0,
               "creative": 0, "media_skipped": plan["unchanged"], "media_writes": writes}
    for change in plan["changes"]:
        if change["action"] not in ("upload", "place"):
            continue
        placement_type = change["scope"].split(" · ")[1]
        if placement_type in _SCREENSHOT_LIKE:
            summary["screenshots"] += 1
        elif placement_type == "APP_PREVIEW":
            summary["previews"] += 1
        else:
            summary["creative"] += 1
    return summary
