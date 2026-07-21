"""MCP release_start accepts a `ship` argument (App Store path); no approve
tool is exposed (approval is an out-of-band human action)."""
import plistlib
import zipfile

from andp import mcp, service
from conftest import FakeResponse, FakeSession, make_test_managers


def _call(method, params=None):
    return mcp.handle_message({"jsonrpc": "2.0", "id": 1, "method": method,
                               "params": params or {}})


def _make_ipa(directory):
    info = {"CFBundleIdentifier": "me.demo.app", "CFBundleShortVersionString": "1.0",
            "CFBundleVersion": "1", "ITSAppUsesNonExemptEncryption": False}
    path = directory / "App.ipa"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Payload/App.app/Info.plist", plistlib.dumps(info))
    return str(path)


def test_release_start_tool_declares_ship_arg():
    tools = {t["name"]: t for t in _call("tools/list")["result"]["tools"]}
    props = tools["release_start"]["inputSchema"]["properties"]
    assert "ship" in props
    assert props["ship"]["type"] == "boolean"


def test_no_approve_tool_exposed():
    names = {t["name"] for t in _call("tools/list")["result"]["tools"]}
    assert "release_approve" not in names
    assert "approve" not in names


def test_release_start_ship_via_mcp(tmp_path, monkeypatch, ec_private_key_pem):
    from conftest import real_secrets_yaml
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    (tmp_path / "andp.yml").write_text("policy:\n  allow_submit: false\n")
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    ipa = _make_ipa(tmp_path)

    response = _call("tools/call", {"name": "release_start",
                                    "arguments": {"ipa_path": ipa, "ship": True}})
    structured = response["result"]["structuredContent"]
    assert structured["ok"] is True
    from andp.core.state import StateStore
    raw = StateStore(str(tmp_path / ".andp" / "state")).load(structured["release_id"])
    assert raw["want_ship"] is True
