"""Tests for infrastructure/asc/client.py — client HTTP App Store Connect (JSON:API)."""
import pytest

from andp.asc.client import ASCAPIError, ASCClient

BASE = "https://api.appstoreconnect.apple.com"


class StubAuth:
    def __init__(self, value="stub-jwt"):
        self.value = value

    def token(self):
        return self.value


def make_client(fake_session, sleeps=None):
    return ASCClient(
        auth=StubAuth(),
        session=fake_session,
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
    )


def test_get_sends_bearer_token_and_returns_json(fake_session, fake_response):
    fake_session.queue(fake_response(200, {"data": {"id": "42", "type": "apps"}}))
    client = make_client(fake_session)

    result = client.get("/v1/apps/42")

    request = fake_session.requests[0]
    assert request["method"] == "GET"
    assert request["url"] == f"{BASE}/v1/apps/42"
    assert request["headers"]["Authorization"] == "Bearer stub-jwt"
    assert result["data"]["id"] == "42"


def test_get_passes_query_params(fake_session, fake_response):
    fake_session.queue(fake_response(200, {"data": []}))
    client = make_client(fake_session)

    client.get("/v1/apps", params={"filter[bundleId]": "me.meeshy.app"})

    assert fake_session.requests[0]["params"] == {"filter[bundleId]": "me.meeshy.app"}


def test_api_error_is_raised_with_details(fake_session, fake_response):
    fake_session.queue(
        fake_response(
            409,
            {
                "errors": [
                    {
                        "status": "409",
                        "code": "ENTITY_ERROR.ATTRIBUTE.INVALID",
                        "title": "Attribute error",
                        "detail": "Version already exists",
                    }
                ]
            },
        )
    )
    client = make_client(fake_session)

    with pytest.raises(ASCAPIError) as exc_info:
        client.get("/v1/appStoreVersions")

    assert exc_info.value.status == 409
    assert "Version already exists" in str(exc_info.value)


def test_post_sends_json_api_payload(fake_session, fake_response):
    fake_session.queue(fake_response(201, {"data": {"id": "new", "type": "betaGroups"}}))
    client = make_client(fake_session)

    payload = {"data": {"type": "betaGroups", "attributes": {"name": "Beta"}}}
    result = client.post("/v1/betaGroups", payload)

    request = fake_session.requests[0]
    assert request["method"] == "POST"
    assert request["json"] == payload
    assert request["headers"]["Content-Type"] == "application/json"
    assert result["data"]["id"] == "new"


def test_patch_and_delete(fake_session, fake_response):
    fake_session.queue(
        fake_response(200, {"data": {"id": "1", "type": "builds"}}),
        fake_response(204),
    )
    client = make_client(fake_session)

    client.patch("/v1/builds/1", {"data": {}})
    assert client.delete("/v1/betaTesters/9") is None

    assert fake_session.requests[0]["method"] == "PATCH"
    assert fake_session.requests[1]["method"] == "DELETE"


def test_get_all_follows_pagination_links(fake_session, fake_response):
    fake_session.queue(
        fake_response(
            200,
            {
                "data": [{"id": "1", "type": "betaTesters"}],
                "links": {"next": f"{BASE}/v1/betaTesters?cursor=abc"},
            },
        ),
        fake_response(200, {"data": [{"id": "2", "type": "betaTesters"}], "links": {}}),
    )
    client = make_client(fake_session)

    items = client.get_all("/v1/betaTesters")

    assert [item["id"] for item in items] == ["1", "2"]
    assert fake_session.requests[1]["url"] == f"{BASE}/v1/betaTesters?cursor=abc"


def test_rate_limit_429_retries_after_delay(fake_session, fake_response):
    sleeps = []
    fake_session.queue(
        fake_response(429, {"errors": [{"status": "429", "title": "Rate limited"}]},
                      headers={"Retry-After": "7"}),
        fake_response(200, {"data": []}),
    )
    client = make_client(fake_session, sleeps=sleeps)

    result = client.get("/v1/apps")

    assert result == {"data": []}
    assert sleeps == [7.0]


def test_rate_limit_gives_up_after_max_retries(fake_session, fake_response):
    sleeps = []
    fake_session.queue(*[
        fake_response(429, {"errors": [{"status": "429", "title": "Rate limited"}]})
        for _ in range(5)
    ])
    client = make_client(fake_session, sleeps=sleeps)

    with pytest.raises(ASCAPIError) as exc_info:
        client.get("/v1/apps")

    assert exc_info.value.status == 429
    assert len(sleeps) == 3  # 3 retries puis abandon


def test_mutations_are_audit_logged_when_enabled(
    asc_client, fake_session, fake_response, tmp_path, monkeypatch
):
    """Every write to the API (POST/PATCH/DELETE) leaves a JSONL audit trail
    when ANDP_AUDIT_LOG is set — agent actions must be traceable. GETs are not logged."""
    import json as jsonlib

    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("ANDP_AUDIT_LOG", str(audit_path))

    fake_session.queue(
        fake_response(200, {"data": []}),
        fake_response(201, {"data": {"id": "X1", "type": "profiles"}}),
    )
    asc_client.get("/v1/apps")
    asc_client.post("/v1/profiles", {"data": {"type": "profiles"}})

    lines = [jsonlib.loads(l) for l in audit_path.read_text().splitlines()]
    assert len(lines) == 1
    entry = lines[0]
    assert entry["method"] == "POST"
    assert entry["path"].endswith("/v1/profiles")
    assert entry["status"] == 201
    assert "ts" in entry


def test_no_audit_log_by_default(asc_client, fake_session, fake_response, tmp_path, monkeypatch):
    monkeypatch.delenv("ANDP_AUDIT_LOG", raising=False)
    monkeypatch.chdir(tmp_path)
    fake_session.queue(fake_response(201, {"data": {"id": "X1", "type": "profiles"}}))
    asc_client.post("/v1/profiles", {"data": {"type": "profiles"}})
    assert list(tmp_path.iterdir()) == []
