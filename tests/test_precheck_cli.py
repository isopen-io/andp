"""service.precheck + CLI `andp precheck` + MCP precheck tool (read-only),
and the `--no-precheck` flag on `release start --ship`."""
import json

from andp import service
from andp.asc import asc_manager
from conftest import FakeResponse, FakeSession, make_test_managers, real_secrets_yaml


def _real(tmp_path, monkeypatch, ec_private_key_pem):
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    return session


def _clean_precheck(session):
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),                    # find_app
        FakeResponse(200, {"data": [{"id": "ver-1"}]}),                    # find_version
        FakeResponse(200, {"data": {"id": "ver-1", "attributes": {"appVersionState": "PREPARE_FOR_SUBMISSION"}}}),  # get_version
        FakeResponse(200, {"data": {"id": "build-77"}}),                   # build
        FakeResponse(200, {"data": [{"id": "loc-en", "attributes": {
            "locale": "en-US", "description": "Great.", "keywords": "k", "supportUrl": "https://x"}}]}),
        FakeResponse(200, {"data": [{"id": "set-1"}]}),
        FakeResponse(200, {"data": [{"id": "s1"}]}),
    )


def test_service_precheck_ok(tmp_path, monkeypatch, ec_private_key_pem):
    session = _real(tmp_path, monkeypatch, ec_private_key_pem)
    _clean_precheck(session)
    result = service.precheck("me.demo.app", "1.0")
    assert result["command"] == "precheck"
    assert result["ok"] is True
    assert result["errors"] == 0


def test_service_precheck_version_not_found_is_read_only(tmp_path, monkeypatch, ec_private_key_pem):
    session = _real(tmp_path, monkeypatch, ec_private_key_pem)
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),   # find_app
        FakeResponse(200, {"data": []}),                  # find_version -> none
    )
    result = service.precheck("me.demo.app", "9.9")
    assert result["ok"] is False
    assert result["error"]["code"] == "version_not_found"
    # crucially: no POST created a version
    assert all(r["method"] == "GET" for r in session.requests)


def test_cli_precheck(tmp_path, monkeypatch, ec_private_key_pem, capsys):
    session = _real(tmp_path, monkeypatch, ec_private_key_pem)
    _clean_precheck(session)
    code = asc_manager.main(["precheck", "me.demo.app", "1.0", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["command"] == "precheck"
    assert out["ok"] is True


def test_cli_precheck_errors_exit_1(tmp_path, monkeypatch, ec_private_key_pem, capsys):
    session = _real(tmp_path, monkeypatch, ec_private_key_pem)
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),
        FakeResponse(200, {"data": [{"id": "ver-1"}]}),
        FakeResponse(200, {"data": {"id": "ver-1", "attributes": {"appVersionState": "PREPARE_FOR_SUBMISSION"}}}),
        FakeResponse(200, {"data": None}),   # no build -> error
        FakeResponse(200, {"data": []}),     # no localizations -> error
    )
    code = asc_manager.main(["precheck", "me.demo.app", "1.0", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["ok"] is False


def test_mcp_precheck_tool_is_readonly():
    from andp import mcp
    resp = mcp.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = {t["name"]: t for t in resp["result"]["tools"]}
    assert "precheck" in tools
    assert tools["precheck"]["annotations"]["readOnlyHint"] is True
