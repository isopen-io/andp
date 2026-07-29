"""Bundle validation read straight from the .ipa, before the upload.

App Store Connect accepts a malformed package, then rejects it *asynchronously*
during processing: the upload reports success, no build ever appears, and the
only notice is an email. A real delivery burned three hours that way on

    Missing Info.plist value. A value for the key 'NSExtensionAttributes' in
    bundle Meeshy.app/PlugIns/MeeshyShareExtension.appex is required.

These checks turn that silent asynchronous rejection into an immediate, named
error — in pure Python, without shelling out to altool.
"""
import plistlib
import zipfile

import pytest

from andp.core.ipa import validate_bundle
from andp.core.release import ReleaseMachine
from andp.core.state import StateStore
from andp.errors import AndpError
from conftest import FakeSession, make_test_managers

SHARE = "com.apple.share-services"

_ACTIVATION_RULE = {
    "NSExtensionActivationSupportsText": True,
    "NSExtensionActivationSupportsWebURLWithMaxCount": 1,
}


def _ipa(directory, name="App.ipa", extensions=()):
    """An .ipa carrying `extensions` as (appex_name, NSExtension dict)."""
    path = directory / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Payload/App.app/Info.plist", plistlib.dumps({
            "CFBundleIdentifier": "me.demo.app",
            "CFBundleShortVersionString": "1.0",
            "CFBundleVersion": "1",
        }))
        for appex_name, ns_extension in extensions:
            zf.writestr(
                f"Payload/App.app/PlugIns/{appex_name}.appex/Info.plist",
                plistlib.dumps({
                    "CFBundleIdentifier": f"me.demo.app.{appex_name}",
                    "NSExtension": ns_extension,
                }),
            )
    return str(path)


def _ids(findings):
    return [f["id"] for f in findings]


def test_share_extension_with_the_rule_under_attributes_is_accepted(tmp_path):
    ipa = _ipa(tmp_path, extensions=[("Share", {
        "NSExtensionPointIdentifier": SHARE,
        "NSExtensionPrincipalClass": "ShareViewController",
        "NSExtensionAttributes": {"NSExtensionActivationRule": _ACTIVATION_RULE},
    })])
    assert validate_bundle(ipa) == []


def test_activation_rule_directly_under_nsextension_is_rejected(tmp_path):
    # The exact shape Apple refused. The rule belongs one level deeper.
    ipa = _ipa(tmp_path, extensions=[("Share", {
        "NSExtensionPointIdentifier": SHARE,
        "NSExtensionPrincipalClass": "ShareViewController",
        "NSExtensionActivationRule": _ACTIVATION_RULE,
    })])
    findings = validate_bundle(ipa)
    assert _ids(findings) == ["extension_activation_rule_misplaced"]
    message = findings[0]["message"]
    assert "Share.appex" in message
    assert "NSExtensionAttributes" in message
    assert findings[0]["level"] == "error"


def test_share_extension_without_attributes_at_all_is_rejected(tmp_path):
    ipa = _ipa(tmp_path, extensions=[("Share", {
        "NSExtensionPointIdentifier": SHARE,
        "NSExtensionPrincipalClass": "ShareViewController",
    })])
    findings = validate_bundle(ipa)
    assert _ids(findings) == ["extension_attributes_missing"]
    assert "Share.appex" in findings[0]["message"]


def test_extension_points_that_do_not_require_attributes_are_left_alone(tmp_path):
    # A notification-service extension legitimately ships without
    # NSExtensionAttributes — flagging it would be a false positive.
    ipa = _ipa(tmp_path, extensions=[("NSE", {
        "NSExtensionPointIdentifier": "com.apple.usernotifications.service",
        "NSExtensionPrincipalClass": "NotificationService",
    })])
    assert validate_bundle(ipa) == []


def test_every_faulty_extension_is_reported_not_just_the_first(tmp_path):
    ipa = _ipa(tmp_path, extensions=[
        ("Share", {"NSExtensionPointIdentifier": SHARE,
                   "NSExtensionActivationRule": _ACTIVATION_RULE}),
        ("Action", {"NSExtensionPointIdentifier": "com.apple.services",
                    "NSExtensionActivationRule": _ACTIVATION_RULE}),
    ])
    findings = validate_bundle(ipa)
    assert _ids(findings) == [
        "extension_activation_rule_misplaced",
        "extension_activation_rule_misplaced",
    ]
    assert {"Share.appex", "Action.appex"} == {
        f["message"].split("bundle ")[1].split(" ")[0].rstrip(":") for f in findings
    }


def test_an_ipa_without_extensions_is_accepted(tmp_path):
    assert validate_bundle(_ipa(tmp_path)) == []


def test_an_unreadable_ipa_reports_nothing_rather_than_raising(tmp_path):
    # Validation must never be the thing that breaks a release: an IPA we cannot
    # parse is Apple's problem to adjudicate, not a reason to abort locally.
    broken = tmp_path / "broken.ipa"
    broken.write_bytes(b"not a zip")
    assert validate_bundle(str(broken)) == []


# -- the release refuses to upload a package Apple will drop ---------------

def test_start_refuses_a_bundle_apple_would_reject(tmp_path):
    # No HTTP is queued: the release must die before it touches the network,
    # because uploading is precisely what wastes the hours.
    ipa = _ipa(tmp_path, extensions=[("Share", {
        "NSExtensionPointIdentifier": SHARE,
        "NSExtensionActivationRule": _ACTIVATION_RULE,
    })])
    store = StateStore(str(tmp_path / "state"))

    with pytest.raises(AndpError) as excinfo:
        ReleaseMachine.start(store, make_test_managers(FakeSession()), ipa)

    error = excinfo.value
    assert error.code == "bundle_invalid"
    assert not error.retryable
    assert "Share.appex" in error.message
    assert error.remediation


def test_start_accepts_a_well_formed_bundle(tmp_path):
    ipa = _ipa(tmp_path, extensions=[("Share", {
        "NSExtensionPointIdentifier": SHARE,
        "NSExtensionAttributes": {"NSExtensionActivationRule": _ACTIVATION_RULE},
    })])
    store = StateStore(str(tmp_path / "state"))

    machine = ReleaseMachine.start(store, make_test_managers(FakeSession()), ipa)

    assert machine.state == "created"
