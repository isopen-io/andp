"""Folder-convention publisher for App Store metadata and assets.

Layout (deliver-style):
    <root>/<locale>/whatsNew.txt | description.txt | keywords.txt |
                    promotionalText.txt | supportUrl.txt | marketingUrl.txt
    (or deliver's release_notes.txt, promotional_text.txt, support_url.txt,
    marketing_url.txt — the same fields; app-info files such as name.txt are
    `andp store apply`'s)
    <root>/<locale>/screenshots/<GROUP>/*.png|jpg|jpeg
    <root>/<locale>/previews/<GROUP>/*.mp4|mov|m4v
    <root>/<locale>/imessage_screenshots/<GROUP>/*
    <root>/<locale>/product_page_header/*   <root>/<locale>/search_results/*

GROUP is an App Asset Library placement group or display class (IPHONE_DUO,
IPAD_13_PROFILE…) or a legacy type (APP_IPHONE_67…) — see media_spec. Visuals
go through the App Asset Library (upload once, place per locale, in name
order); without it, the legacy screenshot/preview sets take the groups they can
express. Every file is checked against Apple's specifications before anything
is written. Idempotency is per FILE: a file already placed is skipped.
"""
import os

from .asc.appstore import (
    EDITABLE_VERSION_STATES, IN_REVIEW_VERSION_STATES, version_state,
)
from .errors import AndpError
from .asc.asset_refdata import REF_DATA
from .listing_source import version_localization_files
from .media_spec import read_media_tree
from .media_sync import apply_media, locale_summary, plan_media


def _is_locale_dir(name):
    # Skip hidden / tooling dirs (.git, __MACOSX, .DS_Store folders, …).
    return not (name.startswith(".") or name.startswith("__"))


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


def _read_tree(root_dir):
    """(texts per locale, media tree) — every problem raised BEFORE any write."""
    texts, errors = {}, []
    for locale in sorted(os.listdir(root_dir)):
        locale_dir = os.path.join(root_dir, locale)
        if not os.path.isdir(locale_dir) or not _is_locale_dir(locale):
            continue
        attributes, problems = version_localization_files(locale_dir)
        texts[locale] = attributes
        errors.extend(problems)
    media, media_errors = read_media_tree(root_dir, REF_DATA)
    errors.extend(media_errors)
    if errors:
        raise AndpError(code="invalid_metadata", message="; ".join(errors), retryable=False,
                        remediation="Fix the texts or the media files listed — nothing "
                                    "was written.")
    return texts, media


def publish_metadata(managers, app_id, version_string, root_dir, version_id=None):
    """Push every locale's texts, screenshots, previews and creative assets.

    Idempotent per file: re-running only sends what is missing. Pass
    version_id to skip re-resolving the version (the machine pins it).
    Returns {version_id, media_backend, locales: {locale: {...}}}.
    """
    if not os.path.isdir(root_dir):
        raise FileNotFoundError(f"Metadata directory not found: {root_dir}")
    texts, media = _read_tree(root_dir)

    version_id = _resolve_version(managers, app_id, version_string, version_id)

    summary = {"version_id": version_id, "locales": {}}
    localizations = {}
    for locale, attributes in texts.items():
        if not attributes and locale not in media:
            continue  # nothing to push for this locale — don't create a phantom localization
        localization, created = managers.appstore.upsert_version_localization(
            version_id, locale, attributes)
        localizations[locale] = localization["id"]
        summary["locales"][locale] = {"metadata": "created" if created else "updated"}

    plan = plan_media(managers, app_id, version_id, media, localizations=localizations)
    if plan["errors"]:
        raise AndpError(code="media_unsupported", message="; ".join(plan["errors"]),
                        retryable=False,
                        remediation="Use a display group the legacy sets support, or "
                                    "publish once the App Asset Library is available.")
    apply_media(managers, plan)
    summary["media_backend"] = plan["backend"]
    for locale in summary["locales"]:
        summary["locales"][locale].update(locale_summary(plan, locale))
    return summary
