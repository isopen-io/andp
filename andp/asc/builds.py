"""Build delivery and tracking via the App Store Connect API.

Uses the Build Upload API (ASC API 4.1+, GA late 2025): a pure-HTTP
reserve/upload/commit flow that replaces altool/Transporter:
  1. POST /v1/buildUploads
  2. POST /v1/buildUploadFiles  -> uploadOperations (chunked PUT targets)
  3. PUT each chunk to the returned URLs
  4. PATCH /v1/buildUploadFiles/{id} uploaded=true
Then GET /v1/builds until processingState leaves PROCESSING.
"""
import os
import time

import requests

TERMINAL_STATES = ("VALID", "FAILED", "INVALID")


class BuildProcessingError(Exception):
    """Raised when a build fails processing or never finishes in time."""


def _default_upload_transport(method, url, data, headers):
    response = requests.request(method, url, data=data, headers=headers)
    response.raise_for_status()


class BuildsManager:
    def __init__(self, client, upload_transport=None, sleep=time.sleep, clock=time.monotonic):
        self.client = client
        self.upload_transport = upload_transport or _default_upload_transport
        self._sleep = sleep
        self._clock = clock

    # -- Build Upload API --------------------------------------------------

    def reserve_upload(self, app_id, version, build_number, platform="IOS"):
        """Reserve a build upload slot (POST /v1/buildUploads). Returns the
        reservation id. Split out from the transfer so the caller can persist
        the reservation write-ahead before moving any bytes."""
        upload = self.client.post(
            "/v1/buildUploads",
            {
                "data": {
                    "type": "buildUploads",
                    "attributes": {
                        "cfBundleShortVersionString": version,
                        "cfBundleVersion": build_number,
                        "platform": platform,
                    },
                    "relationships": {
                        "app": {"data": {"type": "apps", "id": app_id}}
                    },
                }
            },
        )["data"]
        return upload["id"]

    def transfer_reserved(self, reservation_id, file_path):
        """Reserve the file, PUT its chunks, and commit — against an existing
        buildUploads reservation."""
        file_size = os.path.getsize(file_path)
        upload_file = self.client.post(
            "/v1/buildUploadFiles",
            {
                "data": {
                    "type": "buildUploadFiles",
                    "attributes": {
                        "fileName": os.path.basename(file_path),
                        "fileSize": file_size,
                        "assetType": "ASSET",
                        "uti": "com.apple.ipa",
                    },
                    "relationships": {
                        "buildUpload": {
                            "data": {"type": "buildUploads", "id": reservation_id}
                        }
                    },
                }
            },
        )["data"]

        operations = upload_file["attributes"]["uploadOperations"]
        with open(file_path, "rb") as f:
            for operation in operations:
                f.seek(operation["offset"])
                chunk = f.read(operation["length"])
                headers = {
                    h["name"]: h["value"] for h in operation.get("requestHeaders", [])
                }
                self.upload_transport(operation["method"], operation["url"], chunk, headers)

        self.client.patch(
            f"/v1/buildUploadFiles/{upload_file['id']}",
            {
                "data": {
                    "type": "buildUploadFiles",
                    "id": upload_file["id"],
                    "attributes": {"uploaded": True},
                }
            },
        )

    def upload_ipa(self, file_path, version, build_number, app_id, platform="IOS"):
        """Upload a signed .ipa and return the buildUpload reservation id.

        app_id is mandatory: the API rejects reservations without the app
        relationship (409 "must provide a value for the relationship 'app'").
        """
        reservation_id = self.reserve_upload(app_id, version, build_number, platform)
        self.transfer_reserved(reservation_id, file_path)
        return reservation_id

    # -- processing --------------------------------------------------------

    def wait_for_processing(self, app_id, build_number, poll_interval=60, timeout=1800):
        """Poll /v1/builds until the build leaves PROCESSING; return the build resource."""
        deadline = self._clock() + timeout
        while True:
            response = self.client.get(
                "/v1/builds",
                params={
                    "filter[app]": app_id,
                    "filter[version]": build_number,
                    "sort": "-uploadedDate",
                    "limit": 1,
                },
            )
            builds = response.get("data", [])
            if builds:
                state = builds[0]["attributes"].get("processingState")
                if state == "VALID":
                    return builds[0]
                if state in ("FAILED", "INVALID"):
                    raise BuildProcessingError(
                        f"Build {build_number} processing ended in state {state}"
                    )
            if self._clock() >= deadline:
                raise BuildProcessingError(
                    f"Timed out waiting for build {build_number} to finish processing"
                )
            self._sleep(poll_interval)

    def find_build(self, app_id, build_number):
        """Most recent build matching (app, CFBundleVersion). Returns the build
        resource or None. Same filter set as wait_for_processing (proven).

        Note: build numbers reused across marketing versions could in theory
        collide here; the machine mitigates by pinning the build id once
        resolved (never re-resolving by filter afterwards). A dotted
        `filter[preReleaseVersion.version]` was deliberately avoided — its
        support is unverified and a 400 would break every poll.
        """
        params = {
            "filter[app]": app_id,
            "filter[version]": build_number,
            "sort": "-uploadedDate",
            "limit": 1,
        }
        data = self.client.get("/v1/builds", params=params).get("data", [])
        return data[0] if data else None

    def latest_valid_build(self, app_id):
        """Most recently uploaded build in VALID state, or None."""
        response = self.client.get(
            "/v1/builds",
            params={
                "filter[app]": app_id,
                "filter[processingState]": "VALID",
                "sort": "-uploadedDate",
                "limit": 1,
            },
        )
        data = response.get("data", [])
        return data[0] if data else None

    def latest_build_number(self, app_id):
        """Return (best, skipped): the numeric GLOBAL max CFBundleVersion across
        ALL builds (any processing state), and how many non-integer versions were
        skipped. Full pagination (get_all follows links.next) and a NUMERIC max —
        never the API's lexicographic `sort=-version`, which ranks "9" above
        "1000". A global max is >= any per-marketing-version max, so
        `max(floor, best) + 1` is always accepted by App Store Connect.

        The fastlane strategy assumes integer build numbers; a *dotted*/
        alphanumeric version is skipped AND counted (so the caller can warn that
        `best` may be incomplete). An empty/not-yet-populated version is skipped
        but NOT counted (nothing actionable — a build still ingesting)."""
        builds = self.client.get_all("/v1/builds", params={"filter[app]": app_id, "limit": 200})
        best = 0
        skipped = 0
        for build in builds:
            version = ((build.get("attributes") or {}).get("version") or "").strip()
            if version.isascii() and version.isdigit():
                best = max(best, int(version))
            elif version:                       # non-empty but not an integer
                skipped += 1
        return best, skipped

    # -- attributes ----------------------------------------------------------

    def set_uses_non_exempt_encryption(self, build_id, value):
        payload = {
            "data": {
                "type": "builds",
                "id": build_id,
                "attributes": {"usesNonExemptEncryption": value},
            }
        }
        return self.client.patch(f"/v1/builds/{build_id}", payload)["data"]

    def expire_build(self, build_id):
        payload = {
            "data": {"type": "builds", "id": build_id, "attributes": {"expired": True}}
        }
        return self.client.patch(f"/v1/builds/{build_id}", payload)["data"]
