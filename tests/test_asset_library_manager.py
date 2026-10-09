"""AssetLibraryManager — the App Asset Library HTTP contract (API 4.5.1).

Observed 2026-10-09 on me.meeshy.app and encoded here:
- the library's images / videos are listed at /v1/appAssetLibraries/{id}/images
  (the links of GET /v1/apps/{id}/assetLibrary; the OpenAPI file omits them);
- a placement on a live version reports state "ACTIVE", absent from the enum.
"""
from conftest import FakeResponse, FakeSession, make_test_managers


def _mgr(*responses):
    session = FakeSession(list(responses))
    return make_test_managers(session).asset_library, session


def _ok(data, **extra):
    return FakeResponse(200, {"data": data, "links": {}, **extra})


def test_library_id_comes_from_the_app():
    mgr, session = _mgr(_ok({"type": "appAssetLibraries", "id": "LIB"}))
    assert mgr.library_id("APP") == "LIB"
    assert session.requests[0]["url"].endswith("/v1/apps/APP/assetLibrary")


def test_library_assets_are_listed_through_the_observed_links():
    mgr, session = _mgr(_ok([{"id": "i1", "attributes": {"fileName": "a.png", "fileSize": 3,
                                                          "state": "APPROVED"}}]))
    images = mgr.assets("LIB", "IMAGE")
    assert images == [{"id": "i1", "fileName": "a.png", "fileSize": 3, "state": "APPROVED",
                       "mediaType": "IMAGE"}]
    assert session.requests[0]["url"].endswith("/v1/appAssetLibraries/LIB/images")


def test_placements_are_read_in_display_order_with_their_files():
    mgr, session = _mgr(_ok(
        [{"id": "p2", "attributes": {"mediaType": "IMAGE", "placementType": "APP_SCREENSHOT",
                                     "placementGroup": "IPHONE_DUO_PROFILE", "state": "ACTIVE"},
          "relationships": {"image": {"data": {"type": "appAssetLibraryImages", "id": "i2"}}}}],
        included=[{"type": "appAssetLibraryImages", "id": "i2",
                   "attributes": {"fileName": "02.png", "fileSize": 9}}]))
    placements = mgr.placements("LOC")
    assert placements == [{"id": "p2", "placementType": "APP_SCREENSHOT",
                           "placementGroup": "IPHONE_DUO_PROFILE", "state": "ACTIVE",
                           "mediaType": "IMAGE", "mediaId": "i2", "fileName": "02.png",
                           "fileSize": 9}]
    params = session.requests[0]["params"]
    assert params["sort"] == "placementGroupPosition" and "image" in params["include"]
    assert session.requests[0]["url"].endswith("/v1/appStoreVersionLocalizations/LOC/placements")


def test_image_upload_reserves_puts_and_marks_uploaded(tmp_path):
    path = tmp_path / "01.png"
    path.write_bytes(b"0123456789")
    sent = []
    mgr, session = _mgr(
        FakeResponse(201, {"data": {"id": "img", "attributes": {"uploadOperations": [
            {"method": "PUT", "url": "https://up/1", "offset": 0, "length": 10,
             "requestHeaders": [{"name": "Content-Type", "value": "image/png"}]}]}}}),
        _ok({"id": "img", "attributes": {"state": "UPLOAD_COMPLETE"}}))
    mgr.upload_transport = lambda *a: sent.append(a)
    asset = mgr.upload("LIB", str(path), "APP_SCREENSHOTS_AND_PREVIEWS")
    create = session.requests[0]
    assert create["url"].endswith("/v1/appAssetLibraryImages")
    assert create["json"]["data"]["attributes"] == {
        "category": "APP_SCREENSHOTS_AND_PREVIEWS", "fileName": "01.png", "fileSize": 10,
        "referenceName": "01.png"}
    assert create["json"]["data"]["relationships"]["assetLibrary"]["data"] == {
        "type": "appAssetLibraries", "id": "LIB"}
    assert sent and sent[0][0] == "PUT"
    commit = session.requests[1]
    assert commit["method"] == "PATCH" and commit["url"].endswith("/v1/appAssetLibraryImages/img")
    assert commit["json"]["data"]["attributes"] == {"uploaded": True}
    assert asset["id"] == "img"


def test_a_video_goes_to_the_video_resource(tmp_path):
    path = tmp_path / "01.mp4"
    path.write_bytes(b"vid")
    mgr, session = _mgr(
        FakeResponse(201, {"data": {"id": "vid", "attributes": {"uploadOperations": []}}}),
        _ok({"id": "vid"}))
    mgr.upload("LIB", str(path), "APP_SCREENSHOTS_AND_PREVIEWS")
    assert session.requests[0]["url"].endswith("/v1/appAssetLibraryVideos")
    assert session.requests[0]["json"]["data"]["type"] == "appAssetLibraryVideos"


def test_placement_links_the_asset_to_the_version_localization():
    mgr, session = _mgr(_ok({"id": "pl"}))
    mgr.place("LOC", "APP_SCREENSHOT", "IPHONE_DUO_PROFILE", "IMAGE", "img")
    body = session.requests[0]["json"]["data"]
    assert body["attributes"] == {"placementType": "APP_SCREENSHOT",
                                  "placementGroup": "IPHONE_DUO_PROFILE"}
    assert body["relationships"]["image"]["data"] == {"type": "appAssetLibraryImages", "id": "img"}
    assert body["relationships"]["appStoreVersionLocalization"]["data"] == {
        "type": "appStoreVersionLocalizations", "id": "LOC"}


def test_ordering_request_lists_the_placements_in_order():
    mgr, session = _mgr(FakeResponse(201, {"data": {"id": "ord"}}))
    mgr.order("LOC", "IPHONE_DUO_PROFILE", ["p2", "p1"])
    body = session.requests[0]["json"]["data"]
    assert body["type"] == "appAssetLibraryPlacementOrderingRequests"
    assert body["attributes"] == {"placementGroup": "IPHONE_DUO_PROFILE"}
    assert [r["id"] for r in body["relationships"]["orderedPlacements"]["data"]] == ["p2", "p1"]


def test_remove_placement_deletes_it():
    mgr, session = _mgr(FakeResponse(204, None))
    mgr.unplace("pl")
    assert session.requests[0]["method"] == "DELETE"
    assert session.requests[0]["url"].endswith("/v1/appAssetLibraryPlacements/pl")


def test_ref_data_is_read_once_and_cached():
    mgr, session = _mgr(_ok([{"id": "1", "attributes": {"imageSpecs": [], "videoSpecs": [],
                                                        "placementTypes": [], "features": [],
                                                        "placementProfileGroups": [],
                                                        "displayClasses": []}}]))
    first = mgr.ref_data()
    second = mgr.ref_data()
    assert first is second and len(session.requests) == 1
    assert set(first) == {"specs", "mappings", "categories", "limits", "groups",
                          "display_classes"}
