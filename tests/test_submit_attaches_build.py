"""submit must attach a VALID build to the version before submitting.

Apple rejects a review submission whose appStoreVersion has no build attached.
The old submit did ensure_version -> submit_for_review with no attach_build in
between — a review submission doomed to fail. Regression test for that.
"""
from andp.asc import asc_manager
from conftest import FakeResponse


def _configured(tmp_path, monkeypatch, ec_private_key_pem):
    from conftest import real_secrets_yaml
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)


def test_submit_attaches_latest_valid_build_before_submitting(
    tmp_path, monkeypatch, ec_private_key_pem, capsys
):
    _configured(tmp_path, monkeypatch, ec_private_key_pem)

    session = None
    original = asc_manager.make_managers

    def patched(account):
        nonlocal session
        managers = original(account)
        session = managers.client.session
        return managers

    monkeypatch.setattr(asc_manager, "make_managers", patched)

    # We inject a recording FakeSession by pre-seeding the responses through
    # the client the managers build. Easiest: swap the session after build.
    from conftest import FakeSession
    injected = FakeSession()

    def patched2(account):
        managers = original(account)
        managers.client.session = injected
        return managers

    monkeypatch.setattr(asc_manager, "make_managers", patched2)

    injected.queue(
        # find_app
        FakeResponse(200, {"data": [{"id": "app-1", "type": "apps"}]}),
        # ensure_version: GET existing -> found
        FakeResponse(200, {"data": [{"id": "ver-1", "type": "appStoreVersions",
                                     "attributes": {"versionString": "1.0",
                                                    "appStoreState": "PREPARE_FOR_SUBMISSION"}}]}),
        # latest_valid_build
        FakeResponse(200, {"data": [{"id": "build-9", "type": "builds",
                                     "attributes": {"processingState": "VALID"}}]}),
        # attach_build (PATCH relationships/build -> 204)
        FakeResponse(204, None, content=b""),
        # submit_for_review: POST reviewSubmissions
        FakeResponse(201, {"data": {"id": "sub-1", "type": "reviewSubmissions",
                                    "attributes": {"state": "READY_FOR_REVIEW"}}}),
        # POST reviewSubmissionItems
        FakeResponse(201, {"data": {"id": "item-1", "type": "reviewSubmissionItems"}}),
        # PATCH reviewSubmissions submitted=true
        FakeResponse(200, {"data": {"id": "sub-1", "type": "reviewSubmissions",
                                    "attributes": {"state": "WAITING_FOR_REVIEW"}}}),
    )

    exit_code = asc_manager.main(["submit", "me.demo.app", "1.0"])

    assert exit_code == 0
    # The build must have been attached: a PATCH to the version's build relationship.
    attach_calls = [
        r for r in injected.requests
        if r["method"] == "PATCH" and "appStoreVersions/ver-1/relationships/build" in r["url"]
    ]
    assert len(attach_calls) == 1, "submit did not attach a build before submitting"
    assert attach_calls[0]["json"]["data"] == {"type": "builds", "id": "build-9"}


def test_submit_fails_clearly_when_no_valid_build(
    tmp_path, monkeypatch, ec_private_key_pem, capsys
):
    _configured(tmp_path, monkeypatch, ec_private_key_pem)
    from conftest import FakeSession
    injected = FakeSession()
    original = asc_manager.make_managers

    def patched(account):
        managers = original(account)
        managers.client.session = injected
        return managers

    monkeypatch.setattr(asc_manager, "make_managers", patched)

    injected.queue(
        FakeResponse(200, {"data": [{"id": "app-1", "type": "apps"}]}),
        FakeResponse(200, {"data": [{"id": "ver-1", "type": "appStoreVersions",
                                     "attributes": {"versionString": "1.0",
                                                    "appStoreState": "PREPARE_FOR_SUBMISSION"}}]}),
        # latest_valid_build: none VALID yet
        FakeResponse(200, {"data": []}),
    )

    exit_code = asc_manager.main(["submit", "me.demo.app", "1.0"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "build" in out.lower()
