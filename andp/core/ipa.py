"""Read publishing metadata straight from an .ipa — the binary is the source
of truth for bundle id, version and build number."""
import hashlib
import plistlib
import zipfile


def read_metadata(ipa_path):
    """(bundle_id, version, build) from the IPA's Info.plist; all None if unreadable."""
    try:
        with zipfile.ZipFile(ipa_path) as zf:
            for name in zf.namelist():
                if name.startswith("Payload/") and name.endswith(".app/Info.plist"):
                    info = plistlib.loads(zf.read(name))
                    return (
                        info.get("CFBundleIdentifier"),
                        info.get("CFBundleShortVersionString"),
                        info.get("CFBundleVersion"),
                    )
    except Exception:
        pass
    return None, None, None


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
