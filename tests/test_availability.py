"""AvailabilityManager — appAvailabilities v2 / territoryAvailabilities.

deliver has no territory support at all, so this exceeds parity. The danger is
silent delisting: reads MUST paginate (B2) and the available set MUST filter on
attributes.available == true (N2).
"""
from conftest import FakeResponse, FakeSession, make_test_managers


def _ta(territory, available=True):
    return {"id": f"ta-{territory}", "type": "territoryAvailabilities",
            "attributes": {"available": available},
            "relationships": {"territory": {"data": {"type": "territories", "id": territory}}}}


def test_get_availability_returns_id_and_new_territories_flag():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": {"id": "av-1",
                  "attributes": {"availableInNewTerritories": True}}}))
    av = make_test_managers(session).availability.get_availability("APP")
    assert av == {"id": "av-1", "available_in_new_territories": True}


def test_get_availability_none_when_absent():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": None}))
    assert make_test_managers(session).availability.get_availability("APP") is None


def test_list_available_territories_filters_unavailable_and_paginates():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": {"id": "av-1", "attributes": {}}}))  # get_availability
    page1 = {"data": [_ta(f"T{i}") for i in range(50)],
             "links": {"next": "https://api.appstoreconnect.apple.com/v2/appAvailabilities/av-1/territoryAvailabilities?cursor=2"}}
    page2 = {"data": [_ta("USA"), _ta("XXX", available=False)], "links": {}}
    session.queue(FakeResponse(200, page1), FakeResponse(200, page2))
    terrs = make_test_managers(session).availability.list_available_territories("APP")
    assert "USA" in terrs and "T0" in terrs and "T49" in terrs   # both pages (B2)
    assert "XXX" not in terrs                                     # N2: available==false excluded
    assert len(terrs) == 51


def test_list_all_territories_paginates():
    session = FakeSession()
    page1 = {"data": [{"id": f"T{i}", "type": "territories"} for i in range(50)],
             "links": {"next": "https://api.appstoreconnect.apple.com/v1/territories?cursor=2"}}
    page2 = {"data": [{"id": "FRA", "type": "territories"}], "links": {}}
    session.queue(FakeResponse(200, page1), FakeResponse(200, page2))
    allt = make_test_managers(session).availability.list_all_territories()
    assert "FRA" in allt and len(allt) == 51


def test_availability_snapshot_bundles_id_flag_and_territories():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": {"id": "av-1",
                  "attributes": {"availableInNewTerritories": True}}}))
    session.queue(FakeResponse(200, {"data": [_ta("USA"), _ta("FRA"),
                  _ta("XXX", available=False)], "links": {}}))
    snap = make_test_managers(session).availability.availability_snapshot("APP")
    assert snap["id"] == "av-1"
    assert snap["available_in_new_territories"] is True
    assert snap["territories"] == {"USA", "FRA"}


def test_availability_snapshot_none_when_absent():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": None}))
    assert make_test_managers(session).availability.availability_snapshot("APP") is None


def test_set_availability_posts_v2_with_included_territories():
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": {"id": "av-2"}}))
    make_test_managers(session).availability.set_availability(
        "APP", ["USA", "FRA"], available_in_new_territories=True)
    req = session.requests[-1]
    assert req["method"] == "POST"
    assert req["url"].endswith("/v2/appAvailabilities")
    body = req["json"]
    assert body["data"]["attributes"]["availableInNewTerritories"] is True
    assert body["data"]["relationships"]["app"]["data"]["id"] == "APP"
    refs = body["data"]["relationships"]["territoryAvailabilities"]["data"]
    assert len(refs) == 2
    inc_terrs = {i["relationships"]["territory"]["data"]["id"] for i in body["included"]}
    assert inc_terrs == {"USA", "FRA"}
    assert all(i["attributes"]["available"] is True for i in body["included"])
    # temp ids link relationship refs <-> included objects
    assert {r["id"] for r in refs} == {i["id"] for i in body["included"]}
