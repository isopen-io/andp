"""`store plan` / `store apply` service layer: andp.yml + metadata → ASC."""
import json

import pytest

from andp import listing_service, service
from conftest import real_secrets_yaml, write_secrets
from listing_fakes import fake_managers_with_app, live_state

ANDP_YML = """
store:
  metadata_dir: md
  env_file: secrets.env
  app:
    content_rights: USES_THIRD_PARTY_CONTENT
  categories:
    primary: SOCIAL_NETWORKING
    secondary: EDUCATION
  version:
    copyright: "2026 Acme"
  review:
    contact_first_name: Ada
    demo_account_required: true
    demo_account_name_env: DEMO_USER
    demo_account_password_env: DEMO_PASSWORD
  age_rating:
    socialMedia: true
"""


def _project(tmp_path, yml=ANDP_YML):
    (tmp_path / "andp.yml").write_text(yml)
    (tmp_path / "secrets.env").write_text("DEMO_USER=rev\nDEMO_PASSWORD=very-secret\n")
    md = tmp_path / "md" / "fr-FR"
    md.mkdir(parents=True)
    (md / "subtitle.txt").write_text("Chat et vocaux\n")
    (md / "promotional_text.txt").write_text("Nouveau\n")
    return tmp_path


@pytest.fixture
def configured(tmp_path, monkeypatch, ec_private_key_pem):
    write_secrets(tmp_path, real_secrets_yaml(ec_private_key_pem))
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    state = live_state()
    managers = fake_managers_with_app(state)
    monkeypatch.setattr(service, "make_managers", lambda account: managers)
    return managers, state


@pytest.fixture
def offline(tmp_path, monkeypatch):
    (tmp_path / "secrets.example.yml").write_text(
        "accounts:\n  primary:\n    asc_api:\n      key_id: \"REPLACE\"\n")
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_plan_without_credentials_still_validates_everything(offline):
    r = listing_service.store_plan("me.demo.app")
    assert r["ok"] is True and r["dry_run"] is True
    assert r["desired"]["app_info_localizations"] == 1
    assert r["desired"]["review"] == 4


def test_plan_without_credentials_reports_validation_errors(offline):
    (offline / "md" / "fr-FR" / "subtitle.txt").write_text("x" * 31)
    r = listing_service.store_plan("me.demo.app")
    assert r["ok"] is False
    assert "fr-FR: subtitle: 31 characters, the App Store allows 30" in r["errors"]


def test_plan_lists_changes_masks_secrets_and_writes_nothing(configured):
    managers, _ = configured
    r = listing_service.store_plan("me.demo.app", version="1.2.0")
    assert r["ok"] is True and r["dry_run"] is False and r["written"] is False
    assert managers.writes == []
    fields = {(c["family"], c["field"]) for c in r["changes"]}
    assert ("app", "contentRightsDeclaration") in fields
    assert ("app_info_localization", "subtitle") in fields
    assert ("version_localization", "promotionalText") in fields
    assert ("age_rating", "socialMedia") in fields
    assert "very-secret" not in json.dumps(r)
    assert "_context" not in r


def test_plan_reports_an_unknown_app(configured, monkeypatch):
    monkeypatch.setattr(service, "make_managers",
                        lambda account: fake_managers_with_app(live_state(), found=False))
    r = listing_service.store_plan("me.demo.app")
    assert r["ok"] is False and r["error"]["code"] == "app_not_found"


def test_store_apply_writes_the_listing_once_and_age_rating_once(configured):
    managers, state = configured
    r = service.configure_store("me.demo.app", version="1.2.0")
    listing = r["blocks"]["listing"]
    assert listing["ok"] is True, listing
    kinds = [w[0] for w in managers.writes]
    assert kinds.count("update_age_rating") == 1
    assert "update_app" in kinds and "save_review_detail" in kinds
    assert state["review"]["attributes"]["demoAccountPassword"] == "very-secret"
    again = listing_service.store_plan("me.demo.app", version="1.2.0")
    assert again["changes"] == []


def test_store_apply_without_listing_sections_does_not_add_a_listing_block(
        tmp_path, monkeypatch, ec_private_key_pem):
    write_secrets(tmp_path, real_secrets_yaml(ec_private_key_pem))
    (tmp_path / "andp.yml").write_text("store:\n  pricing:\n    price: free\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(service, "configure_pricing",
                        lambda *a, **k: {"command": "configure_pricing", "ok": True})
    r = service.configure_store("me.demo.app")
    assert "listing" not in r["blocks"]


def test_store_apply_refuses_an_invalid_listing(configured):
    (configured[1])  # state unused
    import pathlib
    pathlib.Path("md/fr-FR/subtitle.txt").write_text("x" * 40)
    managers, _ = configured
    r = service.configure_store("me.demo.app", version="1.2.0")
    assert r["blocks"]["listing"]["ok"] is False
    assert not [w for w in managers.writes if w[0] != "update_age_rating"]
