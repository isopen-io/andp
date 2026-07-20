"""Tests for infrastructure/asc/assets.py — upload de screenshots App Store.

Flux officiel : ensure appScreenshotSet → POST /v1/appScreenshots (réservation)
→ PUT des chunks selon uploadOperations → PATCH uploaded=true + checksum MD5.
"""
import hashlib

import pytest

from andp.asc.assets import ScreenshotManager

PNG_BYTES = b"\x89PNG-fake-screenshot-bytes"


class RecordingTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, data, headers):
        self.calls.append({"method": method, "url": url, "data": data, "headers": headers})


@pytest.fixture
def screenshot_file(tmp_path):
    path = tmp_path / "iphone67-01.png"
    path.write_bytes(PNG_BYTES)
    return str(path)


def test_upload_screenshot_full_flow(asc_client, fake_session, fake_response, screenshot_file):
    operations = [{
        "method": "PUT", "url": "https://upload.apple.com/shot-1",
        "offset": 0, "length": len(PNG_BYTES),
        "requestHeaders": [{"name": "Content-Type", "value": "image/png"}],
    }]
    fake_session.queue(
        # aucun set existant pour ce displayType
        fake_response(200, {"data": []}),
        fake_response(201, {"data": {"id": "SET1", "type": "appScreenshotSets"}}),
        fake_response(201, {"data": {"id": "SHOT1", "type": "appScreenshots",
                                     "attributes": {"uploadOperations": operations}}}),
        fake_response(200, {"data": {"id": "SHOT1", "type": "appScreenshots"}}),
    )
    transport = RecordingTransport()
    mgr = ScreenshotManager(asc_client, upload_transport=transport)

    result = mgr.upload_screenshot("VL1", "APP_IPHONE_67", screenshot_file)

    create_set = fake_session.requests[1]["json"]["data"]
    assert create_set["type"] == "appScreenshotSets"
    assert create_set["attributes"] == {"screenshotDisplayType": "APP_IPHONE_67"}
    assert create_set["relationships"]["appStoreVersionLocalization"]["data"] == {
        "type": "appStoreVersionLocalizations", "id": "VL1",
    }

    reserve = fake_session.requests[2]["json"]["data"]
    assert reserve["attributes"] == {
        "fileName": "iphone67-01.png", "fileSize": len(PNG_BYTES),
    }
    assert reserve["relationships"]["appScreenshotSet"]["data"] == {
        "type": "appScreenshotSets", "id": "SET1",
    }

    assert transport.calls[0]["data"] == PNG_BYTES
    assert transport.calls[0]["headers"] == {"Content-Type": "image/png"}

    commit = fake_session.requests[3]
    assert commit["method"] == "PATCH"
    assert commit["url"].endswith("/v1/appScreenshots/SHOT1")
    attributes = commit["json"]["data"]["attributes"]
    assert attributes["uploaded"] is True
    assert attributes["sourceFileChecksum"] == hashlib.md5(PNG_BYTES).hexdigest()

    assert result["id"] == "SHOT1"


def test_upload_screenshot_reuses_existing_set(asc_client, fake_session, fake_response, screenshot_file):
    operations = [{"method": "PUT", "url": "https://upload.apple.com/shot-1",
                   "offset": 0, "length": len(PNG_BYTES), "requestHeaders": []}]
    fake_session.queue(
        fake_response(200, {"data": [{"id": "SET9", "type": "appScreenshotSets",
                                      "attributes": {"screenshotDisplayType": "APP_IPHONE_67"}}]}),
        fake_response(201, {"data": {"id": "SHOT2", "type": "appScreenshots",
                                     "attributes": {"uploadOperations": operations}}}),
        fake_response(200, {"data": {"id": "SHOT2", "type": "appScreenshots"}}),
    )
    mgr = ScreenshotManager(asc_client, upload_transport=RecordingTransport())

    mgr.upload_screenshot("VL1", "APP_IPHONE_67", screenshot_file)

    # pas de POST /v1/appScreenshotSets : le set existant est réutilisé
    reserve = fake_session.requests[1]["json"]["data"]
    assert reserve["relationships"]["appScreenshotSet"]["data"]["id"] == "SET9"
