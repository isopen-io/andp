"""Service layer for store configuration: pricing / availability / age rating.

Library-first (CLI + MCP call these), dry-run aware, idempotent, every API error
wrapped into the standard {ok, error} envelope.
"""
import json

import pytest

from andp import service
from conftest import FakeResponse, FakeSession, make_test_managers, real_secrets_yaml


@pytest.fixture
def cfg(tmp_path, monkeypatch, ec_private_key_pem):
    """Configured dir + a recording FakeSession the test drives."""
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    monkeypatch.setattr(service, "make_managers", lambda account: make_test_managers(session))
    return session, tmp_path


@pytest.fixture
def dry(tmp_path, monkeypatch):
    """Unconfigured dir → dry-run (no credentials)."""
    (tmp_path / "secrets.example.yml").write_text("accounts:\n  primary:\n    asc_api:\n      key_id: \"REPLACE\"\n")
    monkeypatch.chdir(tmp_path)


def _app():
    return FakeResponse(200, {"data": [{"id": "app-9", "type": "apps"}]})


def _pp(pid, price, terr="USA"):
    return {"id": pid, "attributes": {"customerPrice": price},
            "relationships": {"territory": {"data": {"id": terr}}}}


# -- pricing ----------------------------------------------------------------

def test_pricing_sets_schedule_when_price_point_found(cfg):
    session, _ = cfg
    session.queue(
        _app(),
        FakeResponse(200, {"data": [_pp("pp-9", "0.99")], "links": {}}),  # price points
        FakeResponse(200, {"data": None}),                                # no schedule yet
        FakeResponse(200, {"data": {"id": "sched-1"}}),                   # POST
    )
    r = service.configure_pricing("me.demo.app", price="0.99")
    assert r["ok"] and r["changed"] is True and r["price_point_id"] == "pp-9"
    assert session.requests[-1]["url"].endswith("/v1/appPriceSchedules")


def test_pricing_free_resolves_zero_price_point(cfg):
    session, _ = cfg
    session.queue(
        _app(),
        FakeResponse(200, {"data": [_pp("pp-free", "0.00"), _pp("pp-9", "0.99")], "links": {}}),
        FakeResponse(200, {"data": None}),
        FakeResponse(200, {"data": {"id": "sched-1"}}),
    )
    r = service.configure_pricing("me.demo.app", price="free")
    assert r["ok"] and r["changed"] is True and r["price_point_id"] == "pp-free"


def test_pricing_idempotent_skip_when_already_set(cfg):
    session, _ = cfg
    session.queue(
        _app(),
        FakeResponse(200, {"data": [_pp("pp-9", "0.99")], "links": {}}),
        FakeResponse(200, {"data": {"id": "sched-1"}}),                    # schedule exists
        FakeResponse(200, {                                               # manualPrices
            "data": [{"id": "ap1", "attributes": {"startDate": None},
                      "relationships": {"appPricePoint": {"data": {"id": "pp-9"}}}}],
            "included": [{"id": "pp-9", "type": "appPricePoints",
                          "relationships": {"territory": {"data": {"id": "USA"}}}}],
            "links": {}}),
    )
    r = service.configure_pricing("me.demo.app", price="0.99")
    assert r["ok"] and r["changed"] is False and r["detail"] == "already set"
    assert all(rq["method"] != "POST" for rq in session.requests)         # no write


def test_pricing_price_point_not_found_is_wrapped_error(cfg):
    session, _ = cfg
    session.queue(_app(), FakeResponse(200, {"data": [_pp("pp-9", "0.99")], "links": {}}))
    r = service.configure_pricing("me.demo.app", price="4.99")
    assert r["ok"] is False and r["error"]["code"] == "price_point_not_found"


def test_pricing_dry_run_is_planned_and_touches_no_manager(dry):
    r = service.configure_pricing("me.demo.app", price="0.99")
    assert r["ok"] and r["dry_run"] is True and r["changed"] is None


def test_pricing_not_configured_errors(cfg):
    r = service.configure_pricing("me.demo.app")  # no price anywhere
    assert r["ok"] is False and r["error"]["code"] == "not_configured"


# -- availability -----------------------------------------------------------

def _avail(flag=False):
    return FakeResponse(200, {"data": {"id": "av-1", "attributes": {"availableInNewTerritories": flag}}})


def _all_terr(*ids):
    return FakeResponse(200, {"data": [{"id": i} for i in ids], "links": {}})


def _ta(t, avail=True):
    return {"id": f"ta-{t}", "attributes": {"available": avail},
            "relationships": {"territory": {"data": {"id": t}}}}


def test_availability_sets_replacement_set(cfg):
    session, _ = cfg
    session.queue(
        _app(), _all_terr("USA", "FRA", "DEU"),
        _avail(False), FakeResponse(200, {"data": [_ta("USA")], "links": {}}),  # snapshot
        FakeResponse(200, {"data": {"id": "av-1"}}),                            # POST
    )
    r = service.configure_availability("me.demo.app", territories=["USA", "FRA"])
    assert r["ok"] and r["changed"] is True and r["territory_count"] == 2
    assert session.requests[-1]["url"].endswith("/v2/appAvailabilities")


def test_availability_all_expands_to_every_territory(cfg):
    session, _ = cfg
    session.queue(
        _app(), _all_terr("USA", "FRA", "DEU"),
        _avail(False), FakeResponse(200, {"data": [_ta("USA")], "links": {}}),
        FakeResponse(200, {"data": {"id": "av-1"}}),
    )
    r = service.configure_availability("me.demo.app", territories="all")
    assert r["ok"] and r["changed"] is True and r["territory_count"] == 3


def test_availability_unknown_territory_is_error(cfg):
    session, _ = cfg
    session.queue(_app(), _all_terr("USA", "FRA"))
    r = service.configure_availability("me.demo.app", territories=["USA", "ZZ"])
    assert r["ok"] is False and r["error"]["code"] == "unknown_territory"


def test_availability_empty_set_is_refused_delist_guard(cfg):
    session, _ = cfg
    session.queue(_app(), _all_terr("USA", "FRA"))
    r = service.configure_availability("me.demo.app", territories=[])
    assert r["ok"] is False and r["error"]["code"] == "empty_territories"


def test_availability_preserves_new_territories_flag_when_unspecified(cfg):
    session, _ = cfg
    session.queue(
        _app(), _all_terr("USA", "FRA"),
        _avail(True), FakeResponse(200, {"data": [_ta("USA")], "links": {}}),  # current flag True
        FakeResponse(200, {"data": {"id": "av-1"}}),
    )
    r = service.configure_availability("me.demo.app", territories=["USA", "FRA"])
    assert r["ok"] and r["available_in_new_territories"] is True               # S1: preserved
    assert session.requests[-1]["json"]["data"]["attributes"]["availableInNewTerritories"] is True


def test_availability_idempotent_skip(cfg):
    session, _ = cfg
    session.queue(
        _app(), _all_terr("USA", "FRA"),
        _avail(False), FakeResponse(200, {"data": [_ta("USA")], "links": {}}),
    )
    r = service.configure_availability("me.demo.app", territories=["USA"])
    assert r["ok"] and r["changed"] is False
    assert all(rq["method"] != "POST" for rq in session.requests)


def test_availability_all_idempotent_skip(cfg):
    session, _ = cfg
    session.queue(
        _app(), _all_terr("USA", "FRA"),
        _avail(False), FakeResponse(200, {"data": [_ta("USA"), _ta("FRA")], "links": {}}),
    )
    r = service.configure_availability("me.demo.app", territories="all")
    assert r["ok"] and r["changed"] is False           # already every territory
    assert all(rq["method"] != "POST" for rq in session.requests)


def test_availability_dry_run(dry):
    r = service.configure_availability("me.demo.app", territories=["USA"])
    assert r["ok"] and r["dry_run"] is True and r["changed"] is None


# -- age rating -------------------------------------------------------------

def _appinfos(state="PREPARE_FOR_SUBMISSION"):
    return FakeResponse(200, {"data": [{"id": "info-edit", "attributes": {"state": state}}], "links": {}})


def _decl(**attrs):
    return FakeResponse(200, {"data": {"id": "decl-9", "attributes": attrs}})


def test_age_rating_patches_only_the_diff(cfg):
    session, _ = cfg
    session.queue(
        _app(), _appinfos(),
        _decl(gambling=False, violenceCartoonOrFantasy="NONE"),
        FakeResponse(200, {"data": {"id": "decl-9"}}),   # PATCH
    )
    r = service.configure_age_rating("me.demo.app", declaration={
        "gambling": True, "violenceCartoonOrFantasy": "NONE"})
    assert r["ok"] and r["changed"] is True and r["updated_fields"] == ["gambling"]
    assert session.requests[-1]["method"] == "PATCH"


def test_age_rating_idempotent_skip(cfg):
    session, _ = cfg
    session.queue(_app(), _appinfos(), _decl(gambling=False))
    r = service.configure_age_rating("me.demo.app", declaration={"gambling": False})
    assert r["ok"] and r["changed"] is False
    assert all(rq["method"] != "PATCH" for rq in session.requests)


def test_age_rating_unknown_key_is_validation_error_before_io(cfg):
    session, _ = cfg  # nothing queued: must fail before any request
    r = service.configure_age_rating("me.demo.app", declaration={"bogusField": "NONE"})
    assert r["ok"] is False and r["error"]["code"] == "invalid_age_rating"
    assert session.requests == []


def test_age_rating_no_declaration_found(cfg):
    session, _ = cfg
    session.queue(_app(), FakeResponse(200, {"data": [], "links": {}}))  # no appInfos
    r = service.configure_age_rating("me.demo.app", declaration={"gambling": True})
    assert r["ok"] is False and r["error"]["code"] == "no_declaration"


def test_age_rating_config_path_file_is_loaded(cfg):
    session, tmp = cfg
    (tmp / "rating.json").write_text(json.dumps({"gambling": True}))
    session.queue(_app(), _appinfos(), _decl(gambling=False),
                  FakeResponse(200, {"data": {"id": "decl-9"}}))
    r = service.configure_age_rating("me.demo.app", declaration={"config_path": "rating.json"})
    assert r["ok"] and r["changed"] is True and r["updated_fields"] == ["gambling"]


def test_age_rating_dry_run(dry):
    r = service.configure_age_rating("me.demo.app", declaration={"gambling": True})
    assert r["ok"] and r["dry_run"] is True and r["fields"] == ["gambling"]


def test_age_rating_config_path_non_dict_is_bad_config(cfg):
    session, tmp = cfg
    (tmp / "r.json").write_text("[1, 2, 3]")            # top-level array, not an object
    r = service.configure_age_rating("me.demo.app", declaration={"config_path": "r.json"})
    assert r["ok"] is False and r["error"]["code"] == "bad_config"
    assert session.requests == []                        # failed before any API call


def test_pricing_malformed_andp_yml_is_wrapped(cfg):
    session, tmp = cfg
    (tmp / "andp.yml").write_text("store: {pricing: {price: '0.99'")  # unterminated -> YAMLError
    r = service.configure_pricing("me.demo.app", price="0.99")
    assert r["ok"] is False and r["error"]["code"] == "bad_config"    # no raw YAMLError leak


def test_configure_store_contains_a_raising_block(cfg, monkeypatch):
    session, tmp = cfg
    (tmp / "andp.yml").write_text(
        'store:\n  pricing:\n    price: "0.99"\n'
        '  availability:\n    territories: [USA]\n')

    def _boom(*a, **k):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(service, "configure_pricing", _boom)
    session.queue(  # availability still runs after the pricing block blows up
        _app(), _all_terr("USA", "FRA"), FakeResponse(200, {"data": None}),
        FakeResponse(200, {"data": {"id": "av-1"}}))
    r = service.configure_store("me.demo.app")
    assert r["ok"] is False                               # a block failed...
    assert r["blocks"]["pricing"]["ok"] is False          # ...contained, not raised
    assert r["blocks"]["availability"]["ok"] is True      # ...and later blocks still ran


# -- configure_store (best-effort orchestration) ----------------------------

def test_configure_store_runs_only_configured_blocks(cfg):
    session, tmp = cfg
    (tmp / "andp.yml").write_text('store:\n  pricing:\n    price: "0.99"\n')
    session.queue(
        _app(), FakeResponse(200, {"data": [_pp("pp-9", "0.99")], "links": {}}),
        FakeResponse(200, {"data": None}), FakeResponse(200, {"data": {"id": "sched-1"}}),
    )
    r = service.configure_store("me.demo.app")
    assert r["ok"] is True
    assert r["blocks"]["pricing"]["ok"] is True
    assert r["blocks"]["availability"] == {"skipped": "not configured"}
    assert r["blocks"]["age_rating"] == {"skipped": "not configured"}


def test_configure_store_best_effort_partial_failure(cfg):
    session, tmp = cfg
    (tmp / "andp.yml").write_text(
        'store:\n  pricing:\n    price: "4.99"\n'
        '  availability:\n    territories: [USA]\n')
    session.queue(
        _app(), FakeResponse(200, {"data": [_pp("pp-9", "0.99")], "links": {}}),  # pricing: 4.99 absent
        _app(), _all_terr("USA", "FRA"), FakeResponse(200, {"data": None}),       # availability: no current
        FakeResponse(200, {"data": {"id": "av-1"}}),                              # availability POST
    )
    r = service.configure_store("me.demo.app")
    assert r["ok"] is False                                    # a block failed
    assert r["blocks"]["pricing"]["ok"] is False
    assert r["blocks"]["availability"]["ok"] is True           # but availability still applied
