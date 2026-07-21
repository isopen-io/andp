"""Service layer for --ship: policy-driven allow_submit/compliance + approve."""
import plistlib
import zipfile

import pytest

from andp import service
from conftest import FakeResponse, FakeSession, make_test_managers


def _make_ipa(directory, encryption=False):
    info = {
        "CFBundleIdentifier": "me.demo.app",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
    }
    if encryption is not None:
        info["ITSAppUsesNonExemptEncryption"] = encryption
    path = directory / "App.ipa"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Payload/App.app/Info.plist", plistlib.dumps(info))
    return str(path)


@pytest.fixture
def real(tmp_path, monkeypatch, ec_private_key_pem):
    from conftest import real_secrets_yaml
    (tmp_path / "secrets.yml").write_text(real_secrets_yaml(ec_private_key_pem))
    monkeypatch.chdir(tmp_path)
    session = FakeSession()
    monkeypatch.setattr(service, "make_managers", lambda a: make_test_managers(session))
    return tmp_path, session


def test_start_ship_reads_allow_submit_and_compliance_from_policy(real):
    tmp_path, session = real
    (tmp_path / "andp.yml").write_text(
        "policy:\n  allow_submit: true\ncompliance:\n  uses_non_exempt_encryption: false\n"
    )
    ipa = _make_ipa(tmp_path)
    result = service.release_start(ipa, ship=True)
    assert result["ok"] is True
    rid = result["release_id"]
    snap = service.release_status(rid)
    assert snap["state"] == "created"
    # the machine state carries the policy-derived flags
    from andp.core.state import StateStore
    raw = StateStore(str(tmp_path / ".andp" / "state")).load(rid)
    assert raw["want_ship"] is True
    assert raw["allow_submit"] is True
    assert raw["uses_non_exempt_encryption"] is False


def test_start_ship_dry_run_plan_includes_appstore_stages(tmp_path, monkeypatch):
    (tmp_path / "secrets.example.yml").write_text(
        'accounts:\n  primary:\n    asc_api:\n      key_id: "ABCDE12345"\n'
        '      issuer_id: "x"\n      key_content: "REPLACE_WITH"\n'
    )
    monkeypatch.chdir(tmp_path)
    ipa = _make_ipa(tmp_path)
    result = service.release_start(ipa, ship=True, group="Beta")
    assert result["dry_run"] is True
    assert result["plan"] == ["app_record", "upload", "processing",
                              "testflight_group", "version", "build_attached",
                              "compliance", "submit"]


def test_approve_opens_the_gate(real):
    tmp_path, session = real
    ipa = _make_ipa(tmp_path)
    rid = service.release_start(ipa, ship=True)["release_id"]
    result = service.release_approve(rid)
    assert result["ok"] is True
    from andp.core.state import StateStore
    raw = StateStore(str(tmp_path / ".andp" / "state")).load(rid)
    assert raw["approved"] is True


def test_approve_unknown_release_reports_not_found(real):
    result = service.release_approve("nope")
    assert result["ok"] is False
    assert result["error"]["code"] == "not_found"
