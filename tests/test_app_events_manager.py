"""AppEventsManager and event placements — the HTTP contract (OpenAPI 4.5.1, 2026-10-06)."""
from andp.asc.assetlibrary import EVENT_LOCALIZATION
from conftest import FakeResponse, FakeSession, make_test_managers


def _managers(*responses):
    session = FakeSession(list(responses))
    return make_test_managers(session), session


def _ok(data, **extra):
    return FakeResponse(200, {"data": data, "links": {}, **extra})


def test_list_events_joins_their_localizations():
    managers, session = _managers(_ok(
        [{"id": "ev1", "type": "appEvents",
          "attributes": {"referenceName": "Saison 1", "eventState": "DRAFT"},
          "relationships": {"localizations": {"data": [
              {"type": "appEventLocalizations", "id": "l1"}]}}}],
        included=[{"type": "appEventLocalizations", "id": "l1",
                   "attributes": {"locale": "fr-FR", "name": "Saison 1"}}]))
    events = managers.app_events.list_events("APP")
    assert session.requests[0]["url"].endswith("/v1/apps/APP/appEvents")
    assert session.requests[0]["params"]["include"] == "localizations"
    assert events == [{"id": "ev1", "state": "DRAFT",
                       "attributes": {"referenceName": "Saison 1", "eventState": "DRAFT"},
                       "localizations": {"fr-FR": {"id": "l1", "locale": "fr-FR",
                                                   "name": "Saison 1"}}}]


def test_events_and_localizations_are_created_and_updated():
    managers, session = _managers(_ok({"id": "ev1"}), _ok({"id": "ev1"}),
                                  _ok({"id": "l1"}), _ok({"id": "l1"}))
    events = managers.app_events
    events.create_event("APP", {"referenceName": "Saison 1", "badge": "NEW_SEASON"})
    events.update_event("ev1", {"priority": "HIGH"})
    events.create_localization("ev1", "fr-FR", {"name": "Saison 1"})
    events.update_localization("l1", {"shortDescription": "Huit semaines"})
    create, update, loc, loc_update = (r["json"]["data"] for r in session.requests)
    assert session.requests[0]["url"].endswith("/v1/appEvents")
    assert create["relationships"]["app"]["data"] == {"type": "apps", "id": "APP"}
    assert session.requests[1]["method"] == "PATCH" and update["id"] == "ev1"
    assert loc["attributes"] == {"locale": "fr-FR", "name": "Saison 1"}
    assert loc["relationships"]["appEvent"]["data"] == {"type": "appEvents", "id": "ev1"}
    assert session.requests[3]["url"].endswith("/v1/appEventLocalizations/l1")
    assert loc_update["attributes"] == {"shortDescription": "Huit semaines"}


def test_a_placement_can_sit_on_an_event_localization():
    managers, session = _managers(_ok([]), _ok({"id": "pl1"}))
    library = managers.asset_library
    library.placements("l1", parent=EVENT_LOCALIZATION)
    library.place("l1", "EVENT_CARD_ASSET", "DEFAULT_PROFILE", "IMAGE", "img1",
                  parent=EVENT_LOCALIZATION)
    assert session.requests[0]["url"].endswith("/v1/appEventLocalizations/l1/placements")
    rels = session.requests[1]["json"]["data"]["relationships"]
    assert rels["appEventLocalization"]["data"] == {"type": "appEventLocalizations",
                                                    "id": "l1"}
    assert "appStoreVersionLocalization" not in rels


def test_list_events_follows_the_next_page():
    page1 = _ok([{"id": "ev1", "attributes": {"referenceName": "A"}}])
    page1._json["links"] = {"next": "https://api.appstoreconnect.apple.com/v1/next"}
    managers, session = _managers(page1, _ok([{"id": "ev2",
                                               "attributes": {"referenceName": "B"}}]))
    events = managers.app_events.list_events("APP")
    assert [e["id"] for e in events] == ["ev1", "ev2"]
    assert session.requests[1]["url"] == "https://api.appstoreconnect.apple.com/v1/next"


def test_submission_items_reads_every_relationship_and_fails_closed():
    managers, session = _managers(_ok([
        {"id": "i1", "relationships": {
            "reviewSubmission": {"data": {"type": "reviewSubmissions", "id": "s"}},
            "appEvent": {"data": {"type": "appEvents", "id": "ev1"}}}},
        {"id": "i2", "relationships": {
            "appStoreVersion": {"data": {"type": "appStoreVersions", "id": "v1"}}}},
        {"id": "i3", "relationships": {
            "appStoreVersion": {"links": {"related": "https://…"}}}}]))
    items = managers.appstore.submission_items("s")
    assert "appEvent" in session.requests[0]["params"]["include"]
    assert items == [("appEvent", "ev1"), ("appStoreVersion", "v1"), ("unknown", "i3")]
