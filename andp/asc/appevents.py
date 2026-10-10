"""In-app events (`appEvents`, `appEventLocalizations`) — App Store Connect API 4.5.1.

An event belongs to the app; its texts live in one localization per language,
and its visuals are App Asset Library placements on those localizations
(EVENT_CARD_ASSET, EVENT_DETAILS_PAGE_ASSET — see AssetLibraryManager with
parent=EVENT_LOCALIZATION). Events are matched by `referenceName`, which App
Store Connect keeps unique per app.
"""

# Event states whose metadata can still be written. Past the review, an event
# is frozen: changing an approved event means creating a new one.
EDITABLE_EVENT_STATES = frozenset({"DRAFT", "READY_FOR_REVIEW", "REJECTED"})
# Gone from the store: never matched, never edited.
ENDED_EVENT_STATES = frozenset({"PAST", "ARCHIVED"})


def _view(resource, included):
    attrs = dict(resource.get("attributes") or {})
    refs = (((resource.get("relationships") or {}).get("localizations") or {})
            .get("data") or [])
    localizations = {}
    for ref in refs:
        loc = included.get(("appEventLocalizations", ref.get("id")))
        if loc is None:
            continue
        loc_attrs = dict(loc.get("attributes") or {})
        localizations[loc_attrs.get("locale")] = {"id": loc["id"], **loc_attrs}
    return {"id": resource["id"], "state": attrs.get("eventState"),
            "attributes": attrs, "localizations": localizations}


class AppEventsManager:
    def __init__(self, client):
        self.client = client

    def list_events(self, app_id):
        """Every event of the app with its localizations, as views."""
        events, included = [], {}
        path = f"/v1/apps/{app_id}/appEvents"
        params = {"include": "localizations", "limit": 200, "limit[localizations]": 50}
        while path:
            response = self.client.get(path, params=params) or {}
            included.update({(i.get("type"), i.get("id")): i
                             for i in response.get("included") or []})
            events.extend(response.get("data") or [])
            path, params = (response.get("links") or {}).get("next"), None
        return [_view(item, included) for item in events]

    def create_event(self, app_id, attributes):
        payload = {"data": {"type": "appEvents", "attributes": attributes,
                            "relationships": {"app": {"data": {"type": "apps",
                                                               "id": app_id}}}}}
        return (self.client.post("/v1/appEvents", payload) or {}).get("data")

    def update_event(self, event_id, attributes):
        payload = {"data": {"type": "appEvents", "id": event_id, "attributes": attributes}}
        return (self.client.patch(f"/v1/appEvents/{event_id}", payload) or {}).get("data")

    def create_localization(self, event_id, locale, attributes):
        payload = {"data": {"type": "appEventLocalizations",
                            "attributes": {"locale": locale, **attributes},
                            "relationships": {"appEvent": {"data": {
                                "type": "appEvents", "id": event_id}}}}}
        return (self.client.post("/v1/appEventLocalizations", payload) or {}).get("data")

    def update_localization(self, localization_id, attributes):
        payload = {"data": {"type": "appEventLocalizations", "id": localization_id,
                            "attributes": attributes}}
        return (self.client.patch(f"/v1/appEventLocalizations/{localization_id}",
                                  payload) or {}).get("data")
