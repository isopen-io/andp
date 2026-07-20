"""MCP server: AI agents drive publishing as native tools over JSON-RPC.

handle_message() is the pure dispatcher (stdio loop is a thin wrapper).
Policy: submission to App Review is refused unless andp.yml explicitly
allows it — agents must not be able to ship to review by accident.
"""
import json

from andp import mcp
from conftest import FakeResponse


def _call(method, params=None, id=1):
    msg = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        msg["params"] = params
    return mcp.handle_message(msg)


def test_initialize_handshake():
    response = _call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    result = response["result"]
    assert result["serverInfo"]["name"] == "andp"
    assert "tools" in result["capabilities"]


def test_notifications_return_none():
    assert mcp.handle_message(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    ) is None


def test_unknown_method_errors():
    response = _call("frobnicate")
    assert response["error"]["code"] == -32601


def test_tools_list_exposes_publishing_tools():
    response = _call("tools/list")
    tools = {t["name"]: t for t in response["result"]["tools"]}
    for name in ("verify", "upload", "release", "status", "testflight_add", "submit"):
        assert name in tools, name
        assert "inputSchema" in tools[name]
    assert tools["verify"]["inputSchema"]["type"] == "object"


def test_tools_call_verify_returns_structured_result(configured_dir, fake_transport):
    fake_transport.queue(
        FakeResponse(
            200,
            {"data": [{"id": "app-42", "type": "apps",
                       "attributes": {"name": "Demo", "bundleId": "me.demo.app"}}]},
        )
    )

    response = _call("tools/call", {"name": "verify", "arguments": {"bundle_id": "me.demo.app"}})

    result = response["result"]
    assert result.get("isError", False) is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["command"] == "verify"
    assert payload["ok"] is True
    assert payload["app"]["id"] == "app-42"


def test_tools_call_verify_failure_is_error(configured_dir, fake_transport):
    fake_transport.queue(FakeResponse(200, {"data": []}))

    response = _call("tools/call", {"name": "verify", "arguments": {"bundle_id": "me.demo.app"}})

    result = response["result"]
    assert result["isError"] is True
    payload = json.loads(result["content"][0]["text"])
    assert payload["ok"] is False


def test_submit_refused_without_policy(configured_dir):
    response = _call(
        "tools/call",
        {"name": "submit", "arguments": {"bundle_id": "me.demo.app", "version": "1.0"}},
    )

    result = response["result"]
    assert result["isError"] is True
    assert "policy" in result["content"][0]["text"].lower()
    assert "allow_submit" in result["content"][0]["text"]


def test_submit_allowed_by_policy_file(tmp_path, monkeypatch):
    # DRY-RUN credentials: the command itself is a no-op, we only test the gate
    (tmp_path / "secrets.example.yml").write_text(
        'accounts:\n  primary:\n    asc_api:\n      key_id: "ABCDE12345"\n'
        '      issuer_id: "x"\n      key_content: "REPLACE_WITH"\n'
    )
    (tmp_path / "andp.yml").write_text("policy:\n  allow_submit: true\n")
    monkeypatch.chdir(tmp_path)

    response = _call(
        "tools/call",
        {"name": "submit", "arguments": {"bundle_id": "me.demo.app", "version": "1.0"}},
    )

    result = response["result"]
    assert result.get("isError", False) is False
    assert "DRY-RUN" in result["content"][0]["text"]
