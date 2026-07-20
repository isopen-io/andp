"""Tests for infrastructure/asc/builds.py — Build Upload API (ASC API 4.1+) et suivi des builds.

Flux officiel : POST /v1/buildUploads → POST /v1/buildUploadFiles (réservation)
→ PUT des chunks vers les uploadOperations → PATCH uploaded=true → polling
GET /v1/builds jusqu'à processingState VALID.
"""
import pytest

from builds import BuildProcessingError, BuildsManager


class RecordingTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, data, headers):
        self.calls.append({"method": method, "url": url, "data": data, "headers": headers})


@pytest.fixture
def ipa_file(tmp_path):
    path = tmp_path / "Meeshy.ipa"
    path.write_bytes(b"0123456789ABCDEF")  # 16 octets
    return str(path)


def _upload_flow_responses(fake_response, operations):
    return [
        fake_response(201, {"data": {"id": "UP1", "type": "buildUploads"}}),
        fake_response(201, {"data": {"id": "UPF1", "type": "buildUploadFiles",
                                     "attributes": {"uploadOperations": operations}}}),
        fake_response(200, {"data": {"id": "UPF1", "type": "buildUploadFiles"}}),
    ]


def test_upload_ipa_runs_reserve_upload_commit(asc_client, fake_session, fake_response, ipa_file):
    operations = [{
        "method": "PUT",
        "url": "https://upload.apple.com/part-1",
        "offset": 0,
        "length": 16,
        "requestHeaders": [{"name": "Content-Type", "value": "application/octet-stream"}],
    }]
    fake_session.queue(*_upload_flow_responses(fake_response, operations))
    transport = RecordingTransport()
    mgr = BuildsManager(asc_client, upload_transport=transport)

    upload_id = mgr.upload_ipa(ipa_file, version="1.2.0", build_number="42", app_id="6786703445", platform="IOS")

    reserve_upload = fake_session.requests[0]["json"]["data"]
    assert reserve_upload["type"] == "buildUploads"
    assert reserve_upload["attributes"] == {
        "cfBundleShortVersionString": "1.2.0",
        "cfBundleVersion": "42",
        "platform": "IOS",
    }
    # The API returns 409 without the app relationship (observed live 2026-07-20)
    assert reserve_upload["relationships"]["app"]["data"] == {"type": "apps", "id": "6786703445"}

    reserve_file = fake_session.requests[1]["json"]["data"]
    assert reserve_file["type"] == "buildUploadFiles"
    assert reserve_file["attributes"]["fileName"] == "Meeshy.ipa"
    assert reserve_file["attributes"]["fileSize"] == 16
    assert reserve_file["relationships"]["buildUpload"]["data"]["id"] == "UP1"

    assert transport.calls[0]["method"] == "PUT"
    assert transport.calls[0]["url"] == "https://upload.apple.com/part-1"
    assert transport.calls[0]["data"] == b"0123456789ABCDEF"
    assert transport.calls[0]["headers"] == {"Content-Type": "application/octet-stream"}

    commit = fake_session.requests[2]
    assert commit["method"] == "PATCH"
    assert commit["url"].endswith("/v1/buildUploadFiles/UPF1")
    assert commit["json"]["data"]["attributes"]["uploaded"] is True

    assert upload_id == "UP1"


def test_upload_ipa_chunks_according_to_operations(asc_client, fake_session, fake_response, ipa_file):
    operations = [
        {"method": "PUT", "url": "https://upload.apple.com/part-1",
         "offset": 0, "length": 10, "requestHeaders": []},
        {"method": "PUT", "url": "https://upload.apple.com/part-2",
         "offset": 10, "length": 6, "requestHeaders": []},
    ]
    fake_session.queue(*_upload_flow_responses(fake_response, operations))
    transport = RecordingTransport()
    mgr = BuildsManager(asc_client, upload_transport=transport)

    mgr.upload_ipa(ipa_file, version="1.2.0", build_number="42", app_id="6786703445")

    assert transport.calls[0]["data"] == b"0123456789"
    assert transport.calls[1]["data"] == b"ABCDEF"


def test_wait_for_processing_polls_until_valid(asc_client, fake_session, fake_response):
    processing = {"data": [{"id": "B1", "type": "builds",
                            "attributes": {"processingState": "PROCESSING"}}]}
    valid = {"data": [{"id": "B1", "type": "builds",
                       "attributes": {"processingState": "VALID"}}]}
    fake_session.queue(fake_response(200, processing), fake_response(200, valid))
    sleeps = []
    mgr = BuildsManager(asc_client, sleep=sleeps.append)

    build = mgr.wait_for_processing("APP1", build_number="42", poll_interval=30, timeout=600)

    params = fake_session.requests[0]["params"]
    assert params["filter[app]"] == "APP1"
    assert params["filter[version]"] == "42"
    assert build["attributes"]["processingState"] == "VALID"
    assert sleeps == [30]


def test_wait_for_processing_raises_on_invalid_build(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(200, {"data": [{"id": "B1", "type": "builds",
                                      "attributes": {"processingState": "INVALID"}}]})
    )
    mgr = BuildsManager(asc_client, sleep=lambda s: None)

    with pytest.raises(BuildProcessingError, match="INVALID"):
        mgr.wait_for_processing("APP1", build_number="42")


def test_wait_for_processing_times_out(asc_client, fake_response, fake_session):
    responses = [
        fake_response(200, {"data": [{"id": "B1", "type": "builds",
                                      "attributes": {"processingState": "PROCESSING"}}]})
        for _ in range(50)
    ]
    fake_session.queue(*responses)
    fake_now = [0.0]

    def fake_sleep(seconds):
        fake_now[0] += seconds

    mgr = BuildsManager(asc_client, sleep=fake_sleep, clock=lambda: fake_now[0])

    with pytest.raises(BuildProcessingError, match="[Tt]ime"):
        mgr.wait_for_processing("APP1", build_number="42", poll_interval=60, timeout=300)


def test_set_uses_non_exempt_encryption(asc_client, fake_session, fake_response):
    fake_session.queue(fake_response(200, {"data": {"id": "B1", "type": "builds"}}))
    mgr = BuildsManager(asc_client)

    mgr.set_uses_non_exempt_encryption("B1", False)

    request = fake_session.requests[0]
    assert request["method"] == "PATCH"
    assert request["url"].endswith("/v1/builds/B1")
    assert request["json"]["data"]["attributes"] == {"usesNonExemptEncryption": False}
