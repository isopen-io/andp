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
from media_files import mp4, png

# The App Asset Library lookup failing sends the visuals down the legacy
# appScreenshotSets / appPreviewSets path — the path these tests exercise.
NO_LIBRARY = FakeResponse(404, {"errors": [{"status": "404", "detail": "not found"}]})


def _tree(root):
    os.makedirs(os.path.join(root, "en-US", "screenshots", "APP_IPHONE_67"))
    os.makedirs(os.path.join(root, "en-US", "previews", "APP_IPHONE_67"))
    with open(os.path.join(root, "en-US", "whatsNew.txt"), "w") as f:
        f.write("Bug fixes and improvements.\n")
    with open(os.path.join(root, "en-US", "description.txt"), "w") as f:
        f.write("A great app.\n")
    png(os.path.join(root, "en-US", "screenshots", "APP_IPHONE_67", "01.png"), 1290, 2796)
    mp4(os.path.join(root, "en-US", "previews", "APP_IPHONE_67", "01.mp4"), 886, 1920, 20)


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
        NO_LIBRARY,
        # plan (GET only): preview set, screenshot set — none yet
        FakeResponse(200, {"data": []}),
        FakeResponse(200, {"data": []}),
        # apply previews: ensure set (empty -> create), reserve, commit
        FakeResponse(200, {"data": []}),
        FakeResponse(201, {"data": {"id": "pset-1", "type": "appPreviewSets"}}),
        FakeResponse(201, {"data": {"id": "prev-1", "attributes": {"uploadOperations": []}}}),
        FakeResponse(200, {"data": {"id": "prev-1"}}),
        # apply screenshots: ensure set (empty -> create), reserve, commit
        FakeResponse(200, {"data": []}),
        FakeResponse(201, {"data": {"id": "sset-1", "type": "appScreenshotSets"}}),
        FakeResponse(201, {"data": {"id": "shot-1", "attributes": {"uploadOperations": []}}}),
        FakeResponse(200, {"data": {"id": "shot-1"}}),
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
    png(os.path.join(root, "en-US", "screenshots", "APP_IPHONE_67", "01.png"), 1290, 2796)

    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "ver-1", "attributes": {"appVersionState": "PREPARE_FOR_SUBMISSION"}}]}),
        FakeResponse(200, {"data": [{"id": "loc-en", "attributes": {"locale": "en-US"}}]}),
        FakeResponse(200, {"data": {"id": "loc-en"}}),
        NO_LIBRARY,
        # plan: set found, existing filenames already has 01.png -> SKIP
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


def test_publish_places_iphone_duo_screenshots_through_the_asset_library(tmp_path):
    root = tmp_path / "metadata"
    (root / "fr-FR" / "screenshots" / "IPHONE_DUO").mkdir(parents=True)
    png(str(root / "fr-FR" / "screenshots" / "IPHONE_DUO" / "01.png"), 2007, 2853)
    ref = {"placementTypes": [{"placementTypeId": "APP_SCREENSHOT",
                               "acceptsAssetCategories": ["APP_SCREENSHOTS_AND_PREVIEWS"],
                               "specMappings": []}]}
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "ver-1", "attributes": {
            "appVersionState": "PREPARE_FOR_SUBMISSION"}}]}),
        FakeResponse(200, {"data": [{"id": "loc-fr", "attributes": {"locale": "fr-FR"}}]}),
        FakeResponse(200, {"data": {"id": "loc-fr"}}),
        FakeResponse(200, {"data": {"type": "appAssetLibraries", "id": "LIB"}}),
        FakeResponse(200, {"data": [{"id": "1", "attributes": ref}]}),        # ref data
        FakeResponse(200, {"data": [], "links": {}}),                         # library images
        FakeResponse(200, {"data": [], "links": {}}),                         # library videos
        FakeResponse(200, {"data": []}),                                      # placements
        FakeResponse(201, {"data": {"id": "img-1", "attributes": {"uploadOperations": []}}}),
        FakeResponse(200, {"data": {"id": "img-1", "attributes": {"fileName": "01.png"}}}),
        FakeResponse(201, {"data": {"id": "pl-1"}}),                          # placement
        FakeResponse(200, {"data": [{"id": "pl-1", "attributes": {
            "placementType": "APP_SCREENSHOT", "placementGroup": "IPHONE_DUO_PROFILE",
            "mediaType": "IMAGE"}, "relationships": {"image": {"data": {"id": "img-1"}}}}],
            "included": [{"type": "appAssetLibraryImages", "id": "img-1",
                          "attributes": {"fileName": "01.png"}}]}),           # re-read order
    )
    summary = publish_metadata(make_test_managers(session), "app-9", "1.0", str(root))
    assert summary["media_backend"] == "asset_library"
    assert summary["locales"]["fr-FR"]["screenshots"] == 1
    place = session.requests[10]
    assert place["url"].endswith("/v1/appAssetLibraryPlacements")
    assert place["json"]["data"]["attributes"] == {"placementType": "APP_SCREENSHOT",
                                                   "placementGroup": "IPHONE_DUO_PROFILE"}
    assert len(session.requests) == 12                                       # no ordering needed


def test_publish_refuses_a_wrong_size_before_any_request(tmp_path):
    folder = tmp_path / "metadata" / "fr-FR" / "screenshots" / "IPHONE_DUO"
    folder.mkdir(parents=True)
    png(str(folder / "01.png"), 1290, 2796)
    session = FakeSession()
    import pytest
    from andp.errors import AndpError
    with pytest.raises(AndpError) as err:
        publish_metadata(make_test_managers(session), "app-9", "1.0", str(tmp_path / "metadata"))
    assert err.value.code == "invalid_metadata" and "1290×2796" in err.value.message
    assert session.requests == []
