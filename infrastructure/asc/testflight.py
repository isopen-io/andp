"""TestFlight automation via the App Store Connect API: beta groups,
testers, per-build "What to Test" notes and Beta App Review submission."""

from client import ASCAPIError


class TestFlightManager:
    __test__ = False  # nom en "Test*" : ne pas collecter comme classe de test pytest

    def __init__(self, client):
        self.client = client

    # -- groups --------------------------------------------------------------

    def ensure_group(self, app_id, name, public_link_enabled=None, public_link_limit=None):
        """Return the beta group named `name`, creating it if needed."""
        response = self.client.get(
            "/v1/betaGroups", params={"filter[app]": app_id, "filter[name]": name}
        )
        existing = response.get("data", [])
        if existing:
            return existing[0]

        attributes = {"name": name}
        if public_link_enabled is not None:
            attributes["publicLinkEnabled"] = public_link_enabled
        if public_link_limit is not None:
            attributes["publicLinkLimit"] = public_link_limit
        payload = {
            "data": {
                "type": "betaGroups",
                "attributes": attributes,
                "relationships": {"app": {"data": {"type": "apps", "id": app_id}}},
            }
        }
        return self.client.post("/v1/betaGroups", payload)["data"]

    # -- testers ---------------------------------------------------------------

    def add_tester(self, group_id, email, first_name=None, last_name=None):
        """Create the tester in the group; if they already exist, link them instead."""
        attributes = {"email": email}
        if first_name:
            attributes["firstName"] = first_name
        if last_name:
            attributes["lastName"] = last_name
        payload = {
            "data": {
                "type": "betaTesters",
                "attributes": attributes,
                "relationships": {
                    "betaGroups": {"data": [{"type": "betaGroups", "id": group_id}]}
                },
            }
        }
        try:
            return self.client.post("/v1/betaTesters", payload)["data"]
        except ASCAPIError as exc:
            if exc.status != 409:
                raise

        response = self.client.get("/v1/betaTesters", params={"filter[email]": email})
        testers = response.get("data", [])
        if not testers:
            raise ASCAPIError(409, [{"detail": f"Tester {email} conflicts but cannot be found"}])
        tester = testers[0]
        self.client.post(
            f"/v1/betaGroups/{group_id}/relationships/betaTesters",
            {"data": [{"type": "betaTesters", "id": tester["id"]}]},
        )
        return tester

    def add_testers(self, group_id, testers):
        """testers: iterable of dicts {email, first_name?, last_name?}."""
        return [
            self.add_tester(
                group_id,
                t["email"],
                first_name=t.get("first_name"),
                last_name=t.get("last_name"),
            )
            for t in testers
        ]

    # -- builds ---------------------------------------------------------------

    def add_build_to_group(self, group_id, build_id):
        self.client.post(
            f"/v1/betaGroups/{group_id}/relationships/builds",
            {"data": [{"type": "builds", "id": build_id}]},
        )

    def set_what_to_test(self, build_id, locale, whats_new):
        response = self.client.get(
            f"/v1/builds/{build_id}/betaBuildLocalizations",
            params={"filter[locale]": locale},
        )
        existing = [
            loc for loc in response.get("data", [])
            if loc.get("attributes", {}).get("locale") == locale
        ]
        if existing:
            localization_id = existing[0]["id"]
            payload = {
                "data": {
                    "type": "betaBuildLocalizations",
                    "id": localization_id,
                    "attributes": {"whatsNew": whats_new},
                }
            }
            return self.client.patch(
                f"/v1/betaBuildLocalizations/{localization_id}", payload
            )["data"]

        payload = {
            "data": {
                "type": "betaBuildLocalizations",
                "attributes": {"locale": locale, "whatsNew": whats_new},
                "relationships": {
                    "build": {"data": {"type": "builds", "id": build_id}}
                },
            }
        }
        return self.client.post("/v1/betaBuildLocalizations", payload)["data"]

    # -- review ---------------------------------------------------------------

    def submit_for_beta_review(self, build_id):
        """Required before a build reaches external testers."""
        payload = {
            "data": {
                "type": "betaAppReviewSubmissions",
                "relationships": {
                    "build": {"data": {"type": "builds", "id": build_id}}
                },
            }
        }
        return self.client.post("/v1/betaAppReviewSubmissions", payload)["data"]
