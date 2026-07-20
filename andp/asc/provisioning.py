"""Provisioning via the App Store Connect API: bundle IDs, capabilities,
certificates, devices and provisioning profiles.

API notes: profiles cannot be PATCHed (delete + recreate); devices cannot be
deleted, only disabled via PATCH.
"""


def _first_or_none(response):
    data = response.get("data", [])
    return data[0] if data else None


class ProvisioningManager:
    def __init__(self, client):
        self.client = client

    # -- bundle IDs ------------------------------------------------------

    def register_bundle_id(self, identifier, name, platform="IOS"):
        payload = {
            "data": {
                "type": "bundleIds",
                "attributes": {"identifier": identifier, "name": name, "platform": platform},
            }
        }
        return self.client.post("/v1/bundleIds", payload)["data"]

    def find_bundle_id(self, identifier):
        response = self.client.get(
            "/v1/bundleIds", params={"filter[identifier]": identifier}
        )
        return _first_or_none(response)

    def enable_capability(self, bundle_id, capability_type, settings=None):
        attributes = {"capabilityType": capability_type}
        if settings:
            attributes["settings"] = settings
        payload = {
            "data": {
                "type": "bundleIdCapabilities",
                "attributes": attributes,
                "relationships": {
                    "bundleId": {"data": {"type": "bundleIds", "id": bundle_id}}
                },
            }
        }
        return self.client.post("/v1/bundleIdCapabilities", payload)["data"]

    # -- certificates ----------------------------------------------------

    def create_certificate(self, csr_content, certificate_type):
        payload = {
            "data": {
                "type": "certificates",
                "attributes": {
                    "csrContent": csr_content,
                    "certificateType": certificate_type,
                },
            }
        }
        return self.client.post("/v1/certificates", payload)["data"]

    def list_certificates(self, certificate_type=None):
        params = {}
        if certificate_type:
            params["filter[certificateType]"] = certificate_type
        return self.client.get_all("/v1/certificates", params=params or None)

    # -- devices ---------------------------------------------------------

    def register_device(self, name, udid, platform="IOS"):
        payload = {
            "data": {
                "type": "devices",
                "attributes": {"name": name, "udid": udid, "platform": platform},
            }
        }
        return self.client.post("/v1/devices", payload)["data"]

    def list_devices(self):
        return self.client.get_all("/v1/devices")

    # -- profiles --------------------------------------------------------

    def create_profile(self, name, profile_type, bundle_id, certificate_ids, device_ids=None):
        relationships = {
            "bundleId": {"data": {"type": "bundleIds", "id": bundle_id}},
            "certificates": {
                "data": [{"type": "certificates", "id": cid} for cid in certificate_ids]
            },
        }
        if device_ids:
            relationships["devices"] = {
                "data": [{"type": "devices", "id": did} for did in device_ids]
            }
        payload = {
            "data": {
                "type": "profiles",
                "attributes": {"name": name, "profileType": profile_type},
                "relationships": relationships,
            }
        }
        return self.client.post("/v1/profiles", payload)["data"]

    def delete_profile(self, profile_id):
        return self.client.delete(f"/v1/profiles/{profile_id}")
