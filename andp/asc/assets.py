"""App Store screenshot and preview-video upload via the App Store Connect API.

Official asset flow (both screenshots and previews): ensure the asset set for
the display/preview type, reserve the asset (fileName + fileSize [+ mimeType
for previews]), PUT the bytes to the returned uploadOperations, then commit
with uploaded=true + MD5 checksum. Apple then processes the asset
(assetDeliveryState) asynchronously.
"""
import hashlib
import os

import requests

_VIDEO_MIME = {
    ".mov": "video/quicktime",
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
}


def _preview_mime(file_path):
    return _VIDEO_MIME.get(os.path.splitext(file_path)[1].lower(), "video/mp4")


def _default_upload_transport(method, url, data, headers):
    response = requests.request(method, url, data=data, headers=headers)
    response.raise_for_status()


def _transfer_bytes(file_path, upload_operations, transport):
    """PUT each chunk described by uploadOperations; return the MD5 of the bytes."""
    checksum = hashlib.md5()
    with open(file_path, "rb") as f:
        for operation in upload_operations:
            f.seek(operation["offset"])
            chunk = f.read(operation["length"])
            checksum.update(chunk)
            headers = {h["name"]: h["value"] for h in operation.get("requestHeaders", [])}
            transport(operation["method"], operation["url"], chunk, headers)
    return checksum.hexdigest()


class ScreenshotManager:
    def __init__(self, client, upload_transport=None):
        self.client = client
        self.upload_transport = upload_transport or _default_upload_transport

    def ensure_screenshot_set(self, localization_id, display_type):
        response = self.client.get(
            f"/v1/appStoreVersionLocalizations/{localization_id}/appScreenshotSets",
            params={"filter[screenshotDisplayType]": display_type},
        )
        existing = response.get("data", [])
        if existing:
            return existing[0]

        payload = {
            "data": {
                "type": "appScreenshotSets",
                "attributes": {"screenshotDisplayType": display_type},
                "relationships": {
                    "appStoreVersionLocalization": {
                        "data": {
                            "type": "appStoreVersionLocalizations",
                            "id": localization_id,
                        }
                    }
                },
            }
        }
        return self.client.post("/v1/appScreenshotSets", payload)["data"]

    def upload_screenshot(self, localization_id, display_type, file_path):
        screenshot_set = self.ensure_screenshot_set(localization_id, display_type)
        return self.upload_screenshot_to_set(screenshot_set["id"], file_path)

    def upload_screenshot_to_set(self, screenshot_set_id, file_path):
        screenshot_set = {"id": screenshot_set_id}
        file_size = os.path.getsize(file_path)
        screenshot = self.client.post(
            "/v1/appScreenshots",
            {
                "data": {
                    "type": "appScreenshots",
                    "attributes": {
                        "fileName": os.path.basename(file_path),
                        "fileSize": file_size,
                    },
                    "relationships": {
                        "appScreenshotSet": {
                            "data": {
                                "type": "appScreenshotSets",
                                "id": screenshot_set["id"],
                            }
                        }
                    },
                }
            },
        )["data"]

        checksum = _transfer_bytes(
            file_path, screenshot["attributes"]["uploadOperations"], self.upload_transport
        )
        return self.client.patch(
            f"/v1/appScreenshots/{screenshot['id']}",
            {
                "data": {
                    "type": "appScreenshots",
                    "id": screenshot["id"],
                    "attributes": {"uploaded": True, "sourceFileChecksum": checksum},
                }
            },
        )["data"]

    def count_screenshots(self, screenshot_set_id):
        """How many screenshots the set already holds (for idempotent skips)."""
        return len(self.client.get_all(f"/v1/appScreenshotSets/{screenshot_set_id}/appScreenshots"))

    def existing_filenames(self, screenshot_set_id):
        """The set of fileNames already in the set — for per-file idempotency."""
        items = self.client.get_all(f"/v1/appScreenshotSets/{screenshot_set_id}/appScreenshots")
        return {i.get("attributes", {}).get("fileName")
                for i in items if i.get("attributes", {}).get("fileName")}


class PreviewManager:
    """App preview VIDEOS (appPreviewSets / appPreviews)."""

    def __init__(self, client, upload_transport=None):
        self.client = client
        self.upload_transport = upload_transport or _default_upload_transport

    def ensure_preview_set(self, localization_id, preview_type):
        response = self.client.get(
            f"/v1/appStoreVersionLocalizations/{localization_id}/appPreviewSets",
            params={"filter[previewType]": preview_type},
        )
        existing = response.get("data", [])
        if existing:
            return existing[0]
        payload = {
            "data": {
                "type": "appPreviewSets",
                "attributes": {"previewType": preview_type},
                "relationships": {
                    "appStoreVersionLocalization": {
                        "data": {"type": "appStoreVersionLocalizations", "id": localization_id}
                    }
                },
            }
        }
        return self.client.post("/v1/appPreviewSets", payload)["data"]

    def upload_preview(self, localization_id, preview_type, file_path):
        preview_set = self.ensure_preview_set(localization_id, preview_type)
        return self.upload_preview_to_set(preview_set["id"], file_path)

    def upload_preview_to_set(self, preview_set_id, file_path):
        preview_set = {"id": preview_set_id}
        file_size = os.path.getsize(file_path)
        preview = self.client.post(
            "/v1/appPreviews",
            {
                "data": {
                    "type": "appPreviews",
                    "attributes": {
                        "fileName": os.path.basename(file_path),
                        "fileSize": file_size,
                        "mimeType": _preview_mime(file_path),
                    },
                    "relationships": {
                        "appPreviewSet": {
                            "data": {"type": "appPreviewSets", "id": preview_set["id"]}
                        }
                    },
                }
            },
        )["data"]

        checksum = _transfer_bytes(
            file_path, preview["attributes"]["uploadOperations"], self.upload_transport
        )
        return self.client.patch(
            f"/v1/appPreviews/{preview['id']}",
            {
                "data": {
                    "type": "appPreviews",
                    "id": preview["id"],
                    "attributes": {"uploaded": True, "sourceFileChecksum": checksum},
                }
            },
        )["data"]

    def count_previews(self, preview_set_id):
        return len(self.client.get_all(f"/v1/appPreviewSets/{preview_set_id}/appPreviews"))

    def existing_filenames(self, preview_set_id):
        items = self.client.get_all(f"/v1/appPreviewSets/{preview_set_id}/appPreviews")
        return {i.get("attributes", {}).get("fileName")
                for i in items if i.get("attributes", {}).get("fileName")}
