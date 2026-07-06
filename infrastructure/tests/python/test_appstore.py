"""Tests for infrastructure/asc/appstore.py — versions App Store, localisations,
build, Review Submissions (API moderne) et release."""
import pytest

from appstore import AppStoreManager


def test_ensure_version_returns_existing(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(200, {"data": [{"id": "V1", "type": "appStoreVersions",
                                      "attributes": {"versionString": "1.2.0"}}]})
    )
    version = AppStoreManager(asc_client).ensure_version("APP1", "1.2.0")

    params = fake_session.requests[0]["params"]
    assert params["filter[versionString]"] == "1.2.0"
    assert version["id"] == "V1"
    assert len(fake_session.requests) == 1


def test_ensure_version_creates_when_missing(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(200, {"data": []}),
        fake_response(201, {"data": {"id": "V2", "type": "appStoreVersions"}}),
    )
    version = AppStoreManager(asc_client).ensure_version(
        "APP1", "1.3.0", platform="IOS", release_type="AFTER_APPROVAL"
    )

    data = fake_session.requests[1]["json"]["data"]
    assert data["type"] == "appStoreVersions"
    assert data["attributes"] == {
        "versionString": "1.3.0", "platform": "IOS", "releaseType": "AFTER_APPROVAL",
    }
    assert data["relationships"]["app"]["data"] == {"type": "apps", "id": "APP1"}
    assert version["id"] == "V2"


def test_update_version_localization_creates_when_missing(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(200, {"data": []}),
        fake_response(201, {"data": {"id": "VL1", "type": "appStoreVersionLocalizations"}}),
    )
    mgr = AppStoreManager(asc_client)

    mgr.update_version_localization("V1", "fr-FR", {
        "description": "Meeshy traduit vos conversations.",
        "keywords": "traduction,messagerie",
        "whatsNew": "Corrections de bugs.",
    })

    create = fake_session.requests[1]["json"]["data"]
    assert create["attributes"]["locale"] == "fr-FR"
    assert create["attributes"]["description"] == "Meeshy traduit vos conversations."
    assert create["relationships"]["appStoreVersion"]["data"] == {
        "type": "appStoreVersions", "id": "V1",
    }


def test_update_version_localization_patches_existing(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(200, {"data": [{"id": "VL1", "type": "appStoreVersionLocalizations",
                                      "attributes": {"locale": "fr-FR"}}]}),
        fake_response(200, {"data": {"id": "VL1", "type": "appStoreVersionLocalizations"}}),
    )
    mgr = AppStoreManager(asc_client)

    mgr.update_version_localization("V1", "fr-FR", {"whatsNew": "Nouvelle traduction hors-ligne."})

    update = fake_session.requests[1]
    assert update["method"] == "PATCH"
    assert update["url"].endswith("/v1/appStoreVersionLocalizations/VL1")
    assert update["json"]["data"]["attributes"] == {"whatsNew": "Nouvelle traduction hors-ligne."}


def test_attach_build_patches_relationship(asc_client, fake_session, fake_response):
    fake_session.queue(fake_response(204))
    AppStoreManager(asc_client).attach_build("V1", "B1")

    request = fake_session.requests[0]
    assert request["method"] == "PATCH"
    assert request["url"].endswith("/v1/appStoreVersions/V1/relationships/build")
    assert request["json"]["data"] == {"type": "builds", "id": "B1"}


def test_submit_for_review_runs_modern_flow(asc_client, fake_session, fake_response):
    """reviewSubmissions → reviewSubmissionItems → submitted=true."""
    fake_session.queue(
        fake_response(201, {"data": {"id": "RS1", "type": "reviewSubmissions"}}),
        fake_response(201, {"data": {"id": "RSI1", "type": "reviewSubmissionItems"}}),
        fake_response(200, {"data": {"id": "RS1", "type": "reviewSubmissions",
                                     "attributes": {"state": "WAITING_FOR_REVIEW"}}}),
    )
    submission = AppStoreManager(asc_client).submit_for_review("APP1", "V1", platform="IOS")

    create = fake_session.requests[0]["json"]["data"]
    assert create["type"] == "reviewSubmissions"
    assert create["attributes"] == {"platform": "IOS"}
    assert create["relationships"]["app"]["data"] == {"type": "apps", "id": "APP1"}

    item = fake_session.requests[1]["json"]["data"]
    assert item["type"] == "reviewSubmissionItems"
    assert item["relationships"]["reviewSubmission"]["data"] == {
        "type": "reviewSubmissions", "id": "RS1",
    }
    assert item["relationships"]["appStoreVersion"]["data"] == {
        "type": "appStoreVersions", "id": "V1",
    }

    submit = fake_session.requests[2]
    assert submit["method"] == "PATCH"
    assert submit["url"].endswith("/v1/reviewSubmissions/RS1")
    assert submit["json"]["data"]["attributes"] == {"submitted": True}
    assert submission["attributes"]["state"] == "WAITING_FOR_REVIEW"


def test_enable_phased_release(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(201, {"data": {"id": "PR1", "type": "appStoreVersionPhasedReleases"}})
    )
    AppStoreManager(asc_client).enable_phased_release("V1")

    data = fake_session.requests[0]["json"]["data"]
    assert data["type"] == "appStoreVersionPhasedReleases"
    assert data["relationships"]["appStoreVersion"]["data"] == {
        "type": "appStoreVersions", "id": "V1",
    }


def test_request_release(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(201, {"data": {"id": "RR1", "type": "appStoreVersionReleaseRequests"}})
    )
    AppStoreManager(asc_client).request_release("V1")

    data = fake_session.requests[0]["json"]["data"]
    assert data["type"] == "appStoreVersionReleaseRequests"
    assert data["relationships"]["appStoreVersion"]["data"] == {
        "type": "appStoreVersions", "id": "V1",
    }
