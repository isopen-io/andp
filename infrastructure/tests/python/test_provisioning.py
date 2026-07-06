"""Tests for infrastructure/asc/provisioning.py — App IDs, capabilities, certificats, profils, devices.

Référence : App Store Connect API — bundleIds, bundleIdCapabilities,
certificates (csrContent PEM), profiles (POST uniquement, pas de PATCH), devices.
"""
from provisioning import ProvisioningManager


def test_register_bundle_id_posts_identifier(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(201, {"data": {"id": "BID1", "type": "bundleIds",
                                     "attributes": {"identifier": "me.meeshy.app"}}})
    )
    mgr = ProvisioningManager(asc_client)

    result = mgr.register_bundle_id("me.meeshy.app", "Meeshy", platform="IOS")

    request = fake_session.requests[0]
    assert request["url"].endswith("/v1/bundleIds")
    assert request["json"]["data"]["type"] == "bundleIds"
    assert request["json"]["data"]["attributes"] == {
        "identifier": "me.meeshy.app", "name": "Meeshy", "platform": "IOS",
    }
    assert result["id"] == "BID1"


def test_find_bundle_id_filters_by_identifier(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(200, {"data": [{"id": "BID1", "type": "bundleIds"}]})
    )
    mgr = ProvisioningManager(asc_client)

    found = mgr.find_bundle_id("me.meeshy.app")

    assert fake_session.requests[0]["params"]["filter[identifier]"] == "me.meeshy.app"
    assert found["id"] == "BID1"


def test_find_bundle_id_returns_none_when_absent(asc_client, fake_session, fake_response):
    fake_session.queue(fake_response(200, {"data": []}))
    assert ProvisioningManager(asc_client).find_bundle_id("me.absent") is None


def test_enable_capability_links_bundle_id(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(201, {"data": {"id": "CAP1", "type": "bundleIdCapabilities"}})
    )
    mgr = ProvisioningManager(asc_client)

    mgr.enable_capability("BID1", "PUSH_NOTIFICATIONS")

    data = fake_session.requests[0]["json"]["data"]
    assert data["type"] == "bundleIdCapabilities"
    assert data["attributes"]["capabilityType"] == "PUSH_NOTIFICATIONS"
    assert data["relationships"]["bundleId"]["data"] == {"type": "bundleIds", "id": "BID1"}


def test_create_certificate_sends_csr_content(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(201, {"data": {"id": "CERT1", "type": "certificates",
                                     "attributes": {"certificateContent": "BASE64DER"}}})
    )
    mgr = ProvisioningManager(asc_client)

    cert = mgr.create_certificate("CSR_PEM_BODY", "DISTRIBUTION")

    attributes = fake_session.requests[0]["json"]["data"]["attributes"]
    assert attributes == {"csrContent": "CSR_PEM_BODY", "certificateType": "DISTRIBUTION"}
    assert cert["attributes"]["certificateContent"] == "BASE64DER"


def test_register_device(asc_client, fake_session, fake_response):
    fake_session.queue(fake_response(201, {"data": {"id": "DEV1", "type": "devices"}}))
    mgr = ProvisioningManager(asc_client)

    mgr.register_device("iPhone de Jules", "00008120-000000000000001E", platform="IOS")

    attributes = fake_session.requests[0]["json"]["data"]["attributes"]
    assert attributes["udid"] == "00008120-000000000000001E"
    assert attributes["name"] == "iPhone de Jules"


def test_create_profile_links_bundle_certificates_devices(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(201, {"data": {"id": "PROF1", "type": "profiles",
                                     "attributes": {"profileContent": "BASE64PROFILE"}}})
    )
    mgr = ProvisioningManager(asc_client)

    profile = mgr.create_profile(
        "Meeshy AppStore", "IOS_APP_STORE", bundle_id="BID1",
        certificate_ids=["CERT1"], device_ids=["DEV1"],
    )

    data = fake_session.requests[0]["json"]["data"]
    assert data["attributes"] == {"name": "Meeshy AppStore", "profileType": "IOS_APP_STORE"}
    rel = data["relationships"]
    assert rel["bundleId"]["data"] == {"type": "bundleIds", "id": "BID1"}
    assert rel["certificates"]["data"] == [{"type": "certificates", "id": "CERT1"}]
    assert rel["devices"]["data"] == [{"type": "devices", "id": "DEV1"}]
    assert profile["attributes"]["profileContent"] == "BASE64PROFILE"


def test_create_profile_without_devices_omits_relationship(asc_client, fake_session, fake_response):
    """Un profil App Store ne référence pas de devices (réservés au dev/ad hoc)."""
    fake_session.queue(fake_response(201, {"data": {"id": "PROF2", "type": "profiles"}}))
    mgr = ProvisioningManager(asc_client)

    mgr.create_profile("Meeshy AppStore", "IOS_APP_STORE",
                       bundle_id="BID1", certificate_ids=["CERT1"])

    assert "devices" not in fake_session.requests[0]["json"]["data"]["relationships"]


def test_delete_profile(asc_client, fake_session, fake_response):
    fake_session.queue(fake_response(204))
    ProvisioningManager(asc_client).delete_profile("PROF1")

    request = fake_session.requests[0]
    assert request["method"] == "DELETE"
    assert request["url"].endswith("/v1/profiles/PROF1")
