"""plan_events / apply_events, and the app_event family inside store plan/apply."""
import datetime

import yaml

from andp.event_spec import read_events
from andp.event_sync import apply_events, plan_events
from andp.listing_plan import apply_plan, build_plan
from andp.listing_source import load_desired
from listing_fakes import event_managers, live_state
from media_files import png

NOW = datetime.datetime(2027, 1, 1, tzinfo=datetime.timezone.utc)
RAW = {
    "key": "saison",
    "reference_name": "Saison {n}",
    "badge": "NEW_SEASON",
    "purpose": "KEEP_ACTIVE_USERS_INFORMED",
    "primary_locale": "fr-FR",
    "territories": "all",
    "publish_start": "2027-01-04T00:00:00+01:00",
    "event_start": "2027-01-11T00:00:00+01:00",
    "event_end": "2027-02-08T20:00:00+01:00",
    "repeat": {"every_days": 56, "count": 1, "first": 4},
    "localizations": {"fr-FR": {"name": "Saison {n}",
                                "short_description": "Huit semaines, quarante étapes",
                                "long_description": "Gagnez des étoiles chaque jour."}},
}


def _events(tmp_path=None, **overrides):
    events, errors, _, _ = read_events([{**RAW, **overrides}],
                                       metadata_dir=str(tmp_path) if tmp_path else None,
                                       now=NOW)
    assert errors == []
    return events


def _card(tmp_path, name="carte.png", key="saison"):
    folder = tmp_path / "app_events" / key / "fr-FR" / "event_card"
    folder.mkdir(parents=True, exist_ok=True)
    return png(folder / name, 1920, 1080)


def _state():
    return live_state()


def test_a_new_event_is_planned_without_writing(tmp_path):
    _card(tmp_path)
    state = _state()
    managers = event_managers(state)
    plan = plan_events(managers, "APP", _events(tmp_path), now=NOW)
    assert managers.writes == [] and plan["errors"] == []
    actions = {(c["scope"], c["field"], c["action"]) for c in plan["changes"]}
    assert actions == {("saison-4", "event", "create"),
                       ("saison-4 · fr-FR", "localization", "create"),
                       ("saison-4 · fr-FR · EVENT_CARD_ASSET", "carte.png", "upload")}
    create = next(c for c in plan["changes"] if c["action"] == "create")
    assert create["desired"]["territorySchedules"][0]["territories"] == sorted(
        state["availability"]["territories"])


def test_apply_creates_event_texts_and_visual_then_replans_empty(tmp_path):
    _card(tmp_path)
    state = _state()
    managers = event_managers(state)
    events = _events(tmp_path)
    writes = apply_events(managers, "APP", plan_events(managers, "APP", events, now=NOW))
    assert writes == 4
    assert managers.writes == [
        ("create_event", "Saison 4"),
        ("create_event_localization", "ev1", "fr-FR"),
        ("upload", "carte.png", "CREATIVE_ASSETS"),
        ("place", "ev1-fr-FR", "EVENT_CARD_ASSET", "DEFAULT_PROFILE", "carte.png")]
    again = plan_events(managers, "APP", events, now=NOW)
    assert again["changes"] == [] and again["unchanged"] > 0


def test_changed_fields_and_a_new_visual_are_updated_and_replaced(tmp_path):
    _card(tmp_path)
    state = _state()
    managers = event_managers(state)
    apply_events(managers, "APP", plan_events(managers, "APP", _events(tmp_path), now=NOW))
    (tmp_path / "app_events" / "saison" / "fr-FR" / "event_card" / "carte.png").unlink()
    _card(tmp_path, "carte-v2.png")
    events = _events(tmp_path, priority="HIGH", event_end="2027-02-01T20:00:00+01:00",
                     localizations={"fr-FR": {**RAW["localizations"]["fr-FR"],
                                              "short_description": "Quarante étapes"}})
    managers.writes.clear()
    plan = plan_events(managers, "APP", events, now=NOW)
    fields = {(c["scope"], c["field"]): c["action"] for c in plan["changes"]}
    assert fields == {("saison-4", "priority"): "update",
                      ("saison-4", "territorySchedules"): "update",
                      ("saison-4 · fr-FR", "shortDescription"): "update",
                      ("saison-4 · fr-FR · EVENT_CARD_ASSET", "carte-v2.png"): "replace"}
    apply_events(managers, "APP", plan)
    assert ("update_event", "ev1", ["priority", "territorySchedules"]) in managers.writes
    assert managers.writes[-1][0] == "place" and managers.writes[-3][0] == "unplace"
    assert plan_events(managers, "APP", events, now=NOW)["changes"] == []


def test_an_approved_event_is_frozen_and_never_fails_the_apply(tmp_path):
    state = _state()
    managers = event_managers(state)
    apply_events(managers, "APP", plan_events(managers, "APP", _events(), now=NOW))
    state["app_events"]["ev1"]["state"] = "APPROVED"
    state["availability"]["territories"] = set(state["availability"]["territories"]) | {"JPN"}
    managers.writes.clear()
    plan = plan_events(managers, "APP", _events(priority="HIGH"), now=NOW)
    assert plan["changes"] == [] and plan["errors"] == []
    assert any("frozen" in n for n in plan["notes"])
    assert apply_events(managers, "APP", plan) == 0 and managers.writes == []


def test_an_event_already_started_and_never_created_is_left_out():
    managers = event_managers(_state())
    later = NOW + datetime.timedelta(days=20)
    plan = plan_events(managers, "APP", _events(), now=later)
    assert plan["errors"] == [] and plan["changes"] == []
    assert any("already started" in n for n in plan["notes"])


def test_past_and_unknown_live_events_are_left_alone():
    state = _state()
    state["app_events"] = {
        "old": {"id": "old", "state": "PAST", "attributes": {"referenceName": "Saison 4"},
                "localizations": {}},
        "other": {"id": "other", "state": "PUBLISHED",
                  "attributes": {"referenceName": "Ligue d'automne"}, "localizations": {}}}
    managers = event_managers(state)
    plan = plan_events(managers, "APP", _events(), now=NOW)
    assert ("saison-4", "event", "create") in {
        (c["scope"], c["field"], c["action"]) for c in plan["changes"]}
    assert any("Ligue d'automne" in n and "kept" in n for n in plan["notes"])


def test_visuals_without_asset_library_are_refused(tmp_path):
    _card(tmp_path)
    state = _state()
    state["library_unavailable"] = True
    plan = plan_events(event_managers(state), "APP", _events(tmp_path), now=NOW)
    assert any("App Asset Library" in e for e in plan["errors"])


def test_store_plan_and_apply_drive_the_app_event_family(tmp_path):
    _card(tmp_path)
    store = yaml.safe_load(yaml.safe_dump({"app_events": [
        {**RAW, "publish_start": "2030-01-04T00:00:00+01:00",
         "event_start": "2030-01-11T00:00:00+01:00",
         "event_end": "2030-02-08T20:00:00+01:00"}]}))
    desired = load_desired(store, project_root=str(tmp_path), metadata_dir=str(tmp_path))
    assert desired["errors"] == []
    state = _state()
    managers = event_managers(state)
    plan = build_plan(managers, "APP", desired)
    assert {c["family"] for c in plan["changes"]} == {"app_event"}
    result = apply_plan(managers, "APP", plan)
    assert result["ok"] and result["families"]["app_event"]["writes"] == 4
    assert build_plan(managers, "APP", desired)["changes"] == []


# -- store submit-events ------------------------------------------------------------

def _submit_project(tmp_path, monkeypatch, ec_private_key_pem, allow=True):
    from andp import service
    from conftest import real_secrets_yaml, write_secrets
    write_secrets(tmp_path, real_secrets_yaml(ec_private_key_pem))
    raw = {**RAW, "publish_start": "2030-01-04T00:00:00+01:00",
           "event_start": "2030-01-11T00:00:00+01:00",
           "event_end": "2030-02-08T20:00:00+01:00",
           "repeat": {"every_days": 56, "count": 2, "first": 4}}
    (tmp_path / "andp.yml").write_text(yaml.safe_dump(
        {"policy": {"allow_submit": allow}, "store": {"app_events": [raw]}}))
    monkeypatch.chdir(tmp_path)
    state = _state()
    managers = event_managers(state)
    managers.apps = __import__("listing_fakes").FakeApps(True)
    monkeypatch.setattr(service, "make_managers", lambda account: managers)
    return managers, state


def test_submit_events_sends_created_events_alone(tmp_path, monkeypatch, ec_private_key_pem):
    from andp.listing_service import submit_events
    managers, state = _submit_project(tmp_path, monkeypatch, ec_private_key_pem)
    managers.app_events.create_event("APP", {"referenceName": "Saison 4"})
    managers.writes.clear()
    r = submit_events("me.demo.app")
    assert r["ok"] is True and r["submitted"] == ["saison-4"]
    assert any("saison-5" in s and "not created" in s for s in r["skipped"])
    assert managers.writes == [("create_review_submission", "IOS"),
                               ("add_event_item", "sub-new", "ev1"),
                               ("mark_submitted", "sub-new")]


def test_submit_events_never_sends_a_draft_holding_a_version(tmp_path, monkeypatch,
                                                              ec_private_key_pem):
    from andp.listing_service import submit_events
    managers, state = _submit_project(tmp_path, monkeypatch, ec_private_key_pem)
    managers.app_events.create_event("APP", {"referenceName": "Saison 4"})
    state["draft_submission"] = {"id": "sub1", "items": [("appStoreVersion", "v1")]}
    managers.writes.clear()
    r = submit_events("me.demo.app")
    assert r["ok"] is False and r["error"]["code"] == "review_submission_conflict"
    assert managers.writes == []


def test_submit_events_is_gated_by_policy(tmp_path, monkeypatch, ec_private_key_pem):
    from andp.listing_service import submit_events
    managers, _ = _submit_project(tmp_path, monkeypatch, ec_private_key_pem, allow=False)
    r = submit_events("me.demo.app")
    assert r["ok"] is False and r["error"]["code"] == "submit_not_allowed"
    assert managers.writes == []


def test_submit_events_refuses_a_draft_holding_events_not_asked_for(
        tmp_path, monkeypatch, ec_private_key_pem):
    from andp.listing_service import submit_events
    managers, state = _submit_project(tmp_path, monkeypatch, ec_private_key_pem)
    managers.app_events.create_event("APP", {"referenceName": "Saison 4"})
    managers.app_events.create_event("APP", {"referenceName": "Saison 5"})
    state["draft_submission"] = {"id": "sub1", "items": [("appEvent", "ev1")]}
    managers.writes.clear()
    r = submit_events("me.demo.app", keys=["saison-5"])
    assert r["ok"] is False and r["error"]["code"] == "review_submission_conflict"
    assert managers.writes == []
    r = submit_events("me.demo.app")
    assert r["ok"] is True and r["submitted"] == ["saison-4", "saison-5"]
    assert managers.writes == [("add_event_item", "sub1", "ev2"), ("mark_submitted", "sub1")]
