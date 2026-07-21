"""Folder-convention publisher for App Store metadata and assets.

Layout (deliver-style):
    <root>/<locale>/whatsNew.txt | description.txt | keywords.txt |
                    promotionalText.txt | supportUrl.txt | marketingUrl.txt
    <root>/<locale>/screenshots/<DISPLAY_TYPE>/*.png|jpg|jpeg
    <root>/<locale>/previews/<DISPLAY_TYPE>/*.mp4|mov|m4v

DISPLAY_TYPE is Apple's raw screenshot/preview type, e.g. APP_IPHONE_67,
APP_IPAD_PRO_3GEN_129. Screenshot/preview sets that already contain assets are
skipped (idempotent re-run) rather than duplicated.
"""
import os

# file name (without .txt) -> appStoreVersionLocalization attribute
_TEXT_FIELDS = {
    "whatsNew": "whatsNew",
    "description": "description",
    "keywords": "keywords",
    "promotionalText": "promotionalText",
    "supportUrl": "supportUrl",
    "marketingUrl": "marketingUrl",
}
_IMAGE_EXT = (".png", ".jpg", ".jpeg")
_VIDEO_EXT = (".mp4", ".mov", ".m4v")


def _read_text_fields(locale_dir):
    attributes = {}
    for stem, attr in _TEXT_FIELDS.items():
        path = os.path.join(locale_dir, f"{stem}.txt")
        if os.path.isfile(path):
            with open(path, "r") as f:
                attributes[attr] = f.read().strip()
    return attributes


def _asset_dirs(parent, extensions):
    """Yield (display_type, [file_paths]) for each display-type subdir."""
    if not os.path.isdir(parent):
        return
    for display_type in sorted(os.listdir(parent)):
        d = os.path.join(parent, display_type)
        if not os.path.isdir(d):
            continue
        files = sorted(
            os.path.join(d, f) for f in os.listdir(d)
            if os.path.splitext(f)[1].lower() in extensions
        )
        if files:
            yield display_type, files


def publish_metadata(managers, app_id, version_string, root_dir):
    """Push every locale's notes, screenshots and previews to the version.

    Returns a summary dict {version_id, locales: {locale: {...}}}.
    """
    if not os.path.isdir(root_dir):
        raise FileNotFoundError(f"Metadata directory not found: {root_dir}")

    version = managers.appstore.ensure_version(app_id, version_string)
    version_id = version["id"]

    summary = {"version_id": version_id, "locales": {}}
    for locale in sorted(os.listdir(root_dir)):
        locale_dir = os.path.join(root_dir, locale)
        if not os.path.isdir(locale_dir):
            continue

        attributes = _read_text_fields(locale_dir)
        localization, created = managers.appstore.upsert_version_localization(
            version_id, locale, attributes
        )
        loc_id = localization["id"]
        loc_summary = {"metadata": "created" if created else "updated",
                       "screenshots": 0, "previews": 0}

        for display_type, files in _asset_dirs(
                os.path.join(locale_dir, "screenshots"), _IMAGE_EXT):
            sset = managers.screenshots.ensure_screenshot_set(loc_id, display_type)
            if managers.screenshots.count_screenshots(sset["id"]) > 0:
                continue  # already populated — skip to stay idempotent
            for path in files:
                managers.screenshots.upload_screenshot_to_set(sset["id"], path)
                loc_summary["screenshots"] += 1

        for display_type, files in _asset_dirs(
                os.path.join(locale_dir, "previews"), _VIDEO_EXT):
            pset = managers.previews.ensure_preview_set(loc_id, display_type)
            if managers.previews.count_previews(pset["id"]) > 0:
                continue
            for path in files:
                managers.previews.upload_preview_to_set(pset["id"], path)
                loc_summary["previews"] += 1

        summary["locales"][locale] = loc_summary
    return summary
