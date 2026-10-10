"""Plan and apply the in-app events of `store.app_events` (family `app_event`).

`plan_events` only reads. Per desired event (matched on `referenceName` among
the app's events that have not ended) it lists:

- the event itself — `create`, or one `update` per attribute that differs
  (`territorySchedules` compared as instants and territory sets);
- each localization — `create`, or one `update` per text that differs;
- each visual — `upload` (new to the App Asset Library) or `place` (the
  library already holds the same file name and size). A placement type holds
  one asset: a different file already placed is `replace`d.

An event past its review (accepted, approved, published) is frozen: it is
left as is with a note — App Store Connect only lets a new event replace it.
An event that already started and was never created is left out the same
way. `apply_events` writes exactly the plan.
"""
import datetime
import os

from .asc.appevents import EDITABLE_EVENT_STATES, ENDED_EVENT_STATES
from .asc.assetlibrary import EVENT_LOCALIZATION, media_type_of
from .event_spec import EVENT_FOLDERS, EVENT_GROUP, same_schedules, wire_schedules

FAMILY = "app_event"
_DEAD_ASSETS = {"FAILED", "ARCHIVED", "REJECTED"}


def _change(scope, field, current, desired, action, locked):
    return {"family": FAMILY, "scope": scope, "field": field, "current": current,
            "desired": desired, "action": action, "locked": locked, "secret": False}


def _library(managers, app_id):
    try:
        return managers.asset_library.library_id(app_id) or None
    except Exception:
        return None


def _same_text(current, desired):
    return (current or "").replace("\r\n", "\n").strip() == desired


def plan_events(managers, app_id, events, now=None):
    """Read-only. {changes, unchanged, errors, notes, ctx}."""
    result = {"changes": [], "unchanged": 0, "errors": [], "notes": [],
              "ctx": {"events": {}, "localizations": {}, "library_id": None,
                      "assets": {}, "desired": {}}}
    if not events:
        return result
    now = now or datetime.datetime.now(datetime.timezone.utc)
    live = {e["attributes"].get("referenceName"): e
            for e in managers.app_events.list_events(app_id)
            if e["state"] not in ENDED_EVENT_STATES}
    territories = None
    if any(s["territories"] == "all" for e in events for s in e["schedules"]):
        territories = sorted(managers.availability.list_available_territories(app_id))
        if not territories:
            result["errors"].append("app_events: territories 'all' — the app is available "
                                    "in no territory yet")
    if any(e["media"] for e in events):
        library_id = _library(managers, app_id)
        result["ctx"]["library_id"] = library_id
        if library_id is None:
            result["errors"].append("app_events: event visuals need the App Asset Library, "
                                    "which this app does not expose")
        else:
            result["ctx"]["ref"] = managers.asset_library.ref_data()
            for media_type in ("IMAGE", "VIDEO"):
                for asset in managers.asset_library.assets(library_id, media_type):
                    if asset.get("state") not in _DEAD_ASSETS:
                        result["ctx"]["assets"][(asset["fileName"], asset["fileSize"])] = asset
    for event in events:
        _plan_event(result, managers, event, live.get(event["attributes"]["referenceName"]),
                    territories or [], now)
    wanted = {e["attributes"]["referenceName"] for e in events}
    for name, event in sorted(live.items()):
        if name not in wanted:
            result["notes"].append(f"app_event {name!r} ({event['state']}) is not in "
                                   "store.app_events — kept")
    return result


def _plan_event(result, managers, event, current, territories, now):
    key = event["key"]
    desired = {**event["attributes"],
               "territorySchedules": wire_schedules(event, territories)}
    result["ctx"]["desired"][key] = {**event, "wire": desired}
    if current is not None and current["state"] not in EDITABLE_EVENT_STATES:
        # Frozen by App Store Connect: nothing can be written, so nothing is
        # planned — a drift (new territory, edited text) is reported once.
        result["notes"].append(f"app_event {key}: {current['state']} — frozen after review, "
                               "left as is; declare a new event to change it")
        result["unchanged"] += 1
        return
    locked = False
    if current is None:
        if min(s["eventStart"] for s in event["schedules"]) <= now:
            result["notes"].append(f"app_event {key}: already started and not created — "
                                   "left out (App Store Connect only creates future events)")
            return
        result["changes"].append(_change(key, "event", None, desired, "create", False))
    else:
        result["ctx"]["events"][key] = current["id"]
        for api, value in desired.items():
            now_value = current["attributes"].get(api)
            same = (same_schedules(now_value, value) if api == "territorySchedules"
                    else now_value == value)
            if same:
                result["unchanged"] += 1
            else:
                result["changes"].append(_change(key, api, now_value, value, "update", locked))
    live_locs = (current or {}).get("localizations") or {}
    for locale, texts in sorted(event["localizations"].items()):
        scope = f"{key} · {locale}"
        loc = live_locs.get(locale)
        if loc is None:
            result["changes"].append(_change(scope, "localization", None, texts, "create",
                                             locked))
        else:
            result["ctx"]["localizations"][(key, locale)] = loc["id"]
            for api, value in texts.items():
                if _same_text(loc.get(api), value):
                    result["unchanged"] += 1
                else:
                    result["changes"].append(_change(scope, api, loc.get(api), value,
                                                     "update", locked))
        groups = event["media"].get(locale) or {}
        placed = (managers.asset_library.placements(loc["id"], parent=EVENT_LOCALIZATION)
                  if loc is not None and groups and result["ctx"]["library_id"] else [])
        for (placement_type, _group), paths in sorted(groups.items()):
            _plan_visual(result, f"{scope} · {placement_type}", placement_type, paths[0],
                         placed, locked)


def _plan_visual(result, scope, placement_type, path, placed, locked):
    name = os.path.basename(path)
    current = [p for p in placed if p["placementType"] == placement_type]
    if any(p["fileName"] == name for p in current):
        result["unchanged"] += 1
        return
    known = result["ctx"]["assets"].get((name, os.path.getsize(path)))
    action = "replace" if current else ("place" if known else "upload")
    result["changes"].append(_change(scope, name, current[0]["fileName"] if current else None,
                                     path, action, locked))


def apply_events(managers, app_id, plan):
    """Write the changes of `plan_events`. Returns the number of writes."""
    if plan.get("errors"):
        raise RuntimeError("; ".join(plan["errors"]))
    ctx = plan["ctx"]
    writes = 0
    changes = [c for c in plan["changes"] if not c["locked"]]
    for key, desired in ctx["desired"].items():
        mine = [c for c in changes if c["scope"] == key]
        if any(c["action"] == "create" for c in mine):
            created = managers.app_events.create_event(app_id, desired["wire"])
            ctx["events"][key] = created["id"]
            writes += 1
        elif mine:
            managers.app_events.update_event(ctx["events"][key],
                                             {c["field"]: c["desired"] for c in mine})
            writes += 1
        for locale in sorted(desired["localizations"]):
            scope = f"{key} · {locale}"
            texts = [c for c in changes if c["scope"] == scope]
            if any(c["action"] == "create" for c in texts):
                created = managers.app_events.create_localization(
                    ctx["events"][key], locale, desired["localizations"][locale])
                ctx["localizations"][(key, locale)] = created["id"]
                writes += 1
            elif texts:
                managers.app_events.update_localization(
                    ctx["localizations"][(key, locale)],
                    {c["field"]: c["desired"] for c in texts})
                writes += 1
            for placement_type in EVENT_FOLDERS.values():
                visual = [c for c in changes if c["scope"] == f"{scope} · {placement_type}"]
                if visual:
                    writes += _apply_visual(managers, ctx, ctx["localizations"][(key, locale)],
                                            placement_type, visual[0])
    return writes


def _apply_visual(managers, ctx, loc_id, placement_type, change):
    library = managers.asset_library
    writes = 0
    if change["action"] == "replace":
        for placed in library.placements(loc_id, parent=EVENT_LOCALIZATION):
            if placed["placementType"] == placement_type:
                library.unplace(placed["id"])
                writes += 1
    path = change["desired"]
    key = (os.path.basename(path), os.path.getsize(path))
    asset = ctx["assets"].get(key)
    if asset is None:
        accepted = ctx["ref"]["categories"].get(placement_type) or ["CREATIVE_ASSETS"]
        asset = library.upload(ctx["library_id"], path, accepted[0])
        ctx["assets"][key] = asset
        writes += 1
    library.place(loc_id, placement_type, EVENT_GROUP, media_type_of(path), asset["id"],
                  parent=EVENT_LOCALIZATION)
    return writes + 1
