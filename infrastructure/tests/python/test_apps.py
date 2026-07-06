"""Tests for infrastructure/asc/apps.py — fiche app : recherche, appInfos, catégories, localisations.

Note : POST /v1/apps n'existe pas (la fiche se crée dans l'UI App Store Connect) ;
on ne fait que retrouver et configurer une app existante.
"""
import pytest

from apps import AppsManager


def test_find_app_filters_by_bundle_id(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(200, {"data": [{"id": "APP1", "type": "apps",
                                      "attributes": {"bundleId": "me.meeshy.app"}}]})
    )
    app = AppsManager(asc_client).find_app("me.meeshy.app")

    assert fake_session.requests[0]["params"]["filter[bundleId]"] == "me.meeshy.app"
    assert app["id"] == "APP1"


def test_find_app_returns_none_when_absent(asc_client, fake_session, fake_response):
    fake_session.queue(fake_response(200, {"data": []}))
    assert AppsManager(asc_client).find_app("me.absent") is None


def test_update_app_patches_attributes(asc_client, fake_session, fake_response):
    fake_session.queue(fake_response(200, {"data": {"id": "APP1", "type": "apps"}}))
    mgr = AppsManager(asc_client)

    mgr.update_app("APP1", {"contentRightsDeclaration": "DOES_NOT_USE_THIRD_PARTY_CONTENT"})

    request = fake_session.requests[0]
    assert request["method"] == "PATCH"
    assert request["url"].endswith("/v1/apps/APP1")
    data = request["json"]["data"]
    assert data == {
        "type": "apps", "id": "APP1",
        "attributes": {"contentRightsDeclaration": "DOES_NOT_USE_THIRD_PARTY_CONTENT"},
    }


def test_get_primary_app_info(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(200, {"data": [{"id": "INFO1", "type": "appInfos"}]})
    )
    info = AppsManager(asc_client).get_app_info("APP1")

    assert fake_session.requests[0]["url"].endswith("/v1/apps/APP1/appInfos")
    assert info["id"] == "INFO1"


def test_set_categories_patches_relationships(asc_client, fake_session, fake_response):
    fake_session.queue(fake_response(200, {"data": {"id": "INFO1", "type": "appInfos"}}))
    mgr = AppsManager(asc_client)

    mgr.set_categories("INFO1", primary="PRODUCTIVITY", secondary="UTILITIES")

    relationships = fake_session.requests[0]["json"]["data"]["relationships"]
    assert relationships["primaryCategory"]["data"] == {"type": "appCategories", "id": "PRODUCTIVITY"}
    assert relationships["secondaryCategory"]["data"] == {"type": "appCategories", "id": "UTILITIES"}


def test_ensure_app_info_localization_creates_when_missing(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(200, {"data": []}),  # aucune localisation fr-FR
        fake_response(201, {"data": {"id": "LOC1", "type": "appInfoLocalizations"}}),
    )
    mgr = AppsManager(asc_client)

    mgr.ensure_app_info_localization("INFO1", "fr-FR", {"name": "Meeshy", "subtitle": "Traduction"})

    create = fake_session.requests[1]
    assert create["method"] == "POST"
    data = create["json"]["data"]
    assert data["attributes"] == {"locale": "fr-FR", "name": "Meeshy", "subtitle": "Traduction"}
    assert data["relationships"]["appInfo"]["data"] == {"type": "appInfos", "id": "INFO1"}


def test_ensure_app_info_localization_patches_when_present(asc_client, fake_session, fake_response):
    fake_session.queue(
        fake_response(200, {"data": [{"id": "LOC1", "type": "appInfoLocalizations",
                                      "attributes": {"locale": "fr-FR"}}]}),
        fake_response(200, {"data": {"id": "LOC1", "type": "appInfoLocalizations"}}),
    )
    mgr = AppsManager(asc_client)

    mgr.ensure_app_info_localization("INFO1", "fr-FR", {"subtitle": "Traduction instantanée"})

    update = fake_session.requests[1]
    assert update["method"] == "PATCH"
    assert update["url"].endswith("/v1/appInfoLocalizations/LOC1")
    assert update["json"]["data"]["attributes"] == {"subtitle": "Traduction instantanée"}
    assert "locale" not in update["json"]["data"]["attributes"]
