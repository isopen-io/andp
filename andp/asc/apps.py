"""App record configuration via the App Store Connect API.

The app record itself must be created once in the App Store Connect UI
(POST /v1/apps does not exist); everything after that is API-driven.
"""


class AppsManager:
    def __init__(self, client):
        self.client = client

    def find_app(self, bundle_id):
        response = self.client.get("/v1/apps", params={"filter[bundleId]": bundle_id})
        data = response.get("data", [])
        return data[0] if data else None

    def update_app(self, app_id, attributes):
        payload = {"data": {"type": "apps", "id": app_id, "attributes": attributes}}
        return self.client.patch(f"/v1/apps/{app_id}", payload)["data"]

    def get_app_info(self, app_id):
        response = self.client.get(f"/v1/apps/{app_id}/appInfos")
        data = response.get("data", [])
        return data[0] if data else None

    def set_categories(self, app_info_id, primary, secondary=None):
        relationships = {
            "primaryCategory": {"data": {"type": "appCategories", "id": primary}}
        }
        if secondary:
            relationships["secondaryCategory"] = {
                "data": {"type": "appCategories", "id": secondary}
            }
        payload = {
            "data": {
                "type": "appInfos",
                "id": app_info_id,
                "relationships": relationships,
            }
        }
        return self.client.patch(f"/v1/appInfos/{app_info_id}", payload)["data"]

    def ensure_app_info_localization(self, app_info_id, locale, attributes):
        """Create the localization if missing, update it otherwise (locale is immutable)."""
        response = self.client.get(
            f"/v1/appInfos/{app_info_id}/appInfoLocalizations",
            params={"filter[locale]": locale},
        )
        existing = response.get("data", [])
        if existing:
            localization_id = existing[0]["id"]
            payload = {
                "data": {
                    "type": "appInfoLocalizations",
                    "id": localization_id,
                    "attributes": attributes,
                }
            }
            return self.client.patch(
                f"/v1/appInfoLocalizations/{localization_id}", payload
            )["data"]

        payload = {
            "data": {
                "type": "appInfoLocalizations",
                "attributes": {"locale": locale, **attributes},
                "relationships": {
                    "appInfo": {"data": {"type": "appInfos", "id": app_info_id}}
                },
            }
        }
        return self.client.post("/v1/appInfoLocalizations", payload)["data"]
