"""store.app_events — reading, repeat, Apple's timing and count rules (pure)."""
import datetime

from andp.event_spec import read_events, same_schedules, wire_schedules
from media_files import mp4, png

NOW = datetime.datetime(2026, 10, 10, tzinfo=datetime.timezone.utc)


def _event(**overrides):
    event = {
        "key": "saison",
        "reference_name": "Saison {n}",
        "badge": "NEW_SEASON",
        "purpose": "KEEP_ACTIVE_USERS_INFORMED",
        "primary_locale": "fr-FR",
        "deep_link": "https://meeshy.me/me/progression/saison/{n}",
        "publish_start": "2026-10-05T00:00:00+02:00",
        "event_start": "2026-10-12T00:00:00+02:00",
        "event_end": "2026-11-09T20:00:00+01:00",
        "localizations": {"fr-FR": {"name": "Saison {n}",
                                    "short_description": "Huit semaines, quarante étapes",
                                    "long_description": "Gagnez des étoiles chaque jour."}},
    }
    event.update(overrides)
    return event


def _read(*raw, metadata_dir=None):
    return read_events(list(raw), metadata_dir=metadata_dir, now=NOW)


def test_a_plain_event_is_read_with_its_fields_and_schedule():
    events, errors, warnings, notes = _read(_event(repeat=None, reference_name="Saison 1"))
    assert errors == [] and notes == []
    event = events[0]
    assert event["key"] == "saison"
    assert event["attributes"] == {
        "referenceName": "Saison 1", "badge": "NEW_SEASON",
        "purpose": "KEEP_ACTIVE_USERS_INFORMED", "primaryLocale": "fr-FR",
        "deepLink": "https://meeshy.me/me/progression/saison/{n}"}
    assert event["localizations"]["fr-FR"]["shortDescription"] == "Huit semaines, quarante étapes"
    assert event["schedules"][0]["territories"] == "all"
    assert event["submit"] is True
    assert any("EVENT_CARD_ASSET" in w for w in warnings)


def test_repeat_unfolds_numbered_events_shifted_by_the_period():
    events, errors, _, _ = _read(_event(repeat={"every_days": 56, "count": 3, "first": 1}))
    assert errors == []
    assert [e["key"] for e in events] == ["saison-1", "saison-2", "saison-3"]
    assert [e["attributes"]["referenceName"] for e in events] == [
        "Saison 1", "Saison 2", "Saison 3"]
    assert events[1]["attributes"]["deepLink"].endswith("/saison/2")
    assert events[2]["localizations"]["fr-FR"]["name"] == "Saison 3"
    gap = events[1]["schedules"][0]["eventStart"] - events[0]["schedules"][0]["eventStart"]
    assert gap == datetime.timedelta(days=56)


def test_past_occurrences_are_left_out_with_a_note():
    events, errors, _, notes = _read(_event(
        publish_start="2026-08-10T00:00:00Z", event_start="2026-08-17T00:00:00Z",
        event_end="2026-09-10T00:00:00Z", repeat={"every_days": 56, "count": 2}))
    assert errors == []
    assert [e["key"] for e in events] == ["saison-2"]
    assert "saison-1" in notes[0] and "left out" in notes[0]


def test_an_event_longer_than_31_days_is_refused():
    _, errors, _, _ = _read(_event(event_end="2026-12-07T20:00:00+01:00"))
    assert any("allows 31" in e for e in errors)


def test_publication_more_than_14_days_ahead_is_refused():
    _, errors, _, _ = _read(_event(publish_start="2026-09-20T00:00:00+02:00"))
    assert any("allows 14" in e for e in errors)


def test_an_event_shorter_than_15_minutes_is_refused():
    _, errors, _, _ = _read(_event(event_end="2026-10-12T00:10:00+02:00"))
    assert any("15 minutes" in e for e in errors)


def test_per_territory_starts_must_stay_within_48_hours():
    _, errors, _, _ = _read(_event(schedules=[
        {"territories": ["FRA"], "publish_start": "2026-10-11T00:00:00Z",
         "event_start": "2026-10-12T00:00:00Z", "event_end": "2026-10-20T00:00:00Z"},
        {"territories": ["USA"], "publish_start": "2026-10-13T00:00:00Z",
         "event_start": "2026-10-15T00:00:00Z", "event_end": "2026-10-20T00:00:00Z"}]))
    assert any("48 hours" in e for e in errors)


def test_texts_follow_the_app_store_limits():
    _, errors, _, _ = _read(_event(localizations={"fr-FR": {
        "name": "N" * 31, "short_description": "S" * 51, "long_description": "L" * 121}}))
    assert sum("the App Store allows" in e for e in errors) == 3


def test_badge_purpose_and_dates_are_required_and_checked():
    raw = _event(badge="SEASON")
    raw.pop("purpose")
    raw.pop("event_end")
    _, errors, _, _ = _read(raw)
    assert any("badge" in e and "not one of" in e for e in errors)
    assert any("purpose is required" in e for e in errors)
    assert any("event_end is required" in e for e in errors)


def test_a_custom_scheme_deep_link_is_accepted_but_not_a_bare_path():
    _, errors, _, _ = _read(_event(deep_link="meeshy://jeu/saison/1"))
    assert errors == []
    _, errors, _, _ = _read(_event(deep_link="/jeu/saison"))
    assert any("deepLink" in e for e in errors)


def test_the_primary_locale_needs_a_localization():
    _, errors, _, _ = _read(_event(primary_locale="en-US"))
    assert any("primary locale en-US" in e for e in errors)


def test_duplicate_keys_and_reference_names_are_refused():
    _, errors, _, _ = _read(_event(reference_name="Ligue"),
                            _event(key="ligue", reference_name="Ligue"))
    assert any("used twice" in e for e in errors)


def test_more_than_fifteen_upcoming_events_only_warn():
    events, errors, warnings, _ = _read(_event(
        event_end="2026-10-19T00:00:00+02:00", repeat={"every_days": 7, "count": 16}))
    assert len(events) == 16 and errors == []
    assert any("at most 15 approved" in w for w in warnings)


def test_time_zone_keeps_the_local_hour_across_daylight_saving():
    events, errors, _, _ = _read(_event(
        time_zone="Europe/Paris", publish_start="2026-10-19T00:00:00+02:00",
        event_start="2026-10-19T00:00:00+02:00", event_end="2026-10-25T20:00:00+01:00",
        repeat={"every_days": 7, "count": 2}))
    assert errors == []
    second = events[1]["schedules"][0]["eventStart"]
    assert second.astimezone(datetime.timezone.utc) == datetime.datetime(
        2026, 10, 25, 23, 0, tzinfo=datetime.timezone.utc)   # 00:00 CET
    _, errors, _, _ = _read(_event(time_zone="Mars/Olympus"))
    assert any("unknown time_zone" in e for e in errors)


def test_more_than_ten_overlapping_events_are_refused():
    raw = [_event(key=f"e{i}", reference_name=f"E{i}") for i in range(11)]
    _, errors, _, _ = _read(*raw)
    assert any("overlap" in e for e in errors)


def test_visuals_are_read_and_checked_per_locale(tmp_path):
    base = tmp_path / "app_events" / "saison" / "fr-FR"
    (base / "event_card").mkdir(parents=True)
    (base / "event_details_page").mkdir()
    png(base / "event_card" / "carte.png", 1920, 1080)
    mp4(base / "event_details_page" / "page.mp4", 1080, 1920, 20)
    own = tmp_path / "app_events" / "saison-2" / "fr-FR" / "event_card"
    own.mkdir(parents=True)
    png(own / "carte-2.png", 3840, 2160)
    events, errors, warnings, _ = _read(_event(repeat={"every_days": 56, "count": 2}),
                                        metadata_dir=str(tmp_path))
    assert errors == []
    first, second = events
    assert sorted(first["media"]["fr-FR"]) == [("EVENT_CARD_ASSET", "DEFAULT_PROFILE"),
                                               ("EVENT_DETAILS_PAGE_ASSET", "DEFAULT_PROFILE")]
    assert second["media"]["fr-FR"][("EVENT_CARD_ASSET", "DEFAULT_PROFILE")][0].endswith(
        "carte-2.png")
    assert not any("saison-1" in w for w in warnings)


def test_a_wrong_visual_or_a_second_one_is_refused(tmp_path):
    card = tmp_path / "app_events" / "saison" / "fr-FR" / "event_card"
    card.mkdir(parents=True)
    png(card / "a.png", 1000, 1000)
    png(card / "b.png", 1920, 1080)
    other = tmp_path / "app_events" / "saison" / "de-DE"
    other.mkdir()
    _, errors, _, _ = _read(_event(), metadata_dir=str(tmp_path))
    assert any("allows 1" in e for e in errors)
    assert any("1000×1000" in e for e in errors)
    assert any("no de-DE localization" in e for e in errors)


def test_schedules_are_wired_in_utc_and_compared_as_instants():
    events, _, _, _ = _read(_event())
    wired = wire_schedules(events[0], ["FRA", "BEL"])
    assert wired == [{"territories": ["BEL", "FRA"], "publishStart": "2026-10-04T22:00:00Z",
                      "eventStart": "2026-10-11T22:00:00Z",
                      "eventEnd": "2026-11-09T19:00:00Z"}]
    live = [{"territories": ["BEL", "FRA"], "publishStart": "2026-10-05T00:00:00+02:00",
             "eventStart": "2026-10-12T00:00:00+02:00", "eventEnd": "2026-11-09T19:00:00Z"}]
    assert same_schedules(live, wired)
    assert not same_schedules(live, [{**wired[0], "territories": ["FRA"]}])
