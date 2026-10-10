"""In-app events (`store.app_events`) — pure reading and validation, no network.

An in-app event is a card on the App Store (product page, search, Today, Apple
Games) for a time-limited moment of the app: a season, a competition, a
premiere. `store.app_events` lists them:

    store:
      app_events:
        - key: saison                      # stable id; also the media folder name
          reference_name: "Saison {n}"     # unique per app, 64 characters
          badge: NEW_SEASON                # LIVE_EVENT, PREMIERE, CHALLENGE, COMPETITION…
          purpose: KEEP_ACTIVE_USERS_INFORMED
          priority: HIGH                   # HIGH | NORMAL
          purchase_requirement: NO_COST_ASSOCIATED
          deep_link: https://meeshy.me/jeu/saisons/{n}
          primary_locale: fr-FR
          territories: all                 # or [FRA, BEL, …]
          publish_start: 2026-10-05T00:00:00+02:00
          event_start: 2026-10-12T00:00:00+02:00
          event_end: 2026-11-11T20:00:00+01:00
          repeat: {every_days: 56, count: 3, first: 1}
          localizations:
            fr-FR: {name: "Saison {n}", short_description: …, long_description: …}

`repeat` unfolds one entry into `count` events, `every_days` apart; `{n}` is the
occurrence number (`first`, `first + 1`, …) in the reference name, the deep
link and the texts. With `time_zone: Europe/Paris` the occurrences keep their
local hour across a daylight-saving change (without it, they keep the offset
written in the dates). A per-territory schedule list (`schedules:`) replaces the
three dates when the event starts on different days in different places.

Visuals live in the metadata folder, one asset per placement:

    <metadata_dir>/app_events/<key>/<locale>/event_card/*            → EVENT_CARD_ASSET
    <metadata_dir>/app_events/<key>/<locale>/event_details_page/*    → EVENT_DETAILS_PAGE_ASSET

For a repeated event, `app_events/<key>-<n>/` (e.g. `saison-2`) wins over the
shared `app_events/<key>/` folder.

Apple's rules (App Store Connect Help, « Offer In-App Events », read 2026-10-10)
are checked before any request: an event lasts 15 minutes to 31 days; it is
published at most 14 days before it starts; per-territory starts are within
48 hours of each other; at most 15 events are approved and 10 overlap at once.
"""
import datetime
import os
import re

from . import listing_spec as spec

MAX_DURATION = datetime.timedelta(days=31)
MIN_DURATION = datetime.timedelta(minutes=15)
MAX_PUBLISH_LEAD = datetime.timedelta(days=14)
MAX_START_SPREAD = datetime.timedelta(hours=48)
MAX_APPROVED = 15
MAX_OVERLAPPING = 10

EVENT_FOLDERS = {
    "event_card": "EVENT_CARD_ASSET",
    "event_details_page": "EVENT_DETAILS_PAGE_ASSET",
}
EVENT_GROUP = "DEFAULT_PROFILE"
EVENT_FEATURE = "IN_APP_EVENTS"

_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_DATES = {"publish_start": "publishStart", "event_start": "eventStart",
          "event_end": "eventEnd"}
_OWN_KEYS = {"key", "territories", "schedules", "repeat", "localizations",
             "submit", "time_zone"} | set(_DATES)
_REPEAT_KEYS = {"every_days", "count", "first"}


def parse_instant(value):
    return spec._parse_datetime(value)


def _iso(moment):
    return moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _territories(raw, where, errors):
    if raw is None or raw == "all":
        return "all"
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)) or not raw:
        errors.append(f"{where}: territories must be 'all' or a list of territory codes")
        return None
    return sorted({str(t).strip().upper() for t in raw})


def _schedule(mapping, territories, where, errors):
    dates = {}
    for key, api in _DATES.items():
        raw = mapping.get(key, mapping.get(api))
        if raw is None:
            errors.append(f"{where}: {key} is required")
            continue
        moment = parse_instant(raw)
        if moment is None:
            errors.append(f"{where}: {key} {raw!r} is not an ISO 8601 date-time with a "
                          "time zone (e.g. 2026-10-12T00:00:00+02:00)")
            continue
        dates[api] = moment
    if len(dates) < 3:
        return None
    own = _territories(mapping.get("territories"), where, errors) \
        if "territories" in mapping else territories
    return {"territories": own, **dates}


def schedule_rules(schedules, where):
    """Apple's timing rules on one event's schedules. Returns errors. Pure."""
    errors = []
    for s in schedules:
        if s["publishStart"] > s["eventStart"]:
            errors.append(f"{where}: publish_start is after event_start")
        elif s["eventStart"] - s["publishStart"] > MAX_PUBLISH_LEAD:
            errors.append(f"{where}: published {(s['eventStart'] - s['publishStart']).days} "
                          "days before it starts — the App Store allows 14")
        length = s["eventEnd"] - s["eventStart"]
        if length < MIN_DURATION:
            errors.append(f"{where}: an event lasts at least 15 minutes")
        elif length > MAX_DURATION:
            errors.append(f"{where}: lasts {length.days} days — the App Store allows 31 "
                          "(split a longer season into its opening event)")
    starts = [s["eventStart"] for s in schedules]
    if starts and max(starts) - min(starts) > MAX_START_SPREAD:
        errors.append(f"{where}: per-territory starts must be within 48 hours of each other")
    return errors


def _shift(moment, days, zone):
    """`moment` moved by `days` — on the wall clock of `zone` when one is given,
    so a weekly or seasonal event keeps its local hour across a DST change."""
    if zone is None:
        return moment + datetime.timedelta(days=days)
    local = moment.astimezone(zone).replace(tzinfo=None) + datetime.timedelta(days=days)
    return local.replace(tzinfo=zone)


def _zone(name, where, errors):
    if name is None:
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(str(name))
    except Exception:
        errors.append(f"{where}: unknown time_zone {name!r} (e.g. Europe/Paris)")
        return None


def _fill(value, n):
    return value.replace("{n}", str(n)) if isinstance(value, str) and n is not None else value


def _occurrences(raw, where, errors):
    repeat = raw.get("repeat")
    if repeat is None:
        return [(None, 0)]
    if not isinstance(repeat, dict) or set(repeat) - _REPEAT_KEYS:
        errors.append(f"{where}: repeat takes every_days, count and first")
        return []
    try:
        every = int(repeat.get("every_days"))
        count = int(repeat.get("count", 1))
        first = int(repeat.get("first", 1))
    except (TypeError, ValueError):
        errors.append(f"{where}: repeat.every_days, count and first are whole numbers")
        return []
    if every < 1 or count < 1:
        errors.append(f"{where}: repeat.every_days and repeat.count are at least 1")
        return []
    return [(first + i, every * i) for i in range(count)]


def _media(metadata_dir, key, base, locales, ref, errors):
    """{locale: {(placementType, DEFAULT_PROFILE): [paths]}} for one event."""
    from .media_spec import check_media, max_count, _media_files
    if not metadata_dir:
        return {}
    root = os.path.join(metadata_dir, "app_events")
    folder = next((os.path.join(root, name) for name in (key, base)
                   if os.path.isdir(os.path.join(root, name))), None)
    if folder is None:
        return {}
    media = {}
    for locale in sorted(os.listdir(folder)):
        locale_dir = os.path.join(folder, locale)
        if not os.path.isdir(locale_dir) or locale.startswith((".", "_")):
            continue
        if locale not in locales:
            errors.append(f"{os.path.relpath(locale_dir, metadata_dir)}: the event has no "
                          f"{locale} localization")
            continue
        for name, placement_type in EVENT_FOLDERS.items():
            path = os.path.join(locale_dir, name)
            if not os.path.isdir(path):
                continue
            files = _media_files(path, placement_type)
            if not files:
                continue
            rel = os.path.relpath(path, metadata_dir)
            limit = max_count(placement_type, ref, feature=EVENT_FEATURE)
            if limit and len(files) > limit:
                errors.append(f"{rel}: {len(files)} files, the App Store allows {limit}")
            for file_path in files:
                _spec, problem = check_media(file_path, placement_type, EVENT_GROUP, ref)
                if problem:
                    errors.append(f"{os.path.relpath(file_path, metadata_dir)}: {problem}")
            media.setdefault(locale, {})[(placement_type, EVENT_GROUP)] = files
    return media


def read_events(raw_events, metadata_dir=None, ref=None, now=None):
    """(events, errors, warnings, notes) from the `store.app_events` list.

    Each event: {key, attributes, schedules, localizations, media, submit}.
    Past occurrences (ended before `now`) are left out with a note."""
    from .asc.asset_refdata import REF_DATA
    ref = ref or REF_DATA
    now = now or datetime.datetime.now(datetime.timezone.utc)
    errors, warnings, notes, events = [], [], [], []
    if raw_events is None:
        return events, errors, warnings, notes
    if not isinstance(raw_events, list):
        return events, ["store.app_events: expected a list of events"], warnings, notes
    seen_keys, seen_names = set(), set()
    for index, raw in enumerate(raw_events):
        where = f"store.app_events[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{where}: expected a mapping")
            continue
        base = str(raw.get("key") or "")
        if not _KEY.match(base):
            errors.append(f"{where}: key is required (lower-case letters, digits, - or _)")
            continue
        where = f"store.app_events.{base}"
        fields = {k: v for k, v in raw.items() if k not in _OWN_KEYS}
        territories = _territories(raw.get("territories"), where, errors)
        zone = _zone(raw.get("time_zone"), where, errors)
        for n, shift in _occurrences(raw, where, errors):
            key = base if n is None else f"{base}-{n}"
            here = f"store.app_events.{key}"
            if key in seen_keys:
                errors.append(f"{here}: the key is used twice")
                continue
            seen_keys.add(key)
            attrs, errs, warns = spec.pick(spec.APP_EVENT_FIELDS,
                                           {k: _fill(v, n) for k, v in fields.items()}, here)
            errors.extend(errs)
            warnings.extend(warns)
            for field in spec.APP_EVENT_FIELDS:
                if field.required and field.api not in attrs:
                    errors.append(f"{here}: {field.api} is required")
            name = attrs.get("referenceName")
            if name in seen_names:
                errors.append(f"{here}: reference name {name!r} is used twice")
            seen_names.add(name)
            raw_schedules = raw.get("schedules") or [
                {k: raw[k] for k in _DATES if k in raw}]
            schedules = [s for s in (_schedule(m, territories, f"{here}.schedule", errors)
                                     for m in raw_schedules) if s]
            schedules = [{**s, **{api: _shift(s[api], shift, zone) for api in _DATES.values()}}
                         for s in schedules]
            if not schedules:
                continue
            if max(s["eventEnd"] for s in schedules) <= now:
                notes.append(f"{here}: ended {_iso(max(s['eventEnd'] for s in schedules))} "
                             "— left out")
                continue
            errors.extend(schedule_rules(schedules, here))
            localizations = {}
            for locale, mapping in sorted((raw.get("localizations") or {}).items()):
                loc_attrs, errs, warns = spec.pick(
                    spec.APP_EVENT_LOCALIZATION_FIELDS,
                    {k: _fill(v, n) for k, v in (mapping or {}).items()},
                    f"{here}.localizations.{locale}")
                errors.extend(errs)
                warnings.extend(warns)
                for field in spec.APP_EVENT_LOCALIZATION_FIELDS:
                    if field.api not in loc_attrs:
                        errors.append(f"{here}.localizations.{locale}: {field.api} is required")
                localizations[locale] = loc_attrs
            primary = attrs.get("primaryLocale")
            if not localizations:
                errors.append(f"{here}: at least one localization is required")
            elif primary and primary not in localizations:
                errors.append(f"{here}: no localization for the primary locale {primary}")
            media = _media(metadata_dir, key, base, set(localizations), ref, errors)
            for placement_type in EVENT_FOLDERS.values():
                if not any((placement_type, EVENT_GROUP) in groups for groups in media.values()):
                    warnings.append(f"{here}: no {placement_type} visual — App Review "
                                    "needs one before the event can be submitted")
            events.append({"key": key, "attributes": attrs, "schedules": schedules,
                           "localizations": localizations, "media": media,
                           "submit": raw.get("submit", True) is not False})
    count_errors, count_warnings = count_rules(events)
    errors.extend(count_errors)
    warnings.extend(count_warnings)
    return events, errors, warnings, notes


def count_rules(events):
    """(errors, warnings): at most 10 overlapping (error); more than 15 upcoming
    is only a warning — Apple caps APPROVED events, and drafts wait their turn."""
    errors, warnings = [], []
    if len(events) > MAX_APPROVED:
        warnings.append(f"store.app_events: {len(events)} upcoming events — the App Store "
                        f"keeps at most {MAX_APPROVED} approved at once; submit them "
                        "as they come")
    spans = sorted((min(s["eventStart"] for s in e["schedules"]),
                    max(s["eventEnd"] for s in e["schedules"]), e["key"]) for e in events)
    for start, _end, key in spans:
        live = [k for s, e, k in spans if s <= start < e]
        if len(live) > MAX_OVERLAPPING:
            errors.append(f"store.app_events: {len(live)} events overlap at {_iso(start)} "
                          f"— the App Store allows {MAX_OVERLAPPING}")
            break
    return errors, warnings


def wire_schedules(event, all_territories=None):
    """The territorySchedules attribute as App Store Connect stores it."""
    wired = []
    for s in event["schedules"]:
        territories = s["territories"]
        if territories == "all":
            territories = sorted(all_territories or [])
        wired.append({"territories": list(territories),
                      "publishStart": _iso(s["publishStart"]),
                      "eventStart": _iso(s["eventStart"]),
                      "eventEnd": _iso(s["eventEnd"])})
    return wired


def same_schedules(current, desired):
    """Compare territorySchedules as instants and territory sets. Pure."""
    def norm(schedules):
        out = []
        for s in schedules or []:
            out.append((tuple(sorted(s.get("territories") or [])),
                        *(parse_instant(s.get(k)) for k in ("publishStart", "eventStart",
                                                            "eventEnd"))))
        return sorted(out, key=repr)
    return norm(current) == norm(desired)
