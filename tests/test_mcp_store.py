"""MCP store tools — library-first (drive the service directly), honest
annotations. store_configure_availability is destructive (shrinking the set
delists territories), so its annotation must say so (S8).
"""
import json

import pytest

from andp import mcp, service
from conftest import FakeResponse, FakeSession, make_test_managers, real_secrets_yaml, write_secrets


def _call(method, params=None, mid=1):
    msg = {"jsonrpc": "2.0", "id": mid, "method": method}
    if params is not None:
        msg["params"] = params
    return mcp.handle_message(msg)


@pytest.fixture
def cfg(tmp_path, monkeypatch, ec_private_key_pem):
    write_secrets(tmp_path, real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    return session, tmp_path


def test_store_tools_are_listed():
    names = {t["name"] for t in _call("tools/list")["result"]["tools"]}
    assert {"store_configure_pricing", "store_configure_availability",
            "store_set_age_rating", "store_apply"} <= names


def test_store_tools_have_full_annotations():
    tools = {t["name"]: t["annotations"] for t in _call("tools/list")["result"]["tools"]}
    for name in ("store_configure_pricing", "store_configure_availability",
                 "store_set_age_rating", "store_apply"):
        for hint in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"):
            assert hint in tools[name]


def test_availability_tool_is_destructive_others_not():
    tools = {t["name"]: t["annotations"] for t in _call("tools/list")["result"]["tools"]}
    assert tools["store_configure_availability"]["destructiveHint"] is True   # S8
    assert tools["store_configure_pricing"]["destructiveHint"] is False
    assert tools["store_set_age_rating"]["destructiveHint"] is False


def test_store_pricing_dispatches_to_service_with_structured_content(cfg):
    session, _ = cfg
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),
        FakeResponse(200, {"data": [{"id": "pp-9", "attributes": {"customerPrice": "0.99"},
                                     "relationships": {"territory": {"data": {"id": "USA"}}}}], "links": {}}),
        FakeResponse(200, {"data": None}),
        FakeResponse(200, {"data": {"id": "s1"}}))
    res = _call("tools/call", {"name": "store_configure_pricing",
                               "arguments": {"bundle_id": "me.demo.app", "price": "0.99"}})["result"]
    assert res["structuredContent"]["changed"] is True
    assert "isError" not in res


def test_store_apply_dispatches(cfg):
    session, tmp = cfg
    (tmp / "andp.yml").write_text('store:\n  pricing:\n    price: "0.99"\n')
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),
        FakeResponse(200, {"data": [{"id": "pp-9", "attributes": {"customerPrice": "0.99"},
                                     "relationships": {"territory": {"data": {"id": "USA"}}}}], "links": {}}),
        FakeResponse(200, {"data": None}),
        FakeResponse(200, {"data": {"id": "s1"}}))
    res = _call("tools/call", {"name": "store_apply",
                               "arguments": {"bundle_id": "me.demo.app"}})["result"]
    assert res["structuredContent"]["blocks"]["pricing"]["ok"] is True


def test_store_plan_tool_is_read_only_and_library_first(monkeypatch):
    from andp import listing_service
    tools = {t["name"]: t for t in _call("tools/list")["result"]["tools"]}
    assert tools["store_plan"]["annotations"]["readOnlyHint"] is True
    seen = {}

    def fake_plan(bundle_id, **kwargs):
        seen.update(bundle_id=bundle_id, **kwargs)
        return {"command": "store_plan", "ok": True, "written": False, "changes": []}
    monkeypatch.setattr(listing_service, "store_plan", fake_plan)
    res = _call("tools/call", {"name": "store_plan", "arguments": {
        "bundle_id": "me.demo.app", "version": "1.2.0",
        "metadata_dir": "fastlane/metadata"}})["result"]
    assert res["structuredContent"]["written"] is False
    assert seen == {"bundle_id": "me.demo.app", "account": "primary", "version": "1.2.0",
                    "metadata_dir": "fastlane/metadata"}


def test_store_apply_forwards_version_and_metadata(monkeypatch):
    seen = {}

    def fake_store(bundle_id, **kwargs):
        seen.update(kwargs)
        return {"command": "configure_store", "ok": True, "blocks": {}}
    monkeypatch.setattr(service, "configure_store", fake_store)
    _call("tools/call", {"name": "store_apply", "arguments": {
        "bundle_id": "me.demo.app", "version": "1.2.0", "metadata_dir": "md"}})
    assert seen["version"] == "1.2.0" and seen["metadata_dir"] == "md"
