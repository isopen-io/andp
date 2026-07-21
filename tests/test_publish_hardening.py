"""Hardening from the v1.2 code review.

BUG 1: per-FILE idempotency (a partially-filled set must not drop the missing
       screenshot on retry).
BUG 2: service.publish returns a dict on any API/network error (never crashes).
BUG 5: text files are read as UTF-8.
BUG 6: an empty .txt does not overwrite the App Store field with "".
BUG 8: the machine passes the pinned version_id (no re-resolve).
"""
import os

import pytest

from andp import service
from andp.publish import publish_metadata
from andp.asc.client import ASCAPIError
from conftest import FakeResponse, FakeSession, make_test_managers


def _shot(root, locale, display, name, data=b"PNG"):
    d = os.path.join(root, locale, "screenshots", display)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)


def _text(root, locale, stem, content):
    d = os.path.join(root, locale)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{stem}.txt"), "w", encoding="utf-8") as f:
        f.write(content)


# -- BUG 1: per-file idempotency ------------------------------------------

def test_only_missing_screenshots_are_uploaded_on_retry(tmp_path):
    root = str(tmp_path / "m")
    for n in ("01.png", "02.png", "03.png"):
        _shot(root, "en-US", "APP_IPHONE_67", n)

    # Retry pass: 01 and 02 already present in the set; only 03 must upload.
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "loc-en", "attributes": {"locale": "en-US"}}]}),
        FakeResponse(200, {"data": {"id": "loc-en"}}),
        FakeResponse(200, {"data": [{"id": "sset-1", "type": "appScreenshotSets"}]}),  # ensure -> found
        # existing filenames -> 01, 02 already there
        FakeResponse(200, {"data": [
            {"id": "s1", "attributes": {"fileName": "01.png"}},
            {"id": "s2", "attributes": {"fileName": "02.png"}}]}),
        # only 03 reserved + committed
        FakeResponse(201, {"data": {"id": "s3", "attributes": {"uploadOperations": []}}}),
        FakeResponse(200, {"data": {"id": "s3"}}),
    )
    managers = make_test_managers(session)
    summary = publish_metadata(managers, "app-9", "1.0", root, version_id="ver-1")

    assert summary["locales"]["en-US"]["screenshots"] == 1        # only 03
    assert summary["locales"]["en-US"]["screenshots_skipped"] == 2
    reserved = [r for r in session.requests
                if r["method"] == "POST" and r["url"].endswith("/v1/appScreenshots")]
    assert len(reserved) == 1
    assert reserved[0]["json"]["data"]["attributes"]["fileName"] == "03.png"


# -- BUG 2: service.publish never leaks -----------------------------------

def test_service_publish_wraps_api_errors(tmp_path, monkeypatch, ec_private_key_pem):
    from conftest import real_secrets_yaml
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    root = str(tmp_path / "m"); _text(root, "en-US", "whatsNew", "Hi")

    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),                  # find_app
        FakeResponse(409, {"errors": [{"status": "409", "detail": "boom"}]}),  # ensure_version 409
    )
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))

    result = service.publish("me.demo.app", "1.0", root)
    assert result["ok"] is False
    assert result["error"]["code"] == "conflict"   # typed, not a crash


# -- BUG 5/6: encoding + empty file ---------------------------------------

def test_utf8_and_empty_file_handling(tmp_path):
    root = str(tmp_path / "m")
    _text(root, "fr-FR", "whatsNew", "Nouveautés : café ☕ 日本語")
    _text(root, "fr-FR", "description", "   ")   # whitespace-only -> must be ignored

    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "loc-fr", "attributes": {"locale": "fr-FR"}}]}),
        FakeResponse(200, {"data": {"id": "loc-fr"}}),
    )
    managers = make_test_managers(session)
    publish_metadata(managers, "app-9", "1.0", root, version_id="ver-1")

    patch = session.requests[-1]["json"]["data"]["attributes"]
    assert patch["whatsNew"] == "Nouveautés : café ☕ 日本語"
    assert "description" not in patch   # empty file did not overwrite


def test_pinned_version_id_skips_ensure_version(tmp_path):
    root = str(tmp_path / "m"); _text(root, "en-US", "whatsNew", "Hi")
    session = FakeSession()
    session.queue(
        # NO ensure_version call — straight to the localization upsert
        FakeResponse(200, {"data": [{"id": "loc-en", "attributes": {"locale": "en-US"}}]}),
        FakeResponse(200, {"data": {"id": "loc-en"}}),
    )
    managers = make_test_managers(session)
    summary = publish_metadata(managers, "app-9", "1.0", root, version_id="ver-PINNED")
    assert summary["version_id"] == "ver-PINNED"
    assert not any("appStoreVersions" in r["url"] and r["method"] == "GET"
                   and "filter[versionString]" in str(r.get("params", {}))
                   for r in session.requests)
