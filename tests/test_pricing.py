"""PricingManager — modern appPriceSchedules / appPricePoints model.

The appPriceTier system is gone: a price is a *schedule* whose manualPrice for
the base territory references an appPricePoint; other territories auto-derive.
"""
from conftest import FakeResponse, FakeSession, make_test_managers


def _pp(pp_id, territory, price):
    return {"id": pp_id, "type": "appPricePoints",
            "attributes": {"customerPrice": price},
            "relationships": {"territory": {"data": {"type": "territories", "id": territory}}}}


def test_list_price_points_paginates_beyond_one_page():
    session = FakeSession()
    page1 = {"data": [_pp(f"pp{i}", "USA", f"{i}.99") for i in range(50)],
             "links": {"next": "https://api.appstoreconnect.apple.com/v1/apps/APP/appPricePoints?cursor=2"}}
    page2 = {"data": [_pp("pp99", "USA", "99.99")], "links": {}}
    session.queue(FakeResponse(200, page1), FakeResponse(200, page2))
    pts = make_test_managers(session).pricing.list_price_points("APP", "USA")
    assert len(pts) == 51                       # B2: both pages, not just 50
    assert pts[-1]["attributes"]["customerPrice"] == "99.99"


def test_find_price_point_matches_by_decimal_not_float():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [
        _pp("free", "USA", "0.00"), _pp("tierA", "USA", "0.99"),
        _pp("tierB", "USA", "1.10")], "links": {}}))
    pt = make_test_managers(session).pricing.find_price_point("APP", "USA", "1.10")
    assert pt["id"] == "tierB"                   # S6: Decimal, no 1.10 float drift


def test_find_price_point_returns_none_when_absent():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [_pp("tierA", "USA", "0.99")], "links": {}}))
    assert make_test_managers(session).pricing.find_price_point("APP", "USA", "4.99") is None


def test_find_free_price_point():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [
        _pp("tierA", "USA", "0.99"), _pp("free", "USA", "0.00")], "links": {}}))
    pt = make_test_managers(session).pricing.find_free_price_point("APP", "USA")
    assert pt["id"] == "free"


def test_get_schedule_returns_none_when_absent():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": None}))
    assert make_test_managers(session).pricing.get_schedule("APP") is None


def test_set_schedule_posts_json_api_replace_body():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": {"id": "sched-1"}}))
    make_test_managers(session).pricing.set_schedule("APP", "USA", "pp-9")
    req = session.requests[-1]
    assert req["method"] == "POST"
    assert req["url"].endswith("/v1/appPriceSchedules")
    body = req["json"]
    rel = body["data"]["relationships"]
    assert rel["app"]["data"]["id"] == "APP"
    assert rel["baseTerritory"]["data"]["id"] == "USA"
    temp = rel["manualPrices"]["data"][0]["id"]
    inc = body["included"][0]
    assert inc["id"] == temp                     # temp id links relationship <-> included
    assert inc["relationships"]["appPricePoint"]["data"]["id"] == "pp-9"
    assert inc["attributes"]["startDate"] is None  # null => live immediately


def test_current_base_price_point_id_picks_the_live_price():
    session = FakeSession()
    # schedule exists...
    session.queue(FakeResponse(200, {"data": {"id": "sched-1"}}))
    # ...manualPrices: one live (startDate null) + one future-scheduled
    session.queue(FakeResponse(200, {
        "data": [
            {"id": "ap1", "type": "appPrices", "attributes": {"startDate": None},
             "relationships": {"appPricePoint": {"data": {"type": "appPricePoints", "id": "pp-live"}}}},
            {"id": "ap2", "type": "appPrices", "attributes": {"startDate": "2099-01-01"},
             "relationships": {"appPricePoint": {"data": {"type": "appPricePoints", "id": "pp-future"}}}},
        ],
        "included": [
            {"id": "pp-live", "type": "appPricePoints",
             "relationships": {"territory": {"data": {"id": "USA"}}}},
            {"id": "pp-future", "type": "appPricePoints",
             "relationships": {"territory": {"data": {"id": "USA"}}}},
        ],
        "links": {}}))
    pid = make_test_managers(session).pricing.current_base_price_point_id("APP", "USA")
    assert pid == "pp-live"                       # S3: the active price, not the future one


def test_current_base_price_point_id_recognizes_a_past_start_date():
    """S3: the live price may carry a PAST startDate (not just null); it must be
    recognised, else a same-price reconcile re-POSTs a full-replace schedule."""
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": {"id": "sched-1"}}))
    session.queue(FakeResponse(200, {
        "data": [
            {"id": "ap1", "type": "appPrices", "attributes": {"startDate": "2020-01-01"},
             "relationships": {"appPricePoint": {"data": {"id": "pp-live"}}}},
            {"id": "ap2", "type": "appPrices", "attributes": {"startDate": "2099-01-01"},
             "relationships": {"appPricePoint": {"data": {"id": "pp-future"}}}},
        ],
        "included": [
            {"id": "pp-live", "type": "appPricePoints",
             "relationships": {"territory": {"data": {"id": "USA"}}}},
            {"id": "pp-future", "type": "appPricePoints",
             "relationships": {"territory": {"data": {"id": "USA"}}}},
        ],
        "links": {}}))
    pid = make_test_managers(session).pricing.current_base_price_point_id(
        "APP", "USA", today="2026-07-21")
    assert pid == "pp-live"          # past-dated price is live; future one ignored


def test_current_base_price_point_id_none_without_schedule():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": None}))
    assert make_test_managers(session).pricing.current_base_price_point_id("APP", "USA") is None
