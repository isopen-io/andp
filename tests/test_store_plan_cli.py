"""CLI `store plan` (read-only diff) and `store apply --version/--metadata`."""
import json

import pytest

from andp import listing_service, service
from andp.asc import asc_manager
from conftest import real_secrets_yaml, write_secrets
from listing_fakes import fake_managers_with_app, live_state


@pytest.fixture
def project(tmp_path, monkeypatch, ec_private_key_pem):
    write_secrets(tmp_path, real_secrets_yaml(ec_private_key_pem))
    (tmp_path / "andp.yml").write_text(
        "store:\n  version:\n    copyright: \"2026 Acme\"\n"
        "  review:\n    demo_account_password_env: PW\n")
    monkeypatch.setenv("PW", "hunter2-secret")
    monkeypatch.chdir(tmp_path)
    managers = fake_managers_with_app(live_state())
    monkeypatch.setattr(service, "make_managers", lambda a: managers)
    return managers


def test_store_plan_prints_the_diff_and_says_nothing_was_written(project, capsys):
    code = asc_manager.main(["store", "plan", "me.demo.app", "--version", "1.2.0"])
    out = capsys.readouterr().out
    assert code == 0
    assert "copyright" in out and "2025 Acme" in out and "2026 Acme" in out
    assert "demoAccountPassword" in out and "hunter2-secret" not in out
    assert "nothing was written" in out.lower()
    assert project.writes == []


def test_store_plan_json(project, capsys):
    code = asc_manager.main(["store", "plan", "me.demo.app", "--version", "1.2.0", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["command"] == "store_plan" and payload["written"] is False
    assert "hunter2-secret" not in json.dumps(payload)


def test_store_plan_exits_1_on_validation_errors(project, capsys, tmp_path):
    (tmp_path / "andp.yml").write_text("store:\n  app:\n    content_rights: MAYBE\n")
    code = asc_manager.main(["store", "plan", "me.demo.app"])
    assert code == 1
    assert "contentRightsDeclaration" in capsys.readouterr().out


def test_store_plan_passes_metadata_dir(project, monkeypatch, capsys):
    seen = {}

    def fake_plan(bundle_id, **kwargs):
        seen.update(kwargs)
        return {"command": "store_plan", "ok": True, "dry_run": False, "written": False,
                "changes": [], "unchanged": 0, "errors": [], "warnings": [], "notes": [],
                "read_only": {}, "version": None}
    monkeypatch.setattr(listing_service, "store_plan", fake_plan)
    asc_manager.main(["store", "plan", "me.demo.app", "--metadata", "fastlane/metadata"])
    assert seen["metadata_dir"] == "fastlane/metadata"


def test_store_apply_takes_version_and_metadata(project, monkeypatch):
    seen = {}

    def fake_store(bundle_id, **kwargs):
        seen.update(kwargs)
        return {"command": "configure_store", "ok": True, "dry_run": False, "blocks": {}}
    monkeypatch.setattr(service, "configure_store", fake_store)
    code = asc_manager.main(["store", "apply", "me.demo.app", "--version", "1.2.0",
                             "--metadata", "md"])
    assert code == 0 and seen["version"] == "1.2.0" and seen["metadata_dir"] == "md"


def test_andp_version_flag(capsys):
    from andp import __version__
    assert asc_manager.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"andp {__version__}"
