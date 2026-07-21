"""CLI release subcommands (start/poll/status/list) wired to the service."""
import json
import plistlib
import zipfile

from andp.asc import asc_manager
from andp import service
from conftest import FakeResponse, FakeSession, make_test_managers, real_secrets_yaml


def _make_ipa(directory):
    plist = plistlib.dumps({
        "CFBundleIdentifier": "me.demo.app",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
    })
    path = directory / "App.ipa"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Payload/App.app/Info.plist", plist)
    return str(path)


def test_release_start_then_status_json(tmp_path, monkeypatch, ec_private_key_pem, capsys):
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    ipa = _make_ipa(tmp_path)

    assert asc_manager.main(["release", "start", ipa, "--json"]) == 0
    start = json.loads(capsys.readouterr().out)
    assert start["command"] == "release_start"
    rid = start["release_id"]

    assert asc_manager.main(["release", "status", rid, "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["state"] == "created"
    assert status["command"] == "release_status"


def test_release_start_dry_run_plan(tmp_path, monkeypatch, capsys):
    (tmp_path / "secrets.example.yml").write_text(
        'accounts:\n  primary:\n    asc_api:\n      key_id: "ABCDE12345"\n'
        '      issuer_id: "x"\n      key_content: "REPLACE_WITH"\n'
    )
    monkeypatch.chdir(tmp_path)
    ipa = _make_ipa(tmp_path)

    assert asc_manager.main(["release", "start", ipa, "--group", "Beta", "--json"]) == 0
    out = [l for l in capsys.readouterr().out.splitlines() if l.startswith("{")][0]
    result = json.loads(out)
    assert result["dry_run"] is True
    assert result["plan"] == ["app_record", "upload", "processing", "testflight_group"]


def test_release_poll_drives_to_done(tmp_path, monkeypatch, ec_private_key_pem, capsys):
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9", "type": "apps"}]}),
        FakeResponse(201, {"data": {"id": "UP1", "type": "buildUploads"}}),
        FakeResponse(201, {"data": {"id": "UPF1", "type": "buildUploadFiles",
                                    "attributes": {"uploadOperations": []}}}),
        FakeResponse(200, {"data": {"id": "UPF1", "type": "buildUploadFiles"}}),
        FakeResponse(200, {"data": [{"id": "build-77", "type": "builds",
                                     "attributes": {"processingState": "VALID"}}]}),
    )
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    ipa = _make_ipa(tmp_path)

    asc_manager.main(["release", "start", ipa, "--json"])
    rid = json.loads(capsys.readouterr().out)["release_id"]

    for _ in range(10):
        asc_manager.main(["release", "poll", rid, "--json"])
        result = json.loads(capsys.readouterr().out)
        if result["terminal"]:
            break
    assert result["state"] == "done"
    assert result["build"]["id"] == "build-77"
