"""Folder-convention publisher for App Store metadata and assets.

Layout (deliver-style):
    <root>/<locale>/whatsNew.txt | description.txt | keywords.txt |
                    promotionalText.txt | supportUrl.txt | marketingUrl.txt
    <root>/<locale>/screenshots/<DISPLAY_TYPE>/*.png|jpg|jpeg
    <root>/<locale>/previews/<DISPLAY_TYPE>/*.mp4|mov|m4v

DISPLAY_TYPE is Apple's raw screenshot/preview type, e.g. APP_IPHONE_67,
APP_IPAD_PRO_3GEN_129. Idempotency is per-FILE: a media file whose fileName is
already in the set is skipped, so a retry uploads exactly the missing files.
"""
import os

from .asc.appstore import (
    EDITABLE_VERSION_STATES, IN_REVIEW_VERSION_STATES, version_state,
)
from .core.errors import AndpError

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


def _is_locale_dir(name):
    # Skip hidden / tooling dirs (.git, __MACOSX, .DS_Store folders, …).
    return not (name.startswith(".") or name.startswith("__"))


def _read_text_fields(locale_dir):
    attributes = {}
    for stem, attr in _TEXT_FIELDS.items():
        path = os.path.join(locale_dir, f"{stem}.txt")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:  # an empty file must NOT overwrite the field with ""
                attributes[attr] = content
    return attributes


def _asset_dirs(parent, extensions):
    """Yield (display_type, [file_paths]) for each display-type subdir."""
    if not os.path.isdir(parent):
        return
    for display_type in sorted(os.listdir(parent)):
        d = os.path.join(parent, display_type)
        if not os.path.isdir(d) or not _is_locale_dir(display_type):
            continue
        files = sorted(
            os.path.join(d, f) for f in os.listdir(d)
            if os.path.splitext(f)[1].lower() in extensions
        )
        if files:
            yield display_type, files


def _resolve_version(managers, app_id, version_string, version_id):
    if version_id is not None:
        return version_id  # pinned by the machine; already editability-checked
    version = managers.appstore.ensure_version(app_id, version_string)
    state = version_state(version)
    if state in IN_REVIEW_VERSION_STATES or (
            state is not None and state not in EDITABLE_VERSION_STATES):
        raise AndpError(
            code="version_not_editable",
            message=f"Version {version_string} is in state {state!r}; cannot edit metadata.",
            retryable=False,
            remediation="Bump the marketing version, or wait until it is editable.",
        )
    return version["id"]


def publish_metadata(managers, app_id, version_string, root_dir, version_id=None):
    """Push every locale's notes, screenshots and previews to the version.

    Idempotent per file: re-running only uploads what is missing. Pass
    version_id to skip re-resolving the version (the machine pins it).
    Returns {version_id, locales: {locale: {...}}}.
    """
    if not os.path.isdir(root_dir):
        raise FileNotFoundError(f"Metadata directory not found: {root_dir}")

    version_id = _resolve_version(managers, app_id, version_string, version_id)

    summary = {"version_id": version_id, "locales": {}}
    for locale in sorted(os.listdir(root_dir)):
        locale_dir = os.path.join(root_dir, locale)
        if not os.path.isdir(locale_dir) or not _is_locale_dir(locale):
            continue

        attributes = _read_text_fields(locale_dir)
        has_assets = any(True for _ in _asset_dirs(
            os.path.join(locale_dir, "screenshots"), _IMAGE_EXT)) or any(
            True for _ in _asset_dirs(os.path.join(locale_dir, "previews"), _VIDEO_EXT))
        if not attributes and not has_assets:
            continue  # nothing to push for this locale — don't create a phantom localization
        localization, created = managers.appstore.upsert_version_localization(
            version_id, locale, attributes
        )
        loc_id = localization["id"]
        loc_summary = {"metadata": "created" if created else "updated",
                       "screenshots": 0, "screenshots_skipped": 0,
                       "previews": 0, "previews_skipped": 0}

        _push_assets(
            managers.screenshots, loc_id, os.path.join(locale_dir, "screenshots"),
            _IMAGE_EXT, loc_summary, "screenshots",
            managers.screenshots.ensure_screenshot_set,
            managers.screenshots.upload_screenshot_to_set)
        _push_assets(
            managers.previews, loc_id, os.path.join(locale_dir, "previews"),
            _VIDEO_EXT, loc_summary, "previews",
            managers.previews.ensure_preview_set,
            managers.previews.upload_preview_to_set)

        summary["locales"][locale] = loc_summary
    return summary


def _push_assets(manager, loc_id, parent, extensions, loc_summary, key,
                 ensure_set, upload_to_set):
    for display_type, files in _asset_dirs(parent, extensions):
        asset_set = ensure_set(loc_id, display_type)
        existing = manager.existing_filenames(asset_set["id"])
        for path in files:
            if os.path.basename(path) in existing:
                loc_summary[f"{key}_skipped"] += 1
                continue
            upload_to_set(asset_set["id"], path)
            loc_summary[key] += 1
