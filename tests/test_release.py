"""`release` — the one-shot automation primitive for agents and CI:
verify (app lookup) -> upload -> wait for Apple processing -> optional
TestFlight group assignment. Structured stages in --json mode.
"""
import json

from andp.asc import asc_manager
from conftest import FakeResponse
from test_builds import _upload_flow_responses
from test_json_output import _make_ipa


def _release_responses(group_data):
    """find_app, upload flow, processing poll (VALID), then group steps."""
    responses = [
        FakeResponse(200, {"data": [{"id": "app-9", "type": "apps",
                                     "attributes": {"name": "Demo", "bundleId": "me.demo.app"}}]}),
        *_upload_flow_responses(FakeResponse, []),
        FakeResponse(200, {"data": [{"id": "build-77", "type": "builds",
                                     "attributes": {"processingState": "VALID"}}]}),
    ]
    responses.extend(group_data)
    return responses


def test_release_full_chain_with_group(configured_dir, fake_transport, capsys):
    _make_ipa(configured_dir)
    fake_transport.queue(
        *_release_responses([
            # ensure_group: lookup finds an existing group
            FakeResponse(200, {"data": [{"id": "grp-1", "type": "betaGroups",
                                         "attributes": {"name": "Beta"}}]}),
            # add_build_to_group
            FakeResponse(204, None, content=b""),
        ])
    )

    exit_code = asc_manager.main(["release", "App.ipa", "--group", "Beta", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["command"] == "release"
    assert payload["ok"] is True
    stages = [s["name"] for s in payload["stages"]]
    assert stages == ["app_record", "upload", "processing", "testflight_group"]
    assert payload["build"]["id"] == "build-77"
    assert payload["build"]["processing_state"] == "VALID"
    # the build really was linked to the group
    link_request = fake_transport.requests[-1]
    assert "/v1/betaGroups/grp-1/relationships/builds" in link_request["url"]


def test_release_without_group_stops_after_processing(configured_dir, fake_transport, capsys):
    _make_ipa(configured_dir)
    fake_transport.queue(*_release_responses([]))

    exit_code = asc_manager.main(["release", "App.ipa", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    stages = [s["name"] for s in payload["stages"]]
    assert stages == ["app_record", "upload", "processing"]


def test_release_failed_processing_reports_stage(configured_dir, fake_transport, capsys):
    _make_ipa(configured_dir)
    fake_transport.queue(
        FakeResponse(200, {"data": [{"id": "app-9", "type": "apps",
                                     "attributes": {"name": "Demo", "bundleId": "me.demo.app"}}]}),
        *_upload_flow_responses(FakeResponse, []),
        FakeResponse(200, {"data": [{"id": "build-77", "type": "builds",
                                     "attributes": {"processingState": "FAILED"}}]}),
    )

    exit_code = asc_manager.main(["release", "App.ipa", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["stages"][-1]["name"] == "processing"
    assert payload["stages"][-1]["ok"] is False
    assert "FAILED" in payload["stages"][-1]["detail"]


def test_release_dry_run_plans_without_network(tmp_path, monkeypatch, capsys):
    (tmp_path / "secrets.example.yml").write_text(
        'accounts:\n  primary:\n    asc_api:\n      key_id: "ABCDE12345"\n'
        '      issuer_id: "x"\n      key_content: "REPLACE_WITH"\n'
    )
    _make_ipa(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = asc_manager.main(["release", "App.ipa", "--group", "Beta", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["dry_run"] is True
