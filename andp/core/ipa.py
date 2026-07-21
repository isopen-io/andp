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


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
