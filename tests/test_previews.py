"""App preview VIDEO upload — the piece missing next to screenshots.

Mirrors the screenshot flow: ensure the appPreviewSet for the preview type,
reserve the appPreview (fileName/fileSize/mimeType), PUT the bytes, commit with
uploaded=true + MD5.
"""
from andp.asc.assets import PreviewManager
from conftest import FakeResponse, FakeSession


class _RecordingTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, data, headers):
        self.calls.append({"method": method, "url": url, "data": data, "headers": headers})


def _client(session):
    from andp.asc.client import ASCClient

    class _Auth:
        def token(self):
            return "t"

    return ASCClient(auth=_Auth(), session=session, sleep=lambda s: None)


def test_upload_preview_reserves_transfers_and_commits(tmp_path):
    video = tmp_path / "01.mp4"
    video.write_bytes(b"FAKEMP4DATA-1234")

    session = FakeSession()
    session.queue(
        # ensure_preview_set: lookup -> none, then create
        FakeResponse(200, {"data": []}),
        FakeResponse(201, {"data": {"id": "set-1", "type": "appPreviewSets"}}),
        # reserve appPreview with uploadOperations
        FakeResponse(201, {"data": {"id": "prev-1", "type": "appPreviews",
                                    "attributes": {"uploadOperations": [{
                                        "method": "PUT",
                                        "url": "https://upload.apple.com/p1",
                                        "offset": 0, "length": 16,
                                        "requestHeaders": [{"name": "Content-Type",
                                                            "value": "video/mp4"}]}]}}}),
        # commit
        FakeResponse(200, {"data": {"id": "prev-1", "type": "appPreviews"}}),
    )
    transport = _RecordingTransport()
    mgr = PreviewManager(_client(session), upload_transport=transport)

    result = mgr.upload_preview("loc-1", "APP_IPHONE_67", str(video))

    # set created for the right preview type + localization
    create_set = session.requests[1]["json"]["data"]
    assert create_set["attributes"]["previewType"] == "APP_IPHONE_67"
    assert create_set["relationships"]["appStoreVersionLocalization"]["data"]["id"] == "loc-1"
    # reservation carries fileName/fileSize/mimeType
    reserve = session.requests[2]["json"]["data"]
    assert reserve["attributes"]["fileName"] == "01.mp4"
    assert reserve["attributes"]["fileSize"] == 16
    assert reserve["attributes"]["mimeType"] == "video/mp4"
    # bytes PUT to the operation url
    assert transport.calls[0]["url"] == "https://upload.apple.com/p1"
    assert transport.calls[0]["data"] == b"FAKEMP4DATA-1234"
    # commit patches uploaded=true + an MD5 checksum
    commit = session.requests[3]["json"]["data"]
    assert commit["attributes"]["uploaded"] is True
    import hashlib
    assert commit["attributes"]["sourceFileChecksum"] == hashlib.md5(b"FAKEMP4DATA-1234").hexdigest()
    assert result["id"] == "prev-1"


def test_ensure_preview_set_reuses_existing(tmp_path):
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [{"id": "set-9", "type": "appPreviewSets"}]}))
    mgr = PreviewManager(_client(session))
    result = mgr.ensure_preview_set("loc-1", "APP_IPHONE_67")
    assert result["id"] == "set-9"
    assert len(session.requests) == 1  # no create


def test_mov_mime_type():
    from andp.asc.assets import _preview_mime
    assert _preview_mime("x.mov") == "video/quicktime"
    assert _preview_mime("x.mp4") == "video/mp4"
    assert _preview_mime("x.m4v") == "video/mp4"
