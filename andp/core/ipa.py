"""Read publishing metadata straight from an .ipa — the binary is the source
of truth for bundle id, version and build number."""
import hashlib
import plistlib
import zipfile


def _read_info_plist(ipa_path):
    with zipfile.ZipFile(ipa_path) as zf:
        for name in zf.namelist():
            if name.startswith("Payload/") and name.endswith(".app/Info.plist"):
                return plistlib.loads(zf.read(name))
    return None


def read_metadata(ipa_path):
    """(bundle_id, version, build) from the IPA's Info.plist; all None if unreadable."""
    try:
        info = _read_info_plist(ipa_path)
        if info is not None:
            return (
                info.get("CFBundleIdentifier"),
                info.get("CFBundleShortVersionString"),
                info.get("CFBundleVersion"),
            )
    except Exception:
        pass
    return None, None, None


def read_export_compliance(ipa_path):
    """The IPA's ITSAppUsesNonExemptEncryption declaration, or None if absent."""
    try:
        info = _read_info_plist(ipa_path)
        if info is not None and "ITSAppUsesNonExemptEncryption" in info:
            return bool(info["ITSAppUsesNonExemptEncryption"])
    except Exception:
        pass
    return None


def _read_extension_plists(ipa_path):
    """[(appex_name, Info.plist dict)] for every embedded app extension."""
    found = []
    with zipfile.ZipFile(ipa_path) as zf:
        for name in zf.namelist():
            if ".appex/Info.plist" not in name or not name.startswith("Payload/"):
                continue
            appex = name.split("/")[-2]
            try:
                found.append((appex, plistlib.loads(zf.read(name))))
            except Exception:
                continue
    return found


# Extension points whose Info.plist must carry NSExtensionAttributes. Apple
# rejects the archive without it — an activation rule is what tells the host
# which content the extension accepts, so an extension point that matches on
# content cannot go without one. Deliberately a allow-list: an extension point
# absent here is left alone rather than guessed at, because a false positive
# would block a release over a rule we invented.
_ATTRIBUTES_REQUIRED = frozenset({
    "com.apple.share-services",
    "com.apple.services",
    "com.apple.ui-services",
})


def validate_bundle(ipa_path):
    """Hard packaging faults readable from the .ipa, as precheck-style findings.

    App Store Connect accepts a malformed package and rejects it later, during
    processing: the upload succeeds, no build ever appears, and only an email
    says why. Catching those faults here turns a silent asynchronous rejection
    into an immediate, named error.

    Returns [] for a package we cannot parse — validation must never be the
    thing that breaks a release.
    """
    try:
        extensions = _read_extension_plists(ipa_path)
    except Exception:
        return []

    findings = []
    for appex, info in extensions:
        ns_extension = info.get("NSExtension")
        if not isinstance(ns_extension, dict):
            continue
        point = ns_extension.get("NSExtensionPointIdentifier")
        attributes = ns_extension.get("NSExtensionAttributes")

        if "NSExtensionActivationRule" in ns_extension:
            findings.append({
                "id": "extension_activation_rule_misplaced",
                "level": "error",
                "message": (
                    f"NSExtensionActivationRule sits directly under NSExtension in bundle "
                    f"{appex}: it belongs inside NSExtensionAttributes. App Store "
                    f"Connect rejects the archive with STATE_ERROR.VALIDATION_ERROR "
                    f"(\"A value for the key 'NSExtensionAttributes' … is required\")."
                ),
            })
        elif point in _ATTRIBUTES_REQUIRED and not isinstance(attributes, dict):
            findings.append({
                "id": "extension_attributes_missing",
                "level": "error",
                "message": (
                    f"Extension point {point} requires NSExtensionAttributes, absent from "
                    f"bundle {appex}. App Store Connect rejects the archive during "
                    f"processing, after reporting the upload as successful."
                ),
            })
    return findings


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
