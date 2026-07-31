"""The MCP surface defines every operation of the end-to-end pipeline.

Agent-first doctrine (2026-07-31): an agent must be able to drive the whole
chain — targets → build → test → run → build_number → verify → upload →
status → publish → precheck → readiness → submit/release → unlock → store —
without ever scraping a CLI stdout it wasn't given.

One absence stays load-bearing: `release_approve`. An approval gate the agent
behind it can open by itself is not a gate — standing consent goes through
`policy.allow_submit` (and `policy.allow_stale_unlock` for unlock).
"""
import json

from andp import mcp, service


def _call(name, arguments=None):
    return mcp.handle_message({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}}})


def _tools():
    response = mcp.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    return {t["name"]: t for t in response["result"]["tools"]}


def test_tools_list_defines_the_whole_pipeline():
    tools = _tools()
    expected = {
        # local Xcode surface
        "targets", "build", "test", "run",
        # numbering + preflight
        "build_number", "verify", "config",
        # binary path
        "upload", "status",
        # metadata path
        "publish", "precheck",
        "readiness_testflight", "readiness_appstore",
        # review path
        "submit", "unlock",
        # release machine
        "release_start", "release_poll", "release_status", "release_list",
        "release_reset",
        # store configuration
        "store_configure_pricing", "store_configure_availability",
        "store_set_age_rating", "store_apply",
        # testers
        "testflight_add",
    }
    missing = expected - set(tools)
    assert not missing, f"MCP surface incomplete: {sorted(missing)}"
    for name in expected:
        assert "inputSchema" in tools[name], name
        assert "annotations" in tools[name], name


def test_release_approve_stays_out_of_reach():
    """The one deliberate absence: a gate an agent can open is not a gate."""
    assert "release_approve" not in _tools()


def test_publish_is_library_first(monkeypatch):
    captured = {}

    def fake_publish(bundle_id, version, metadata_dir, account="primary"):
        captured.update(bundle_id=bundle_id, version=version,
                        metadata_dir=metadata_dir, account=account)
        return {"command": "publish", "ok": True, "dry_run": False,
                "locales": {"fr-FR": {"metadata": "updated",
                                      "screenshots": 5, "previews": 0}}}

    monkeypatch.setattr(service, "publish", fake_publish)
    result = _call("publish", {"bundle_id": "me.demo.app", "version": "1.0",
                               "metadata_dir": "meta"})["result"]
    assert result.get("isError") is not True
    assert result["structuredContent"]["locales"]["fr-FR"]["screenshots"] == 5
    assert captured["metadata_dir"] == "meta"


def test_readiness_tools_are_library_first(monkeypatch):
    monkeypatch.setattr(service, "readiness_testflight",
                        lambda bundle_id, account="primary": {
                            "command": "readiness", "ready": True})
    monkeypatch.setattr(service, "readiness_appstore",
                        lambda bundle_id, version, account="primary": {
                            "command": "readiness", "ready": False,
                            "blockers": ["no build"]})
    ok = _call("readiness_testflight", {"bundle_id": "me.demo.app"})["result"]
    assert ok["structuredContent"]["ready"] is True
    # not_ready is a successful verdict, not a tool error
    verdict = _call("readiness_appstore",
                    {"bundle_id": "me.demo.app", "version": "1.0"})["result"]
    assert verdict.get("isError") is not True
    assert verdict["structuredContent"]["ready"] is False


def test_build_number_is_library_first(monkeypatch):
    captured = {}

    def fake_build_number(strategy, bundle_id=None, floor=0, fmt=None,
                          sha=None, digits=7, account="primary", clock=None):
        captured.update(strategy=strategy, bundle_id=bundle_id, floor=floor)
        return {"command": "build-number", "ok": True, "build_number": 1266}

    monkeypatch.setattr(service, "build_number", fake_build_number)
    result = _call("build_number", {"strategy": "max-build",
                                    "bundle_id": "me.demo.app"})["result"]
    assert result["structuredContent"]["build_number"] == 1266
    assert captured["strategy"] == "max-build"


def test_release_reset_is_library_first(monkeypatch):
    monkeypatch.setattr(service, "release_reset_by_id", lambda rid: {
        "command": "release_reset", "ok": True, "release_id": rid})
    result = _call("release_reset", {"release_id": "rel-1"})["result"]
    assert result["structuredContent"]["release_id"] == "rel-1"


def test_local_tools_reach_the_cli_in_json_mode(monkeypatch):
    calls = []

    def fake_cli(argv):
        calls.append(argv)
        print(json.dumps({"command": argv[0], "ok": True}))
        return 0

    monkeypatch.setattr(mcp, "cli_main", fake_cli)
    assert _call("targets")["result"]["structuredContent"]["ok"] is True
    _call("build", {"all": True})
    _call("build", {"target": "solo", "archive": True})
    _call("test", {"target": "solo"})
    _call("run", {"target": "solo"})
    _call("config")
    assert ["targets", "--json"] in calls
    assert ["build", "--all", "--json"] in calls
    assert ["build", "solo", "--archive", "--json"] in calls
    assert ["test", "solo", "--json"] in calls
    assert ["run", "solo", "--json"] in calls
    assert ["config", "--json"] in calls
    # `run` must never stream logs over stdio — it would block the server
    assert all("--logs" not in argv for argv in calls)


def test_policy_parses_allow_stale_unlock(tmp_path):
    from andp.policy import load_policy
    path = tmp_path / "andp.yml"
    path.write_text("policy:\n  allow_stale_unlock: true\n")
    assert load_policy(str(path))["allow_stale_unlock"] is True
    assert load_policy(str(tmp_path / "absent.yml"))["allow_stale_unlock"] is False


def test_unlock_policy_grants_standing_consent(tmp_path, monkeypatch):
    """policy.allow_stale_unlock: true = durable, auditable human consent —
    the agent may then cancel stale submissions end-to-end."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "andp.yml").write_text("policy:\n  allow_stale_unlock: true\n")
    captured = {}

    def fake_unlock(bundle_id, version, **kwargs):
        captured.update(kwargs)
        return {"command": "unlock", "ok": True, "dry_run": False,
                "bundle_id": bundle_id, "version": version,
                "submission_id": "sub-1", "submitted_at": None,
                "age_seconds": None, "stale": False,
                "already_editable": False, "version_state": "DEVELOPER_REJECTED"}

    monkeypatch.setattr(service, "unlock", fake_unlock)
    _call("unlock", {"bundle_id": "me.demo.app", "version": "1.0"})
    assert captured["assume_yes"] is True


def test_unlock_without_policy_keeps_the_gate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    captured = {}

    def fake_unlock(bundle_id, version, **kwargs):
        captured.update(kwargs)
        return {"command": "unlock", "ok": False,
                "error": {"code": "stale_submission_unconfirmed",
                          "message": "m", "retryable": False, "remediation": "r"}}

    monkeypatch.setattr(service, "unlock", fake_unlock)
    result = _call("unlock", {"bundle_id": "me.demo.app", "version": "1.0"})["result"]
    assert captured["assume_yes"] is False
    assert result["isError"] is True


def test_annotations_tell_hosts_the_truth():
    tools = _tools()
    read_only = {"targets", "config", "build_number",
                 "readiness_testflight", "readiness_appstore"}
    for name in read_only:
        assert tools[name]["annotations"]["readOnlyHint"] is True, name
    for name in ("release_reset", "unlock"):
        assert tools[name]["annotations"]["destructiveHint"] is True, name
    local = {"targets", "build", "test", "run", "config", "release_reset"}
    for name in local:
        assert tools[name]["annotations"]["openWorldHint"] is False, name
