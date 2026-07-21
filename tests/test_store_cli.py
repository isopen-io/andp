"""CLI `store` command: pricing / availability / age-rating / apply.

Thin adapter over the service layer (library-first) — parses args, prints a human
or --json envelope, exits 0/1/2.
"""
import json

import pytest

from andp import service
from andp.asc import asc_manager
from conftest import FakeResponse, FakeSession, make_test_managers, real_secrets_yaml


@pytest.fixture
def cli(tmp_path, monkeypatch, ec_private_key_pem):
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    return session, tmp_path


def _app():
    return FakeResponse(200, {"data": [{"id": "app-9"}]})


def _pp(pid, price):
    return {"id": pid, "attributes": {"customerPrice": price},
            "relationships": {"territory": {"data": {"id": "USA"}}}}


def test_cli_store_pricing(cli, capsys):
    session, _ = cli
    session.queue(_app(), FakeResponse(200, {"data": [_pp("pp-9", "0.99")], "links": {}}),
                  FakeResponse(200, {"data": None}), FakeResponse(200, {"data": {"id": "s1"}}))
    code = asc_manager.main(["store", "pricing", "me.demo.app", "--price", "0.99"])
    assert code == 0
    assert "pricing" in capsys.readouterr().out.lower()


def test_cli_store_pricing_json(cli, capsys):
    session, _ = cli
    session.queue(_app(), FakeResponse(200, {"data": [_pp("pp-9", "0.99")], "links": {}}),
                  FakeResponse(200, {"data": None}), FakeResponse(200, {"data": {"id": "s1"}}))
    code = asc_manager.main(["store", "pricing", "me.demo.app", "--price", "0.99", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["command"] == "configure_pricing" and payload["changed"] is True


def test_cli_store_availability_all(cli, capsys):
    session, _ = cli
    session.queue(
        _app(), FakeResponse(200, {"data": [{"id": "USA"}, {"id": "FRA"}], "links": {}}),
        FakeResponse(200, {"data": None}),                      # no current availability
        FakeResponse(200, {"data": {"id": "av-1"}}))
    code = asc_manager.main(["store", "availability", "me.demo.app", "--all", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["territory_count"] == 2


def test_cli_store_age_rating_config(cli, capsys):
    session, tmp = cli
    (tmp / "r.json").write_text(json.dumps({"gambling": True}))
    session.queue(
        _app(),
        FakeResponse(200, {"data": [{"id": "info", "attributes": {"state": "PREPARE_FOR_SUBMISSION"}}], "links": {}}),
        FakeResponse(200, {"data": {"id": "decl-9", "attributes": {"gambling": False}}}),
        FakeResponse(200, {"data": {"id": "decl-9"}}))
    code = asc_manager.main(["store", "age-rating", "me.demo.app", "--config", "r.json", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["updated_fields"] == ["gambling"]


def test_cli_store_apply_reads_andp_yml(cli, capsys):
    session, tmp = cli
    (tmp / "andp.yml").write_text('store:\n  pricing:\n    price: "0.99"\n')
    session.queue(_app(), FakeResponse(200, {"data": [_pp("pp-9", "0.99")], "links": {}}),
                  FakeResponse(200, {"data": None}), FakeResponse(200, {"data": {"id": "s1"}}))
    code = asc_manager.main(["store", "apply", "me.demo.app", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["blocks"]["pricing"]["ok"] is True


def test_cli_store_unknown_sub(cli, capsys):
    code = asc_manager.main(["store", "wat", "me.demo.app"])
    assert code == 2
    assert "Usage" in capsys.readouterr().out


def test_cli_store_pricing_error_exit_1(cli, capsys):
    session, _ = cli
    session.queue(_app(), FakeResponse(200, {"data": [_pp("pp-9", "0.99")], "links": {}}))  # 4.99 absent
    code = asc_manager.main(["store", "pricing", "me.demo.app", "--price", "4.99"])
    assert code == 1
