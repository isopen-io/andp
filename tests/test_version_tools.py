"""`andp version list|set` — per-platform App Store version records.

ASC keeps one independent appStoreVersion record PER PLATFORM and nothing
synchronises their version strings (lived 2026-07-31: iOS read 1.0.0 while a
hand-created MAC_OS record read 1.0). `list` makes the drift visible; `set`
reconciles a platform to the wanted string — renaming the editable record,
creating one when absent, and refusing to touch a non-editable one.
"""
import json

from andp import mcp, service
from andp.asc import asc_manager
from conftest import FakeResponse, FakeSession, make_test_managers, real_secrets_yaml, write_secrets

APP = {"data": [{"id": "app-9"}]}


def _version(platform, version_string, state, vid):
    return {"id": vid, "attributes": {
        "platform": platform, "versionString": version_string,
        "appVersionState": state}}


def _wire(tmp_path, monkeypatch, ec_private_key_pem, *responses):
    write_secrets(tmp_path, real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    session.queue(*responses)
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    return session


# -- version_list ----------------------------------------------------------


def test_version_list_reports_every_platform(tmp_path, monkeypatch, ec_private_key_pem):
    _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, {"data": [
            _version("MAC_OS", "1.0", "PREPARE_FOR_SUBMISSION", "ver-mac"),
            _version("IOS", "1.0.0", "WAITING_FOR_REVIEW", "ver-ios"),
        ]}),
    )
    result = service.version_list("me.demo.app")
    assert result["ok"] is True
    by_platform = {v["platform"]: v for v in result["versions"]}
    assert by_platform["IOS"]["version_string"] == "1.0.0"
    assert by_platform["IOS"]["editable"] is False
    assert by_platform["MAC_OS"]["version_string"] == "1.0"
    assert by_platform["MAC_OS"]["editable"] is True


def test_version_list_app_not_found(tmp_path, monkeypatch, ec_private_key_pem):
    _wire(tmp_path, monkeypatch, ec_private_key_pem, FakeResponse(200, {"data": []}))
    result = service.version_list("me.demo.app")
    assert result["ok"] is False
    assert result["error"]["code"] == "app_not_found"


def test_version_list_dry_run(tmp_path, monkeypatch):
    (tmp_path / "secrets.example.yml").write_text(
        'accounts:\n  primary:\n    asc_api:\n      key_id: "ABCDE12345"\n'
        '      issuer_id: "x"\n      key_content: "REPLACE_WITH"\n')
    monkeypatch.chdir(tmp_path)
    result = service.version_list("me.demo.app")
    assert result["ok"] is True
    assert result["dry_run"] is True


# -- version_set -----------------------------------------------------------


def test_version_set_renames_the_editable_record(tmp_path, monkeypatch, ec_private_key_pem):
    session = _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, {"data": [
            _version("MAC_OS", "1.0", "PREPARE_FOR_SUBMISSION", "ver-mac")]}),
        FakeResponse(200, {"data": _version("MAC_OS", "1.0.0",
                                            "PREPARE_FOR_SUBMISSION", "ver-mac")}),
    )
    result = service.version_set("me.demo.app", "1.0.0", platform="MAC_OS")
    assert result["ok"] is True
    assert result["changed"] is True
    assert result["created"] is False
    assert result["previous_version_string"] == "1.0"
    patch = session.requests[-1]
    assert patch["method"] == "PATCH"
    assert patch["json"]["data"]["attributes"]["versionString"] == "1.0.0"


def test_version_set_is_a_noop_when_already_right(tmp_path, monkeypatch, ec_private_key_pem):
    session = _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, {"data": [
            _version("IOS", "1.0.0", "WAITING_FOR_REVIEW", "ver-ios")]}),
    )
    result = service.version_set("me.demo.app", "1.0.0", platform="IOS")
    assert result["ok"] is True
    assert result["changed"] is False
    assert len(session.requests) == 2              # no mutation went out


def test_version_set_refuses_a_locked_record(tmp_path, monkeypatch, ec_private_key_pem):
    session = _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, {"data": [
            _version("IOS", "1.0.0", "WAITING_FOR_REVIEW", "ver-ios")]}),
    )
    result = service.version_set("me.demo.app", "1.1.0", platform="IOS")
    assert result["ok"] is False
    assert result["error"]["code"] == "version_not_editable"
    assert len(session.requests) == 2              # never mutates blindly


def test_version_set_creates_when_the_platform_has_no_record(
        tmp_path, monkeypatch, ec_private_key_pem):
    session = _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, {"data": []}),           # list_versions: no MAC_OS record
        FakeResponse(200, {"data": []}),           # ensure_version's own lookup
        FakeResponse(201, {"data": _version("MAC_OS", "1.0.0",
                                            "PREPARE_FOR_SUBMISSION", "ver-new")}),
    )
    result = service.version_set("me.demo.app", "1.0.0", platform="MAC_OS")
    assert result["ok"] is True
    assert result["created"] is True
    assert result["changed"] is True
    post = session.requests[-1]
    assert post["method"] == "POST"
    assert post["json"]["data"]["attributes"]["platform"] == "MAC_OS"


def test_version_set_rejects_an_unknown_platform(tmp_path, monkeypatch, ec_private_key_pem):
    session = _wire(tmp_path, monkeypatch, ec_private_key_pem)
    result = service.version_set("me.demo.app", "1.0.0", platform="ANDROID")
    assert result["ok"] is False
    assert result["error"]["code"] == "unknown_platform"
    assert not session.requests                    # refused before any HTTP


def test_version_set_dry_run(tmp_path, monkeypatch):
    (tmp_path / "secrets.example.yml").write_text(
        'accounts:\n  primary:\n    asc_api:\n      key_id: "ABCDE12345"\n'
        '      issuer_id: "x"\n      key_content: "REPLACE_WITH"\n')
    monkeypatch.chdir(tmp_path)
    result = service.version_set("me.demo.app", "1.0.0", platform="MAC_OS")
    assert result["ok"] is True
    assert result["dry_run"] is True


# -- CLI -------------------------------------------------------------------


class _FakeAccount:
    account_id = "primary"

    def is_configured(self):
        return True


def _cli(monkeypatch):
    monkeypatch.setattr(asc_manager, "load_account", lambda a: _FakeAccount())
    monkeypatch.setattr(asc_manager, "make_managers", lambda a: None)


def test_cli_version_bad_usage_exits_two(tmp_path, monkeypatch):
    (tmp_path / "secrets.example.yml").write_text(
        'accounts:\n  primary:\n    asc_api:\n      key_id: "ABCDE12345"\n'
        '      issuer_id: "x"\n      key_content: "REPLACE_WITH"\n')
    monkeypatch.chdir(tmp_path)
    assert asc_manager.main(["version"]) == 2
    assert asc_manager.main(["version", "frobnicate", "me.app"]) == 2
    assert asc_manager.main(["version", "set", "me.app"]) == 2


def test_cli_version_list_renders_platform_lines(monkeypatch, capsys):
    _cli(monkeypatch)
    monkeypatch.setattr(service, "version_list", lambda *a, **k: {
        "command": "version_list", "ok": True, "dry_run": False,
        "bundle_id": "me.demo.app",
        "versions": [
            {"id": "ver-ios", "platform": "IOS", "version_string": "1.0.0",
             "state": "WAITING_FOR_REVIEW", "editable": False},
            {"id": "ver-mac", "platform": "MAC_OS", "version_string": "1.0",
             "state": "PREPARE_FOR_SUBMISSION", "editable": True},
        ]})
    assert asc_manager.main(["version", "list", "me.demo.app"]) == 0
    out = capsys.readouterr().out
    assert "IOS 1.0.0 — WAITING_FOR_REVIEW" in out
    assert "MAC_OS 1.0 — PREPARE_FOR_SUBMISSION (editable)" in out


def test_cli_version_set_passes_platform_and_renders_rename(monkeypatch, capsys):
    _cli(monkeypatch)
    captured = {}

    def fake_set(bundle_id, version, platform="IOS", account="primary",
                 sync_files=True):
        captured.update(platform=platform, version=version, sync_files=sync_files)
        return {"command": "version_set", "ok": True, "dry_run": False,
                "bundle_id": bundle_id, "platform": platform,
                "version_string": version, "changed": True, "created": False,
                "previous_version_string": "1.0",
                "state": "PREPARE_FOR_SUBMISSION",
                "local_files": {"ok": True, "changed": True,
                                "files": [{"path": "apps/ios/project.yml",
                                           "occurrences": 1}]}}

    monkeypatch.setattr(service, "version_set", fake_set)
    code = asc_manager.main(
        ["version", "set", "me.demo.app", "1.0.0", "--platform", "MAC_OS"])
    assert code == 0
    assert captured == {"platform": "MAC_OS", "version": "1.0.0", "sync_files": True}
    out = capsys.readouterr().out
    assert "1.0 → 1.0.0" in out
    assert "apps/ios/project.yml" in out          # les fichiers touchés sont rendus


def test_cli_version_set_no_sync_files_flag(monkeypatch, capsys):
    _cli(monkeypatch)
    captured = {}

    def fake_set(bundle_id, version, platform="IOS", account="primary",
                 sync_files=True):
        captured.update(sync_files=sync_files)
        return {"command": "version_set", "ok": True, "dry_run": False,
                "bundle_id": bundle_id, "platform": platform,
                "version_string": version, "changed": False, "created": False,
                "previous_version_string": None,
                "state": "PREPARE_FOR_SUBMISSION"}

    monkeypatch.setattr(service, "version_set", fake_set)
    code = asc_manager.main(
        ["version", "set", "me.demo.app", "1.0.0", "--no-sync-files"])
    assert code == 0
    assert captured == {"sync_files": False}


def test_cli_version_json_envelope_verbatim(monkeypatch, capsys):
    _cli(monkeypatch)
    envelope = {"command": "version_list", "ok": True, "dry_run": False,
                "bundle_id": "me.demo.app", "versions": []}
    monkeypatch.setattr(service, "version_list", lambda *a, **k: envelope)
    assert asc_manager.main(["version", "list", "me.demo.app", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == envelope


# -- MCP -------------------------------------------------------------------


def _mcp_call(name, arguments=None):
    return mcp.handle_message({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}}})


def test_mcp_exposes_version_tools():
    response = mcp.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = {t["name"]: t for t in response["result"]["tools"]}
    assert tools["version_list"]["annotations"]["readOnlyHint"] is True
    assert tools["version_set"]["annotations"]["idempotentHint"] is True
    assert tools["version_set"]["annotations"]["readOnlyHint"] is False


def test_mcp_version_tools_are_library_first(monkeypatch):
    monkeypatch.setattr(service, "version_list", lambda bundle_id, account="primary": {
        "command": "version_list", "ok": True, "versions": []})
    captured = {}

    def fake_set(bundle_id, version, platform="IOS", account="primary"):
        captured.update(platform=platform)
        return {"command": "version_set", "ok": True, "changed": False}

    monkeypatch.setattr(service, "version_set", fake_set)
    assert _mcp_call("version_list", {"bundle_id": "me.demo.app"})[
        "result"]["structuredContent"]["ok"] is True
    _mcp_call("version_set", {"bundle_id": "me.demo.app", "version": "1.0.0",
                              "platform": "MAC_OS"})
    assert captured["platform"] == "MAC_OS"


# -- propagation de la version commerciale vers le depot ---------------------
#
# Vecu 2026-07-31 : `andp version set me.meeshy.app 1.0.1` a bien renomme
# l'enregistrement ASC, mais apps/ios/project.yml est reste a 1.0.0 — tout
# build local produisait alors un CFBundleShortVersionString en desaccord avec
# la version qui attend le binaire.


def _project_yml(tmp_path, version="1.0.0"):
    d = tmp_path / "apps" / "ios"
    d.mkdir(parents=True)
    f = d / "project.yml"
    f.write_text(f'settings:\n  MARKETING_VERSION: "{version}"\n')
    return f


def test_version_set_propagates_to_project_yml(tmp_path, monkeypatch, ec_private_key_pem):
    _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, {"data": [
            _version("IOS", "1.0.0", "PREPARE_FOR_SUBMISSION", "ver-ios")]}),
        FakeResponse(200, {"data": _version("IOS", "1.0.1",
                                            "PREPARE_FOR_SUBMISSION", "ver-ios")}),
    )
    f = _project_yml(tmp_path)
    result = service.version_set("me.demo.app", "1.0.1", platform="IOS")
    assert result["ok"] is True
    assert 'MARKETING_VERSION: "1.0.1"' in f.read_text()
    assert result["local_files"]["changed"] is True
    assert result["local_files"]["files"][0]["path"] == "apps/ios/project.yml"


def test_version_set_syncs_the_repo_even_when_asc_is_already_right(
        tmp_path, monkeypatch, ec_private_key_pem):
    """Le cas vecu : ASC porte deja 1.0.1, mais le depot est reste en arriere.

    Un no-op cote ASC ne doit PAS dispenser de reconcilier les fichiers, sinon
    la derive survit exactement a la commande censee la corriger.
    """
    _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, {"data": [
            _version("IOS", "1.0.1", "PREPARE_FOR_SUBMISSION", "ver-ios")]}),
    )
    f = _project_yml(tmp_path, "1.0.0")
    result = service.version_set("me.demo.app", "1.0.1", platform="IOS")
    assert result["changed"] is False              # rien a faire cote ASC
    assert result["local_files"]["changed"] is True  # mais le depot, si
    assert 'MARKETING_VERSION: "1.0.1"' in f.read_text()


def test_version_set_can_skip_the_repo(tmp_path, monkeypatch, ec_private_key_pem):
    _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, {"data": [
            _version("IOS", "1.0.1", "PREPARE_FOR_SUBMISSION", "ver-ios")]}),
    )
    f = _project_yml(tmp_path, "1.0.0")
    result = service.version_set("me.demo.app", "1.0.1", platform="IOS",
                                 sync_files=False)
    assert result["ok"] is True
    assert "local_files" not in result
    assert '"1.0.0"' in f.read_text()


def test_version_set_does_not_touch_the_repo_when_asc_refuses(
        tmp_path, monkeypatch, ec_private_key_pem):
    """Un enregistrement verrouille = echec : le depot ne doit pas partir devant."""
    _wire(
        tmp_path, monkeypatch, ec_private_key_pem,
        FakeResponse(200, APP),
        FakeResponse(200, {"data": [
            _version("IOS", "1.0.0", "WAITING_FOR_REVIEW", "ver-ios")]}),
    )
    f = _project_yml(tmp_path, "1.0.0")
    result = service.version_set("me.demo.app", "2.0.0", platform="IOS")
    assert result["ok"] is False
    assert '"1.0.0"' in f.read_text()
