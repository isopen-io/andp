"""Service layer: the library both CLI and MCP call. No printing, returns dicts.

This is what makes MCP truly library-first — agents get structured results
from the release machine directly, never scraped from a CLI's stdout.
"""
import plistlib
import zipfile

import pytest

from andp import service
from conftest import FakeResponse, FakeSession, make_test_managers


def _make_ipa(directory, name="App.ipa"):
    plist = plistlib.dumps({
        "CFBundleIdentifier": "me.demo.app",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
    })
    path = directory / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Payload/App.app/Info.plist", plist)
    return str(path)


@pytest.fixture
def real_session(tmp_path, monkeypatch, ec_private_key_pem):
    """secrets.yml with test creds + a patched make_managers returning a
    recording FakeSession the test controls."""
    from conftest import real_secrets_yaml
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    monkeypatch.setattr(service, "make_managers", lambda account: make_test_managers(session))
    return session


def _app_found():
    return FakeResponse(200, {"data": [{"id": "app-9", "type": "apps",
                                        "attributes": {"name": "Demo"}}]})


def _upload_flow():
    return [
        FakeResponse(201, {"data": {"id": "UP1", "type": "buildUploads"}}),
        FakeResponse(201, {"data": {"id": "UPF1", "type": "buildUploadFiles",
                                    "attributes": {"uploadOperations": []}}}),
        FakeResponse(200, {"data": {"id": "UPF1", "type": "buildUploadFiles"}}),
    ]


def _build(state="VALID"):
    return FakeResponse(200, {"data": [{"id": "build-77", "type": "builds",
                                        "attributes": {"processingState": state}}]})


def test_start_creates_release_and_reports_next(real_session, tmp_path):
    ipa = _make_ipa(tmp_path)
    result = service.release_start(ipa, group="Beta")
    assert result["command"] == "release_start"
    assert result["ok"] is True
    assert result["dry_run"] is False
    assert result["state"] == "created"
    assert result["next"] == "poll"
    assert result["release_id"]


def test_start_dry_run_returns_plan_no_state_file(tmp_path, monkeypatch):
    (tmp_path / "secrets.example.yml").write_text(
        'accounts:\n  primary:\n    asc_api:\n      key_id: "ABCDE12345"\n'
        '      issuer_id: "x"\n      key_content: "REPLACE_WITH"\n'
    )
    monkeypatch.chdir(tmp_path)
    ipa = _make_ipa(tmp_path)

    result = service.release_start(ipa, group="Beta")

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["plan"] == ["app_record", "upload", "processing", "testflight_group"]
    assert not (tmp_path / ".andp").exists()  # no phantom state in dry-run


def test_poll_drives_to_done(real_session, tmp_path):
    ipa = _make_ipa(tmp_path)
    real_session.queue(_app_found(), *_upload_flow(), _build("VALID"),
                       FakeResponse(200, {"data": [{"id": "grp-1", "type": "betaGroups"}]}),
                       FakeResponse(204, None, content=b""))
    started = service.release_start(ipa, group="Beta")
    rid = started["release_id"]

    result = None
    for _ in range(20):
        result = service.release_poll(rid)
        if result["terminal"]:
            break
    assert result["state"] == "done"
    assert result["terminal"] is True
    assert result["ok"] is True
    assert result["build"]["id"] == "build-77"


def test_poll_reports_retry_after_while_processing(real_session, tmp_path):
    ipa = _make_ipa(tmp_path)
    real_session.queue(_app_found(), *_upload_flow(), _build("PROCESSING"))
    rid = service.release_start(ipa)["release_id"]
    service.release_poll(rid)  # created -> app_resolved
    service.release_poll(rid)  # app_resolved -> uploaded
    service.release_poll(rid)  # uploaded -> processing
    result = service.release_poll(rid)  # one poll, still processing
    assert result["state"] == "processing"
    assert result["terminal"] is False
    assert result["retry_after"] == 60


def test_poll_retryable_error_is_reported_not_raised(real_session, tmp_path):
    ipa = _make_ipa(tmp_path)
    real_session.queue(_app_found(), *_upload_flow(),
                       FakeResponse(503, {"errors": [{"status": "503", "detail": "down"}]}))
    rid = service.release_start(ipa)["release_id"]
    service.release_poll(rid); service.release_poll(rid); service.release_poll(rid)
    result = service.release_poll(rid)  # hits 503
    assert result["ok"] is False
    assert result["error"]["code"] == "asc_unavailable"
    assert result["error"]["retryable"] is True
    assert result["terminal"] is False  # not a terminal failure — retry later


def test_status_is_read_only(real_session, tmp_path):
    ipa = _make_ipa(tmp_path)
    rid = service.release_start(ipa)["release_id"]
    result = service.release_status(rid)
    assert result["command"] == "release_status"
    assert result["state"] == "created"
    # no requests made by a status read
    assert real_session.requests == []


def test_status_unknown_release_reports_not_found(real_session):
    result = service.release_status("does-not-exist")
    assert result["ok"] is False
    assert result["error"]["code"] == "not_found"


def test_list_returns_all_releases(real_session, tmp_path):
    ipa = _make_ipa(tmp_path)
    service.release_start(ipa)
    result = service.release_list()
    assert result["command"] == "release_list"
    assert len(result["releases"]) == 1
    assert result["releases"][0]["state"] == "created"
