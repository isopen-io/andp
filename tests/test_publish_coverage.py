"""Close the v1.2 code-review coverage gaps (TESTS_MANQUANTS) + two small fixes:
a permanent 4xx on the CDN PUT is NOT retryable, and an empty locale dir is
skipped (no phantom localization / no-op PATCH).
"""
import os

import pytest

from andp.core.errors import from_unexpected
from andp.publish import publish_metadata
from andp.core.release import ReleaseMachine, release_id
from andp.core.state import StateStore
from conftest import FakeResponse, FakeSession, make_test_managers


def _text(root, locale, stem, content):
    d = os.path.join(root, locale)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{stem}.txt"), "w", encoding="utf-8") as f:
        f.write(content)


def _shot(root, locale, display, name):
    d = os.path.join(root, locale, "screenshots", display)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "wb") as f:
        f.write(b"PNG")


def _preview(root, locale, display, name):
    d = os.path.join(root, locale, "previews", display)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "wb") as f:
        f.write(b"MP4")


def _loc(locale, lid):
    return [FakeResponse(200, {"data": [{"id": lid, "attributes": {"locale": locale}}]}),
            FakeResponse(200, {"data": {"id": lid}})]


# -- CDN 4xx is a permanent error, not retryable --------------------------

def test_permanent_4xx_on_cdn_put_is_not_retryable():
    class _HTTPError(Exception):
        pass
    _HTTPError.__name__ = "HTTPError"

    class _Resp:
        status_code = 400
    err = _HTTPError("bad request")
    err.response = _Resp()

    typed = from_unexpected(err)
    assert typed.code == "upload_rejected"
    assert typed.retryable is False


def test_5xx_on_cdn_put_is_retryable():
    class _HTTPError(Exception):
        pass
    _HTTPError.__name__ = "HTTPError"

    class _Resp:
        status_code = 503
    err = _HTTPError("unavailable")
    err.response = _Resp()

    typed = from_unexpected(err)
    assert typed.code == "network_error"
    assert typed.retryable is True


# -- empty locale dir is skipped ------------------------------------------

def test_empty_locale_dir_is_skipped(tmp_path):
    root = str(tmp_path / "m")
    os.makedirs(os.path.join(root, "de-DE"))          # no text, no assets
    _text(root, "en-US", "whatsNew", "Hi")

    session = FakeSession()
    session.queue(*_loc("en-US", "loc-en"))           # only en-US touched
    managers = make_test_managers(session)
    summary = publish_metadata(managers, "app-9", "1.0", root, version_id="ver-1")

    assert "en-US" in summary["locales"]
    assert "de-DE" not in summary["locales"]          # skipped, no API calls


# -- multi-locale, independent processing ---------------------------------

def test_multiple_locales_each_pushed(tmp_path):
    root = str(tmp_path / "m")
    _text(root, "en-US", "whatsNew", "English")
    _text(root, "fr-FR", "whatsNew", "Français")

    session = FakeSession()
    session.queue(*_loc("en-US", "loc-en"), *_loc("fr-FR", "loc-fr"))
    managers = make_test_managers(session)
    summary = publish_metadata(managers, "app-9", "1.0", root, version_id="ver-1")

    assert set(summary["locales"]) == {"en-US", "fr-FR"}


# -- preview skip idempotency (the branch only screenshots covered) -------

def test_existing_preview_is_skipped(tmp_path):
    root = str(tmp_path / "m")
    _preview(root, "en-US", "APP_IPHONE_67", "01.mp4")

    session = FakeSession()
    session.queue(
        *_loc("en-US", "loc-en"),
        FakeResponse(200, {"data": [{"id": "pset-1"}]}),                         # ensure preview set
        FakeResponse(200, {"data": [{"id": "p1", "attributes": {"fileName": "01.mp4"}}]}),  # existing
    )
    managers = make_test_managers(session)
    summary = publish_metadata(managers, "app-9", "1.0", root, version_id="ver-1")

    assert summary["locales"]["en-US"]["previews"] == 0
    assert summary["locales"]["en-US"]["previews_skipped"] == 1
    assert not any(r["method"] == "POST" and r["url"].endswith("/v1/appPreviews")
                   for r in session.requests)


# -- hidden / tooling dirs are ignored ------------------------------------

def test_hidden_and_tooling_dirs_are_ignored(tmp_path):
    root = str(tmp_path / "m")
    _text(root, "en-US", "whatsNew", "Hi")
    os.makedirs(os.path.join(root, ".git"))
    os.makedirs(os.path.join(root, "__MACOSX"))
    # a hidden display-type dir inside screenshots must be ignored too
    os.makedirs(os.path.join(root, "en-US", "screenshots", ".DS_Store_dir"))

    session = FakeSession()
    session.queue(*_loc("en-US", "loc-en"))
    managers = make_test_managers(session)
    summary = publish_metadata(managers, "app-9", "1.0", root, version_id="ver-1")

    assert set(summary["locales"]) == {"en-US"}       # .git / __MACOSX ignored


# -- multi-chunk transfer computes MD5 over all chunks --------------------

def test_transfer_bytes_multi_chunk_checksum(tmp_path):
    from andp.asc.assets import _transfer_bytes
    import hashlib

    f = tmp_path / "img.png"
    f.write_bytes(b"0123456789ABCDEF")   # 16 bytes
    ops = [
        {"method": "PUT", "url": "u1", "offset": 0, "length": 10, "requestHeaders": []},
        {"method": "PUT", "url": "u2", "offset": 10, "length": 6, "requestHeaders": []},
    ]
    sent = []
    checksum = _transfer_bytes(str(f), ops, lambda m, u, d, h: sent.append(d))

    assert sent == [b"0123456789", b"ABCDEF"]
    assert checksum == hashlib.md5(b"0123456789ABCDEF").hexdigest()


# -- existing_filenames follows pagination --------------------------------

def test_existing_filenames_paginates(tmp_path):
    from andp.asc.managers import Managers
    from andp.asc.client import ASCClient

    class _Auth:
        def token(self):
            return "t"

    base = "https://api.appstoreconnect.apple.com"
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "a", "attributes": {"fileName": "01.png"}}],
                           "links": {"next": f"{base}/v1/appScreenshotSets/s/appScreenshots?cursor=2"}}),
        FakeResponse(200, {"data": [{"id": "b", "attributes": {"fileName": "02.png"}}]}),
    )
    managers = Managers(ASCClient(auth=_Auth(), session=session, sleep=lambda s: None))
    names = managers.screenshots.existing_filenames("s")
    assert names == {"01.png", "02.png"}


# -- resume the metadata_pending state after a crash ----------------------

def test_resume_metadata_pending_reruns_push(tmp_path):
    store = StateStore(str(tmp_path / ".andp" / "state"))
    ipa = tmp_path / "App.ipa"
    import plistlib, zipfile
    with zipfile.ZipFile(ipa, "w") as zf:
        zf.writestr("Payload/App.app/Info.plist", plistlib.dumps(
            {"CFBundleIdentifier": "me.demo.app", "CFBundleShortVersionString": "1.0",
             "CFBundleVersion": "1"}))
    root = str(tmp_path / "m"); _text(root, "en-US", "whatsNew", "Hi")

    rid = release_id("primary", "me.demo.app", "1.0", "1")
    base = ReleaseMachine.start(store, make_test_managers(FakeSession()), str(ipa),
                                ship=True, allow_submit=True,
                                metadata_dir=root).snapshot()
    base.update({"state": "metadata_pending", "app_id": "app-9",
                 "build_id": "build-77", "version_id": "ver-1"})
    base["history"].append("metadata_pending")
    store.save(rid, base)

    session = FakeSession()
    session.queue(*_loc("en-US", "loc-en"))   # the push re-runs (pinned version_id)
    m = ReleaseMachine.load(store, make_test_managers(session), rid)
    snap = m.step()
    assert snap["state"] == "awaiting_approval"
