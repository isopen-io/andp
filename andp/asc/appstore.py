"""App Store release automation via the App Store Connect API.

Review submission uses the modern Review Submissions flow
(reviewSubmissions + reviewSubmissionItems); the legacy
appStoreVersionSubmissions endpoint was removed in ASC API 4.0.
"""


class AppStoreManager:
    def __init__(self, client):
        self.client = client

    # -- versions --------------------------------------------------------

    def ensure_version(self, app_id, version_string, platform="IOS", release_type=None):
        """Return the appStoreVersion for `version_string`, creating it if needed."""
        response = self.client.get(
            f"/v1/apps/{app_id}/appStoreVersions",
            params={
                "filter[versionString]": version_string,
                "filter[platform]": platform,
            },
        )
        existing = response.get("data", [])
        if existing:
            return existing[0]

        attributes = {"versionString": version_string, "platform": platform}
        if release_type:
            attributes["releaseType"] = release_type
        payload = {
            "data": {
                "type": "appStoreVersions",
                "attributes": attributes,
                "relationships": {"app": {"data": {"type": "apps", "id": app_id}}},
            }
        }
        return self.client.post("/v1/appStoreVersions", payload)["data"]

    def update_version_localization(self, version_id, locale, attributes):
        return self.upsert_version_localization(version_id, locale, attributes)[0]

    def upsert_version_localization(self, version_id, locale, attributes):
        """Create or update the localization; return (resource, created)."""
        response = self.client.get(
            f"/v1/appStoreVersions/{version_id}/appStoreVersionLocalizations",
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
                    "type": "appStoreVersionLocalizations",
                    "id": localization_id,
                    "attributes": attributes,
                }
            }
            resource = self.client.patch(
                f"/v1/appStoreVersionLocalizations/{localization_id}", payload
            )["data"]
            return resource, False

        payload = {
            "data": {
                "type": "appStoreVersionLocalizations",
                "attributes": {"locale": locale, **attributes},
                "relationships": {
                    "appStoreVersion": {
                        "data": {"type": "appStoreVersions", "id": version_id}
                    }
                },
            }
        }
        resource = self.client.post("/v1/appStoreVersionLocalizations", payload)["data"]
        return resource, True

    def attach_build(self, version_id, build_id):
        self.client.patch(
            f"/v1/appStoreVersions/{version_id}/relationships/build",
            {"data": {"type": "builds", "id": build_id}},
        )

    # -- review ----------------------------------------------------------

    def submit_for_review(self, app_id, version_id, platform="IOS"):
        """Create a review submission, add the version to it, then submit."""
        submission = self.client.post(
            "/v1/reviewSubmissions",
            {
                "data": {
                    "type": "reviewSubmissions",
                    "attributes": {"platform": platform},
                    "relationships": {
                        "app": {"data": {"type": "apps", "id": app_id}}
                    },
                }
            },
        )["data"]

        self.client.post(
            "/v1/reviewSubmissionItems",
            {
                "data": {
                    "type": "reviewSubmissionItems",
                    "relationships": {
                        "reviewSubmission": {
                            "data": {"type": "reviewSubmissions", "id": submission["id"]}
                        },
                        "appStoreVersion": {
                            "data": {"type": "appStoreVersions", "id": version_id}
                        },
                    },
                }
            },
        )

        return self.client.patch(
            f"/v1/reviewSubmissions/{submission['id']}",
            {
                "data": {
                    "type": "reviewSubmissions",
                    "id": submission["id"],
                    "attributes": {"submitted": True},
                }
            },
        )["data"]

    # -- release ---------------------------------------------------------

    def enable_phased_release(self, version_id):
        payload = {
            "data": {
                "type": "appStoreVersionPhasedReleases",
                "relationships": {
                    "appStoreVersion": {
                        "data": {"type": "appStoreVersions", "id": version_id}
                    }
                },
            }
        }
        return self.client.post("/v1/appStoreVersionPhasedReleases", payload)["data"]

    def request_release(self, version_id):
        payload = {
            "data": {
                "type": "appStoreVersionReleaseRequests",
                "relationships": {
                    "appStoreVersion": {
                        "data": {"type": "appStoreVersions", "id": version_id}
                    }
                },
            }
        }
        return self.client.post("/v1/appStoreVersionReleaseRequests", payload)["data"]
