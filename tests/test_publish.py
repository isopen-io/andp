"""Folder-convention publisher: release notes + screenshots + previews per
locale/device, pushed to an App Store version.

Convention:
  <root>/<locale>/whatsNew.txt | description.txt | keywords.txt | ...
  <root>/<locale>/screenshots/<DISPLAY_TYPE>/*.png|jpg
  <root>/<locale>/previews/<DISPLAY_TYPE>/*.mp4|mov
"""
import os

from andp.publish import publish_metadata
from conftest import FakeResponse, FakeSession, make_test_managers


def _tree(root):
    os.makedirs(os.path.join(root, "en-US", "screenshots", "APP_IPHONE_67"))
    os.makedirs(os.path.join(root, "en-US", "previews", "APP_IPHONE_67"))
    with open(os.path.join(root, "en-US", "whatsNew.txt"), "w") as f:
        f.write("Bug fixes and improvements.\n")
    with open(os.path.join(root, "en-US", "description.txt"), "w") as f:
        f.write("A great app.\n")
    with open(os.path.join(root, "en-US", "screenshots", "APP_IPHONE_67", "01.png"), "wb") as f:
        f.write(b"PNGDATA")
    with open(os.path.join(root, "en-US", "previews", "APP_IPHONE_67", "01.mp4"), "wb") as f:
        f.write(b"MP4DATA")


def test_publish_pushes_notes_screenshots_and_previews(tmp_path):
    root = str(tmp_path / "metadata")
    _tree(root)

    session = FakeSession()
    session.queue(
        # ensure_version
        FakeResponse(200, {"data": [{"id": "ver-1", "type": "appStoreVersions",
                                     "attributes": {"appVersionState": "PREPARE_FOR_SUBMISSION"}}]}),
        # upsert_version_localization: GET existing -> found
        FakeResponse(200, {"data": [{"id": "loc-en", "type": "appStoreVersionLocalizations",
                                     "attributes": {"locale": "en-US"}}]}),
        FakeResponse(200, {"data": {"id": "loc-en", "type": "appStoreVersionLocalizations"}}),  # patch
        # screenshots: ensure set (empty -> create), count (0), reserve, commit
        FakeResponse(200, {"data": []}),
        FakeResponse(201, {"data": {"id": "sset-1", "type": "appScreenshotSets"}}),
        FakeResponse(200, {"data": []}),  # count_screenshots -> 0
        FakeResponse(201, {"data": {"id": "shot-1", "attributes": {"uploadOperations": []}}}),
        FakeResponse(200, {"data": {"id": "shot-1"}}),
        # previews: ensure set, count (0), reserve, commit
        FakeResponse(200, {"data": []}),
        FakeResponse(201, {"data": {"id": "pset-1", "type": "appPreviewSets"}}),
        FakeResponse(200, {"data": []}),  # count_previews -> 0
        FakeResponse(201, {"data": {"id": "prev-1", "attributes": {"uploadOperations": []}}}),
        FakeResponse(200, {"data": {"id": "prev-1"}}),
    )
    managers = make_test_managers(session)

    summary = publish_metadata(managers, "app-9", "1.0", root)

    assert summary["version_id"] == "ver-1"
    assert summary["locales"]["en-US"]["metadata"] == "updated"
    assert summary["locales"]["en-US"]["screenshots"] == 1
    assert summary["locales"]["en-US"]["previews"] == 1
    # the localization was patched with whatsNew + description
    patch = session.requests[2]["json"]["data"]["attributes"]
    assert patch["whatsNew"].startswith("Bug fixes")
    assert patch["description"].startswith("A great app")


def test_publish_skips_screenshot_set_that_already_has_assets(tmp_path):
    root = str(tmp_path / "metadata")
    os.makedirs(os.path.join(root, "en-US", "screenshots", "APP_IPHONE_67"))
    with open(os.path.join(root, "en-US", "screenshots", "APP_IPHONE_67", "01.png"), "wb") as f:
        f.write(b"PNGDATA")

    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "ver-1", "attributes": {"appVersionState": "PREPARE_FOR_SUBMISSION"}}]}),
        FakeResponse(200, {"data": [{"id": "loc-en", "attributes": {"locale": "en-US"}}]}),
        FakeResponse(200, {"data": {"id": "loc-en"}}),
        # screenshots: ensure set -> found, existing filenames already has 01.png -> SKIP
        FakeResponse(200, {"data": [{"id": "sset-1", "type": "appScreenshotSets"}]}),
        FakeResponse(200, {"data": [{"id": "existing", "attributes": {"fileName": "01.png"}}]}),
    )
    managers = make_test_managers(session)

    summary = publish_metadata(managers, "app-9", "1.0", root)

    assert summary["locales"]["en-US"]["screenshots"] == 0  # skipped
    # no appScreenshots reservation POST happened
    assert not any(r["method"] == "POST" and r["url"].endswith("/v1/appScreenshots")
                   for r in session.requests)


def test_publish_missing_dir_raises(tmp_path):
    session = FakeSession()
    managers = make_test_managers(session)
    import pytest
    with pytest.raises(FileNotFoundError):
        publish_metadata(managers, "app-9", "1.0", str(tmp_path / "nope"))


def test_publish_reads_deliver_file_names_and_ignores_app_info_files(tmp_path):
    """A fastlane `deliver` tree (release_notes.txt, support_url.txt, …) used to
    lose every snake_case field silently: only description/keywords got through.
    App-info files (name.txt, privacy_url.txt) belong to `store apply`, not to
    the version localization, and must not be sent here."""
    root = tmp_path / "metadata" / "fr-FR"
    root.mkdir(parents=True)
    (root / "release_notes.txt").write_text("Corrections.\n")
    (root / "promotional_text.txt").write_text("Nouveau\n")
    (root / "support_url.txt").write_text("https://acme.io/help\n")
    (root / "marketing_url.txt").write_text("https://acme.io\n")
    (root / "name.txt").write_text("Acme\n")
    (root / "privacy_url.txt").write_text("https://acme.io/privacy\n")
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "ver-1", "attributes": {
            "appVersionState": "PREPARE_FOR_SUBMISSION"}}]}),
        FakeResponse(200, {"data": [{"id": "loc-fr", "attributes": {"locale": "fr-FR"}}]}),
        FakeResponse(200, {"data": {"id": "loc-fr"}}),
    )
    publish_metadata(make_test_managers(session), "app-9", "1.0", str(tmp_path / "metadata"))
    assert session.requests[2]["json"]["data"]["attributes"] == {
        "whatsNew": "Corrections.", "promotionalText": "Nouveau",
        "supportUrl": "https://acme.io/help", "marketingUrl": "https://acme.io"}
