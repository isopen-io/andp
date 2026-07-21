"""App Store release automation via the App Store Connect API.

Review submission uses the modern Review Submissions flow
(reviewSubmissions + reviewSubmissionItems); the legacy
appStoreVersionSubmissions endpoint was removed in ASC API 4.0.
"""


# appStoreState is deprecated in favour of appVersionState; a version in one of
# these states can still accept a build and be submitted. READY_FOR_REVIEW is
# included: a pre-filled app auto-advances there before submission.
EDITABLE_VERSION_STATES = frozenset({
    "PREPARE_FOR_SUBMISSION", "READY_FOR_REVIEW", "DEVELOPER_REJECTED",
    "REJECTED", "METADATA_REJECTED", "INVALID_BINARY",
})
# States meaning "already submitted / in review" — a submission for this version
# already exists; do not create another.
IN_REVIEW_VERSION_STATES = frozenset({
    "WAITING_FOR_REVIEW", "IN_REVIEW", "PENDING_APPLE_RELEASE",
    "PENDING_DEVELOPER_RELEASE", "PROCESSING_FOR_APP_STORE",
})


def version_state(version):
    """Read a version's state, preferring the current attribute name."""
    attrs = version.get("attributes", {}) or {}
    return attrs.get("appVersionState") or attrs.get("appStoreState")


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

    def find_version(self, app_id, version_string, platform="IOS"):
        """GET-only version lookup (never creates). Returns the resource or None."""
        response = self.client.get(
            f"/v1/apps/{app_id}/appStoreVersions",
            params={"filter[versionString]": version_string, "filter[platform]": platform},
        )
        data = response.get("data", [])
        return data[0] if data else None

    def get_version(self, version_id):
        return self.client.get(f"/v1/appStoreVersions/{version_id}").get("data")

    def get_version_build(self, version_id):
        """The build attached to the version, or None."""
        return self.client.get(f"/v1/appStoreVersions/{version_id}/build").get("data")

    def list_version_localizations(self, version_id):
        return self.client.get_all(
            f"/v1/appStoreVersions/{version_id}/appStoreVersionLocalizations")

    def localization_screenshot_sets(self, localization_id):
        return self.client.get_all(
            f"/v1/appStoreVersionLocalizations/{localization_id}/appScreenshotSets")

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

    def get_review_submission(self, submission_id):
        """Strong-consistent fetch of a review submission by id (for resume)."""
        return self.client.get(f"/v1/reviewSubmissions/{submission_id}").get("data")

    def find_open_review_submission(self, app_id, platform="IOS"):
        """The app's open (READY_FOR_REVIEW) review submission, or None.

        Apple allows only one open submission per app/platform at a time."""
        response = self.client.get(
            f"/v1/apps/{app_id}/reviewSubmissions",
            params={"filter[state]": "READY_FOR_REVIEW", "filter[platform]": platform},
        )
        data = response.get("data", [])
        return data[0] if data else None

    def submission_version_ids(self, submission_id):
        """The appStoreVersion ids referenced by a submission's items."""
        items = self.client.get_all(f"/v1/reviewSubmissions/{submission_id}/items")
        ids = []
        for item in items:
            rel = (item.get("relationships") or {}).get("appStoreVersion") or {}
            data = rel.get("data")
            if data:
                ids.append(data["id"])
        return ids

    def create_review_submission(self, app_id, platform="IOS"):
        return self.client.post(
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

    def add_submission_item(self, submission_id, version_id):
        return self.client.post(
            "/v1/reviewSubmissionItems",
            {
                "data": {
                    "type": "reviewSubmissionItems",
                    "relationships": {
                        "reviewSubmission": {
                            "data": {"type": "reviewSubmissions", "id": submission_id}
                        },
                        "appStoreVersion": {
                            "data": {"type": "appStoreVersions", "id": version_id}
                        },
                    },
                }
            },
        )["data"]

    def mark_submitted(self, submission_id):
        return self.client.patch(
            f"/v1/reviewSubmissions/{submission_id}",
            {
                "data": {
                    "type": "reviewSubmissions",
                    "id": submission_id,
                    "attributes": {"submitted": True},
                }
            },
        )["data"]

    def submit_for_review(self, app_id, version_id, platform="IOS"):
        """Create a review submission, add the version, then submit
        (non-idempotent convenience; the machine uses the granular methods)."""
        submission = self.create_review_submission(app_id, platform)
        self.add_submission_item(submission["id"], version_id)
        return self.mark_submitted(submission["id"])

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
