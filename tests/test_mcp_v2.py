"""MCP v2: honest tool annotations + library-first release tools.

The release_* tools drive the service layer (the machine) directly — not a
captured CLI stdout — and results carry structuredContent per MCP 2025-03-26.
"""
import plistlib
import zipfile

import pytest

from andp import mcp, service
from conftest import FakeResponse, FakeSession, make_test_managers


def _call(method, params=None, mid=1):
    msg = {"jsonrpc": "2.0", "id": mid, "method": method}
    if params is not None:
        msg["params"] = params
    return mcp.handle_message(msg)


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


def test_initialize_advertises_2025_protocol():
    result = _call("initialize", {})["result"]
    assert result["protocolVersion"] == "2025-03-26"


def test_every_tool_has_the_four_annotation_hints():
    tools = _call("tools/list")["result"]["tools"]
    for tool in tools:
        ann = tool.get("annotations")
        assert ann is not None, f"{tool['name']} has no annotations"
        for hint in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"):
            assert hint in ann, f"{tool['name']} missing {hint}"


def test_annotation_honesty():
    tools = {t["name"]: t["annotations"] for t in _call("tools/list")["result"]["tools"]}
    # verify only reads
    assert tools["verify"]["readOnlyHint"] is True
    # submit is the one destructive, non-idempotent action
    assert tools["submit"]["destructiveHint"] is True
    assert tools["submit"]["idempotentHint"] is False
    # release_poll advances the machine each call -> NOT idempotent
    assert tools["release_poll"]["idempotentHint"] is False
    # release_start resumes the same triple -> idempotent
    assert tools["release_start"]["idempotentHint"] is True
    # read-only queries
    assert tools["release_status"]["readOnlyHint"] is True
    assert tools["release_list"]["readOnlyHint"] is True


def test_release_tools_are_exposed():
    names = {t["name"] for t in _call("tools/list")["result"]["tools"]}
    assert {"release_start", "release_poll", "release_status", "release_list"} <= names


def test_release_start_is_library_first_with_structured_content(
    tmp_path, monkeypatch, ec_private_key_pem
):
    from conftest import real_secrets_yaml
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    monkeypatch.setattr(service, "make_managers", lambda account: make_test_managers(session))
    ipa = _make_ipa(tmp_path)

    response = _call("tools/call", {"name": "release_start",
                                    "arguments": {"ipa_path": ipa, "group": "Beta"}})

    result = response["result"]
    assert result.get("isError", False) is False
    # structured content is present and is the service dict (no stdout scraping)
    structured = result["structuredContent"]
    assert structured["command"] == "release_start"
    assert structured["state"] == "created"
    assert structured["release_id"]
    # no external request was made just to start
    assert session.requests == []


def test_release_poll_advances_and_flags_terminal(
    tmp_path, monkeypatch, ec_private_key_pem
):
    from conftest import real_secrets_yaml
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
    monkeypatch.setattr(service, "make_managers", lambda account: make_test_managers(session))
    ipa = _make_ipa(tmp_path)

    rid = _call("tools/call", {"name": "release_start",
                               "arguments": {"ipa_path": ipa}})["result"]["structuredContent"]["release_id"]

    terminal = False
    for _ in range(10):
        result = _call("tools/call", {"name": "release_poll",
                                      "arguments": {"release_id": rid}})["result"]
        if result["structuredContent"]["terminal"]:
            terminal = True
            break
    assert terminal
    assert result["structuredContent"]["state"] == "done"


def test_submit_still_gated_by_policy(tmp_path, monkeypatch, ec_private_key_pem):
    from conftest import real_secrets_yaml
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    response = _call("tools/call", {"name": "submit",
                                    "arguments": {"bundle_id": "me.demo.app", "version": "1.0"}})
    assert response["result"]["isError"] is True
    assert "policy" in response["result"]["content"][0]["text"].lower()
