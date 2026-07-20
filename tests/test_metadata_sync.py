"""Tests for infrastructure/asc/metadata_manager.py — synchronisation des métadonnées."""
import json

import pytest

from andp.asc.appstore import AppStoreManager
from andp.asc.apps import AppsManager
from andp.asc.metadata_manager import MetadataSyncer


@pytest.fixture
def metadata_file(tmp_path):
    payload = {
        "bundle_id": "me.meeshy.app",
        "version": "1.2.0",
        "localizations": {
            "fr-FR": {"description": "Meeshy traduit vos conversations.",
                      "whatsNew": "Traduction hors-ligne."},
            "en-US": {"description": "Meeshy translates your conversations.",
                      "whatsNew": "Offline translation."},
        },
    }
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(payload))
    return str(path)


def test_sync_pushes_every_locale(asc_client, fake_session, fake_response, metadata_file):
    fake_session.queue(
        # find_app
        fake_response(200, {"data": [{"id": "APP1", "type": "apps"}]}),
        # ensure_version : existe déjà
        fake_response(200, {"data": [{"id": "V1", "type": "appStoreVersions"}]}),
        # fr-FR : localisation existante → PATCH
        fake_response(200, {"data": [{"id": "VLFR", "type": "appStoreVersionLocalizations",
                                      "attributes": {"locale": "fr-FR"}}]}),
        fake_response(200, {"data": {"id": "VLFR", "type": "appStoreVersionLocalizations"}}),
        # en-US : absente → POST
        fake_response(200, {"data": []}),
        fake_response(201, {"data": {"id": "VLEN", "type": "appStoreVersionLocalizations"}}),
    )
    syncer = MetadataSyncer(AppsManager(asc_client), AppStoreManager(asc_client))

    result = syncer.sync_from_file(metadata_file)

    assert result == {"fr-FR": "updated", "en-US": "created"}
    patch_fr = fake_session.requests[3]
    assert patch_fr["method"] == "PATCH"
    assert patch_fr["json"]["data"]["attributes"]["whatsNew"] == "Traduction hors-ligne."
    post_en = fake_session.requests[5]
    assert post_en["method"] == "POST"
    assert post_en["json"]["data"]["attributes"]["locale"] == "en-US"


def test_sync_fails_when_app_missing(asc_client, fake_session, fake_response, metadata_file):
    fake_session.queue(fake_response(200, {"data": []}))
    syncer = MetadataSyncer(AppsManager(asc_client), AppStoreManager(asc_client))

    with pytest.raises(LookupError, match="me.meeshy.app"):
        syncer.sync_from_file(metadata_file)


def test_sync_fails_on_missing_file(asc_client):
    syncer = MetadataSyncer(AppsManager(asc_client), AppStoreManager(asc_client))
    with pytest.raises(FileNotFoundError):
        syncer.sync_from_file("nonexistent.json")
