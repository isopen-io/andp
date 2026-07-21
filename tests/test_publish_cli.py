"""CLI + service for the folder-convention publisher, and --ship wiring."""
import json
import os

import pytest

from andp import service
from andp.asc import asc_manager
from conftest import FakeResponse, FakeSession, make_test_managers, real_secrets_yaml


def _meta_tree(root):
    os.makedirs(os.path.join(root, "en-US"))
    with open(os.path.join(root, "en-US", "whatsNew.txt"), "w") as f:
        f.write("New stuff.\n")


def test_service_publish_pushes_metadata(tmp_path, monkeypatch, ec_private_key_pem):
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    root = str(tmp_path / "meta"); _meta_tree(root)
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),                 # find_app
        FakeResponse(200, {"data": [{"id": "ver-1", "attributes": {"appVersionState": "PREPARE_FOR_SUBMISSION"}}]}),  # ensure_version
        FakeResponse(200, {"data": [{"id": "loc-en", "attributes": {"locale": "en-US"}}]}),  # loc GET
        FakeResponse(200, {"data": {"id": "loc-en"}}),                  # loc PATCH
    )
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))

    result = service.publish("me.demo.app", "1.0", root)
    assert result["ok"] is True
    assert result["locales"]["en-US"]["metadata"] == "updated"


def test_service_publish_dry_run(tmp_path, monkeypatch):
    (tmp_path / "secrets.example.yml").write_text(
        'accounts:\n  primary:\n    asc_api:\n      key_id: "ABCDE12345"\n'
        '      issuer_id: "x"\n      key_content: "REPLACE_WITH"\n')
    monkeypatch.chdir(tmp_path)
    root = str(tmp_path / "meta"); _meta_tree(root)
    result = service.publish("me.demo.app", "1.0", root)
    assert result["ok"] is True
    assert result["dry_run"] is True


def test_cli_publish(tmp_path, monkeypatch, ec_private_key_pem, capsys):
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    root = str(tmp_path / "meta"); _meta_tree(root)
    session = FakeSession()
    session.queue(
        FakeResponse(200, {"data": [{"id": "app-9"}]}),
        FakeResponse(200, {"data": [{"id": "ver-1", "attributes": {"appVersionState": "PREPARE_FOR_SUBMISSION"}}]}),
        FakeResponse(200, {"data": [{"id": "loc-en", "attributes": {"locale": "en-US"}}]}),
        FakeResponse(200, {"data": {"id": "loc-en"}}),
    )
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))

    code = asc_manager.main(["publish", "me.demo.app", "1.0", root, "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["command"] == "publish"
    assert out["ok"] is True
