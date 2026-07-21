"""App availability across territories via appAvailabilities v2.

deliver has no territory support — this exceeds parity. The whole desired set is
POSTed in one atomic request (JSON:API is all-or-nothing, so there is no
partial-delist failure mode). Reads paginate; the available set filters on
attributes.available == true so a listed-but-unavailable territory is excluded.
"""


class AvailabilityManager:
    def __init__(self, client):
        self.client = client

    def get_availability(self, app_id):
        """{id, available_in_new_territories} for the app, or None."""
        data = (self.client.get(f"/v1/apps/{app_id}/appAvailabilityV2") or {}).get("data")
        if not data:
            return None
        return {
            "id": data["id"],
            "available_in_new_territories": bool(
                data.get("attributes", {}).get("availableInNewTerritories")),
        }

    def list_available_territories(self, app_id):
        """The set of territory ids the app is currently available in."""
        availability = self.get_availability(app_id)
        if availability is None:
            return set()
        items = self.client.get_all(
            f"/v2/appAvailabilities/{availability['id']}/territoryAvailabilities")
        available = set()
        for item in items:
            if not item.get("attributes", {}).get("available"):
                continue  # N2: a territory can be listed as available:false
            terr = (((item.get("relationships") or {}).get("territory") or {})
                    .get("data") or {}).get("id")
            if terr:
                available.add(terr)
        return available

    def availability_snapshot(self, app_id):
        """{id, available_in_new_territories, territories:set} in one pass, or None.

        The service uses this so a reconcile reads current state once."""
        availability = self.get_availability(app_id)
        if availability is None:
            return None
        items = self.client.get_all(
            f"/v2/appAvailabilities/{availability['id']}/territoryAvailabilities")
        territories = set()
        for item in items:
            if not item.get("attributes", {}).get("available"):
                continue
            terr = (((item.get("relationships") or {}).get("territory") or {})
                    .get("data") or {}).get("id")
            if terr:
                territories.add(terr)
        return {**availability, "territories": territories}

    def list_all_territories(self):
        """Every territory id App Store Connect knows (paginated — ~175)."""
        return {t["id"] for t in self.client.get_all("/v1/territories")}

    def set_availability(self, app_id, territories, available_in_new_territories=False):
        """Set (replace) the app's territory availability in one atomic POST."""
        refs, included = [], []
        for i, territory in enumerate(sorted(territories)):
            temp = f"${{ta{i}}}"
            refs.append({"type": "territoryAvailabilities", "id": temp})
            included.append({
                "type": "territoryAvailabilities",
                "id": temp,
                "attributes": {"available": True},
                "relationships": {
                    "territory": {"data": {"type": "territories", "id": territory}}
                },
            })
        payload = {
            "data": {
                "type": "appAvailabilities",
                "attributes": {"availableInNewTerritories": bool(available_in_new_territories)},
                "relationships": {
                    "app": {"data": {"type": "apps", "id": app_id}},
                    "territoryAvailabilities": {"data": refs},
                },
            },
            "included": included,
        }
        return (self.client.post("/v2/appAvailabilities", payload) or {}).get("data")
