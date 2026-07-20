"""--json output mode: structured envelopes for AI agents and scripts.

Every command accepts --json and emits a single JSON object on stdout:
{"command": ..., "ok": bool, ...}. Exit codes are unchanged.
"""
import json
import plistlib
import zipfile

from andp.asc import asc_manager
from conftest import FakeResponse


def _make_ipa(directory, name="App.ipa", bundle_id="me.demo.app", version="1.0", build="1"):
    plist = plistlib.dumps(
        {
            "CFBundleIdentifier": bundle_id,
            "CFBundleShortVersionString": version,
            "CFBundleVersion": build,
        }
    )
    path = directory / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Payload/App.app/Info.plist", plist)
    return path


def test_verify_json_success(configured_dir, fake_transport, capsys):
    fake_transport.queue(
        FakeResponse(
            200,
            {"data": [{"id": "app-42", "type": "apps",
                       "attributes": {"name": "Demo", "bundleId": "me.demo.app"}}]},
        )
    )

    exit_code = asc_manager.main(["verify", "me.demo.app", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["command"] == "verify"
    assert payload["ok"] is True
    check_names = [c["name"] for c in payload["checks"]]
    assert check_names == ["credentials", "jwt", "api_auth", "app_record"]
    assert all(c["ok"] for c in payload["checks"])
    assert payload["app"] == {"id": "app-42", "name": "Demo", "bundle_id": "me.demo.app"}


def test_verify_json_failure_names_missing_fields(tmp_path, monkeypatch, capsys):
    (tmp_path / "secrets.yml").write_text(
        """
accounts:
  primary:
    asc_api:
      key_id: "TESTKEY001"
      issuer_id: "REPLACE_WITH_ISSUER_ID"
      key_content: |
        -----BEGIN PRIVATE KEY-----
        PRIMARY_KEY_CONTENT
        -----END PRIVATE KEY-----
"""
    )
    monkeypatch.chdir(tmp_path)

    exit_code = asc_manager.main(["verify", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["ok"] is False
    credentials = payload["checks"][0]
    assert credentials["name"] == "credentials"
    assert credentials["ok"] is False
    assert "issuer_id" in credentials["missing"]
    assert "key_content" in credentials["missing"]


def test_upload_json_dry_run(tmp_path, monkeypatch, capsys):
    (tmp_path / "secrets.example.yml").write_text(
        'accounts:\n  primary:\n    asc_api:\n      key_id: "ABCDE12345"\n'
        '      issuer_id: "x"\n      key_content: "REPLACE_WITH"\n'
    )
    _make_ipa(tmp_path, version="2.0", build="7")
    monkeypatch.chdir(tmp_path)

    exit_code = asc_manager.main(["upload", "App.ipa", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {
        "command": "upload",
        "ok": True,
        "dry_run": True,
        "ipa": "App.ipa",
        "bundle_id": "me.demo.app",
        "version": "2.0",
        "build_number": "7",
    }


def test_upload_json_real(configured_dir, fake_transport, capsys):
    from test_builds import _upload_flow_responses

    _make_ipa(configured_dir)
    fake_transport.queue(
        FakeResponse(200, {"data": [{"id": "app-9", "type": "apps"}]}),
        *_upload_flow_responses(FakeResponse, []),
    )

    exit_code = asc_manager.main(["upload", "App.ipa", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["dry_run"] is False
    assert payload["upload_id"] == "UP1"
    assert payload["app_id"] == "app-9"
