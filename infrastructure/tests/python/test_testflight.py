"""Tests for infrastructure/asc/testflight.py — groupes beta, testeurs, What to Test, Beta App Review."""
import pytest

from testflight import TestFlightManager


def test_ensure_group_returns_existing(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(200, {"data": [{"id": "GRP1", "type": "betaGroups",
                                      "attributes": {"name": "Beta Externe"}}]})
    )
    group = TestFlightManager(asc_client).ensure_group("APP1", "Beta Externe")

    params = fake_session.requests[0]["params"]
    assert params["filter[app]"] == "APP1"
    assert params["filter[name]"] == "Beta Externe"
    assert group["id"] == "GRP1"
    assert len(fake_session.requests) == 1  # pas de création


def test_ensure_group_creates_when_missing(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(200, {"data": []}),
        fake_response(201, {"data": {"id": "GRP2", "type": "betaGroups"}}),
    )
    group = TestFlightManager(asc_client).ensure_group(
        "APP1", "Beta Externe", public_link_enabled=True, public_link_limit=500
    )

    data = fake_session.requests[1]["json"]["data"]
    assert data["type"] == "betaGroups"
    assert data["attributes"] == {
        "name": "Beta Externe",
        "publicLinkEnabled": True,
        "publicLinkLimit": 500,
    }
    assert data["relationships"]["app"]["data"] == {"type": "apps", "id": "APP1"}
    assert group["id"] == "GRP2"


def test_add_tester_creates_and_links_group(asc_client, fake_session, fake_response):
    fake_session.queue(fake_response(201, {"data": {"id": "T1", "type": "betaTesters"}}))
    mgr = TestFlightManager(asc_client)

    tester = mgr.add_tester("GRP1", "jc@sylorion.com", first_name="JC", last_name="N. M.")

    data = fake_session.requests[0]["json"]["data"]
    assert data["attributes"] == {
        "email": "jc@sylorion.com", "firstName": "JC", "lastName": "N. M.",
    }
    assert data["relationships"]["betaGroups"]["data"] == [{"type": "betaGroups", "id": "GRP1"}]
    assert tester["id"] == "T1"


def test_add_existing_tester_falls_back_to_group_link(asc_client, fake_session, fake_response):
    """409 ENTITY_ERROR → le testeur existe déjà : on le retrouve puis on le lie au groupe."""
    fake_session.queue(
        fake_response(409, {"errors": [{"status": "409", "detail": "already exists"}]}),
        fake_response(200, {"data": [{"id": "T9", "type": "betaTesters"}]}),
        fake_response(204),
    )
    mgr = TestFlightManager(asc_client)

    tester = mgr.add_tester("GRP1", "jc@sylorion.com")

    lookup = fake_session.requests[1]
    assert lookup["params"]["filter[email]"] == "jc@sylorion.com"
    link = fake_session.requests[2]
    assert link["method"] == "POST"
    assert link["url"].endswith("/v1/betaGroups/GRP1/relationships/betaTesters")
    assert link["json"]["data"] == [{"type": "betaTesters", "id": "T9"}]
    assert tester["id"] == "T9"


def test_add_build_to_group(asc_client, fake_session, fake_response):
    fake_session.queue(fake_response(204))
    TestFlightManager(asc_client).add_build_to_group("GRP1", "B1")

    request = fake_session.requests[0]
    assert request["url"].endswith("/v1/betaGroups/GRP1/relationships/builds")
    assert request["json"]["data"] == [{"type": "builds", "id": "B1"}]


def test_set_what_to_test_creates_localization(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(200, {"data": []}),
        fake_response(201, {"data": {"id": "BBL1", "type": "betaBuildLocalizations"}}),
    )
    mgr = TestFlightManager(asc_client)

    mgr.set_what_to_test("B1", "fr-FR", "Tester la nouvelle traduction hors-ligne.")

    create = fake_session.requests[1]["json"]["data"]
    assert create["attributes"] == {
        "locale": "fr-FR", "whatsNew": "Tester la nouvelle traduction hors-ligne.",
    }
    assert create["relationships"]["build"]["data"] == {"type": "builds", "id": "B1"}


def test_set_what_to_test_updates_existing_localization(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(200, {"data": [{"id": "BBL1", "type": "betaBuildLocalizations",
                                      "attributes": {"locale": "fr-FR"}}]}),
        fake_response(200, {"data": {"id": "BBL1", "type": "betaBuildLocalizations"}}),
    )
    mgr = TestFlightManager(asc_client)

    mgr.set_what_to_test("B1", "fr-FR", "Nouveau scénario de test.")

    update = fake_session.requests[1]
    assert update["method"] == "PATCH"
    assert update["url"].endswith("/v1/betaBuildLocalizations/BBL1")
    assert update["json"]["data"]["attributes"] == {"whatsNew": "Nouveau scénario de test."}


def test_submit_for_beta_review(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(201, {"data": {"id": "SUB1", "type": "betaAppReviewSubmissions",
                                     "attributes": {"betaReviewState": "WAITING_FOR_REVIEW"}}})
    )
    submission = TestFlightManager(asc_client).submit_for_beta_review("B1")

    data = fake_session.requests[0]["json"]["data"]
    assert data["type"] == "betaAppReviewSubmissions"
    assert data["relationships"]["build"]["data"] == {"type": "builds", "id": "B1"}
    assert submission["attributes"]["betaReviewState"] == "WAITING_FOR_REVIEW"
