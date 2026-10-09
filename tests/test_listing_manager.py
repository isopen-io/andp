"""ListingManager — the App Store Connect resources behind a listing.

Every payload below follows API 4.5.1 (OpenAPI spec of 2026-10-06): the create
requests' mandatory relationships, the attribute names, the upload/commit flow.
"""
from conftest import FakeResponse, FakeSession, make_test_managers


def _mgr(*responses):
    session = FakeSession(list(responses))
    return make_test_managers(session).listing, session


def _ok(data, **extra):
    return FakeResponse(200, {"data": data, "links": {}, **extra})


def test_editable_app_info_prefers_the_editable_record():
    mgr, _ = _mgr(_ok([
        {"id": "live", "attributes": {"state": "READY_FOR_DISTRIBUTION"}},
        {"id": "next", "attributes": {"state": "PREPARE_FOR_SUBMISSION"}}]))
    info, editable = mgr.editable_app_info("APP")
    assert info["id"] == "next" and editable is True


def test_editable_app_info_reports_a_locked_listing():
    mgr, _ = _mgr(_ok([{"id": "live", "attributes": {"state": "READY_FOR_DISTRIBUTION"}}]))
    info, editable = mgr.editable_app_info("APP")
    assert info["id"] == "live" and editable is False


def test_categories_are_read_from_the_included_relationships():
    mgr, session = _mgr(_ok({"id": "ai", "relationships": {
        "primaryCategory": {"data": {"type": "appCategories", "id": "SOCIAL_NETWORKING"}},
        "secondaryCategory": {"data": None},
        "primarySubcategoryOne": {"data": None}}}))
    cats = mgr.categories("ai")
    assert cats["primaryCategory"] == "SOCIAL_NETWORKING"
    assert cats["secondaryCategory"] is None
    assert "primaryCategory" in session.requests[0]["params"]["include"]


def test_update_categories_patches_relationships_and_can_clear_one():
    mgr, session = _mgr(_ok({"id": "ai"}))
    mgr.update_categories("ai", {"primaryCategory": "EDUCATION", "secondaryCategory": None})
    req = session.requests[0]
    assert req["method"] == "PATCH" and req["url"].endswith("/v1/appInfos/ai")
    rels = req["json"]["data"]["relationships"]
    assert rels["primaryCategory"] == {"data": {"type": "appCategories", "id": "EDUCATION"}}
    assert rels["secondaryCategory"] == {"data": None}


def test_app_info_localization_is_created_with_its_app_info():
    mgr, session = _mgr(_ok({"id": "l1"}))
    mgr.create_app_info_localization("ai", "fr-FR", {"name": "Acme"})
    body = session.requests[0]["json"]["data"]
    assert session.requests[0]["url"].endswith("/v1/appInfoLocalizations")
    assert body["attributes"] == {"locale": "fr-FR", "name": "Acme"}
    assert body["relationships"]["appInfo"]["data"] == {"type": "appInfos", "id": "ai"}


def test_review_detail_is_created_when_the_version_has_none():
    mgr, session = _mgr(_ok(None), _ok({"id": "rd"}))
    assert mgr.review_detail("v1") is None
    mgr.save_review_detail("v1", None, {"contactFirstName": "Ada"})
    req = session.requests[1]
    assert req["method"] == "POST" and req["url"].endswith("/v1/appStoreReviewDetails")
    assert req["json"]["data"]["relationships"]["appStoreVersion"]["data"]["id"] == "v1"


def test_review_detail_is_patched_when_present():
    mgr, session = _mgr(_ok({"id": "rd"}))
    mgr.save_review_detail("v1", "rd", {"notes": "Tap chat."})
    req = session.requests[0]
    assert req["method"] == "PATCH" and req["url"].endswith("/v1/appStoreReviewDetails/rd")


def test_review_attachment_reserve_upload_commit(tmp_path):
    path = tmp_path / "demo.mov"
    path.write_bytes(b"0123456789")
    sent = []
    mgr, session = _mgr(
        FakeResponse(201, {"data": {"id": "att", "attributes": {"uploadOperations": [
            {"method": "PUT", "url": "https://up/1", "offset": 0, "length": 10,
             "requestHeaders": []}]}}}),
        _ok({"id": "att"}))
    mgr.upload_transport = lambda *a: sent.append(a)
    mgr.upload_review_attachment("rd", str(path))
    create = session.requests[0]["json"]["data"]
    assert create["attributes"] == {"fileName": "demo.mov", "fileSize": 10}
    assert create["relationships"]["appStoreReviewDetail"]["data"]["id"] == "rd"
    assert sent and sent[0][0] == "PUT"
    commit = session.requests[1]
    assert commit["url"].endswith("/v1/appStoreReviewAttachments/att")
    assert commit["json"]["data"]["attributes"]["uploaded"] is True
    assert len(commit["json"]["data"]["attributes"]["sourceFileChecksum"]) == 32


def test_phased_release_create_and_delete():
    mgr, session = _mgr(_ok({"id": "pr"}), FakeResponse(204, None))
    mgr.create_phased_release("v1")
    mgr.delete_phased_release("pr")
    body = session.requests[0]["json"]["data"]
    assert body["attributes"] == {"phasedReleaseState": "INACTIVE"}
    assert body["relationships"]["appStoreVersion"]["data"]["id"] == "v1"
    assert session.requests[1]["method"] == "DELETE"


def test_accessibility_declaration_is_created_then_published():
    mgr, session = _mgr(_ok({"id": "acc"}), _ok({"id": "acc"}))
    mgr.declare_accessibility("APP", "IPHONE", None, {"supportsVoiceover": True})
    create, publish = session.requests
    assert create["json"]["data"]["attributes"] == {"deviceFamily": "IPHONE",
                                                    "supportsVoiceover": True}
    assert create["json"]["data"]["relationships"]["app"]["data"]["id"] == "APP"
    assert publish["method"] == "PATCH"
    assert publish["json"]["data"]["attributes"] == {"publish": True}


def test_accessibility_draft_is_updated_and_published_in_one_patch():
    mgr, session = _mgr(_ok({"id": "acc"}))
    mgr.declare_accessibility("APP", "IPAD", "acc", {"supportsLargerText": False})
    attrs = session.requests[0]["json"]["data"]["attributes"]
    assert attrs == {"supportsLargerText": False, "publish": True}


def test_encryption_declarations_are_listed_by_app_filter():
    # Observed 2026-10-09: /v1/apps/{id}/appEncryptionDeclarations answers 404
    # ("The relationship 'appEncryptionDeclarations' does not exist").
    mgr, session = _mgr(_ok([{"id": "e1", "attributes": {"exempt": True}}]))
    assert mgr.encryption_declarations("APP")[0]["id"] == "e1"
    assert session.requests[0]["url"].endswith("/v1/appEncryptionDeclarations")
    assert session.requests[0]["params"]["filter[app]"] == "APP"


def test_encryption_declaration_create_payload():
    mgr, session = _mgr(_ok({"id": "e2"}))
    mgr.create_encryption_declaration("APP", {
        "appDescription": "d", "containsProprietaryCryptography": False,
        "containsThirdPartyCryptography": True, "availableOnFrenchStore": True})
    body = session.requests[0]["json"]["data"]
    assert body["type"] == "appEncryptionDeclarations"
    assert body["relationships"]["app"]["data"]["id"] == "APP"


def test_eula_create_update_delete():
    mgr, session = _mgr(_ok({"id": "eu"}), _ok({"id": "eu"}), FakeResponse(204, None))
    mgr.save_eula("APP", None, "Terms", ["FRA", "USA"])
    mgr.save_eula("APP", "eu", "Terms v2", ["FRA"])
    mgr.delete_eula("eu")
    create = session.requests[0]["json"]["data"]
    assert create["relationships"]["app"]["data"]["id"] == "APP"
    assert [t["id"] for t in create["relationships"]["territories"]["data"]] == ["FRA", "USA"]
    update = session.requests[1]
    assert update["method"] == "PATCH" and update["json"]["data"]["attributes"] == {
        "agreementText": "Terms v2"}
    assert session.requests[2]["method"] == "DELETE"


def test_territory_age_ratings_are_summarised():
    mgr, _ = _mgr(_ok([
        {"attributes": {"appStoreAgeRating": "THIRTEEN_PLUS"}},
        {"attributes": {"appStoreAgeRating": "THIRTEEN_PLUS"}},
        {"attributes": {"appStoreAgeRating": "SIXTEEN_PLUS"}}]))
    assert mgr.territory_age_ratings("ai") == {"THIRTEEN_PLUS": 2, "SIXTEEN_PLUS": 1}


def test_update_app_and_version_patch_their_resources():
    mgr, session = _mgr(_ok({"id": "APP"}), _ok({"id": "v1"}))
    mgr.update_app("APP", {"contentRightsDeclaration": "USES_THIRD_PARTY_CONTENT"})
    mgr.update_version("v1", {"copyright": "2026 Acme"})
    assert session.requests[0]["url"].endswith("/v1/apps/APP")
    assert session.requests[0]["json"]["data"]["type"] == "apps"
    assert session.requests[1]["url"].endswith("/v1/appStoreVersions/v1")
