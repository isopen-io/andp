"""App Store screenshot upload via the App Store Connect API.

Official asset flow: ensure the appScreenshotSet for the display type,
reserve the appScreenshot (fileName + fileSize), PUT the bytes to the
returned uploadOperations, then commit with uploaded=true + MD5 checksum.
Apple then processes the asset (assetDeliveryState) asynchronously.
"""
import hashlib
import os

import requests


def _default_upload_transport(method, url, data, headers):
    response = requests.request(method, url, data=data, headers=headers)
    response.raise_for_status()


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

        checksum = hashlib.md5()
        with open(file_path, "rb") as f:
            for operation in screenshot["attributes"]["uploadOperations"]:
                f.seek(operation["offset"])
                chunk = f.read(operation["length"])
                checksum.update(chunk)
                headers = {
                    h["name"]: h["value"] for h in operation.get("requestHeaders", [])
                }
                self.upload_transport(operation["method"], operation["url"], chunk, headers)

        return self.client.patch(
            f"/v1/appScreenshots/{screenshot['id']}",
            {
                "data": {
                    "type": "appScreenshots",
                    "id": screenshot["id"],
                    "attributes": {
                        "uploaded": True,
                        "sourceFileChecksum": checksum.hexdigest(),
                    },
                }
            },
        )["data"]
