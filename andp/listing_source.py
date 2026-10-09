"""The desired App Store listing, read from andp.yml and a metadata tree.

Two sources, one result. The metadata tree follows fastlane `deliver`'s layout
(`copyright.txt`, `primary_category.txt`, `<locale>/name.txt`,
`<locale>/release_notes.txt`, `review_information/…`) and ANDP's camelCase
names (`<locale>/whatsNew.txt`, `supportUrl.txt`, …); `andp.yml` (`store:`)
overrides it field by field. Nothing here talks to Apple.

Secrets never live in either source: any key may be suffixed `_env` to name an
environment variable (or a line of `store.env_file`, a gitignored KEY=VALUE
file), and `_file` to read a text file relative to the project.
"""
import os
import re

from . import listing_spec as spec

KNOWN_SECTIONS = frozenset({
    "platform", "metadata_dir", "env_file", "pricing", "availability", "age_rating",
    "app", "categories", "localizations", "version", "review", "accessibility",
    "encryption", "eula",
})

_ROOT_FILES = {
    "copyright": ("version", "copyright"),
    "primary_category": ("categories", "primary"),
    "secondary_category": ("categories", "secondary"),
    "primary_first_sub_category": ("categories", "primary_subcategory_one"),
    "primary_second_sub_category": ("categories", "primary_subcategory_two"),
    "secondary_first_sub_category": ("categories", "secondary_subcategory_one"),
    "secondary_second_sub_category": ("categories", "secondary_subcategory_two"),
}
_LOCALE_FILES = {
    "name": "name", "subtitle": "subtitle",
    "privacy_url": "privacy_url", "privacyPolicyUrl": "privacyPolicyUrl",
    "privacy_choices_url": "privacy_choices_url", "privacyChoicesUrl": "privacyChoicesUrl",
    "apple_tv_privacy_policy": "privacy_policy_text", "privacyPolicyText": "privacyPolicyText",
    "description": "description", "keywords": "keywords",
    "release_notes": "release_notes", "whatsNew": "whatsNew",
    "promotional_text": "promotional_text", "promotionalText": "promotionalText",
    "support_url": "support_url", "supportUrl": "supportUrl",
    "marketing_url": "marketing_url", "marketingUrl": "marketingUrl",
}
_REVIEW_FILES = ("first_name", "last_name", "phone_number", "email_address",
                 "demo_user", "demo_password", "notes", "demo_required")
_LOCALE_DIR = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,4})?$")
_LOCALIZATION_FIELDS = spec.APP_INFO_LOCALIZATION_FIELDS + spec.VERSION_LOCALIZATION_FIELDS
_APP_INFO_APIS = {f.api for f in spec.APP_INFO_LOCALIZATION_FIELDS}


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_dotenv(path):
    values = {}
    for line in _read(path).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _non_empty_text(path):
    if not os.path.isfile(path):
        return None
    text = spec.normalize_text(_read(path))
    return text or None


def _resolve_refs(mapping, where, project_root, env, errors):
    """Expand `<key>_env` and `<key>_file` references into plain keys."""
    resolved = {}
    for key, value in (mapping or {}).items():
        if isinstance(key, str) and key.endswith("_env"):
            name = str(value)
            if name not in env:
                errors.append(f"{where}: environment variable {name} is not set")
                continue
            resolved[key[:-len("_env")]] = env[name]
        elif isinstance(key, str) and key.endswith("_file") and key != "file":
            path = _project_path(project_root, value)
            if not os.path.isfile(path):
                errors.append(f"{where}: {key} {value!r} does not exist")
                continue
            resolved[key[:-len("_file")]] = _read(path)
        else:
            resolved[key] = value
    return resolved


def _project_path(project_root, value):
    value = str(value)
    return value if os.path.isabs(value) else os.path.join(project_root, value)


# -- metadata tree --------------------------------------------------------------

def _tree(metadata_dir):
    """Raw config-shaped mappings read from the tree (values still unvalidated)."""
    tree = {"version": {}, "categories": {}, "review": {}, "localizations": {}}
    for stem, (section, key) in _ROOT_FILES.items():
        text = _non_empty_text(os.path.join(metadata_dir, f"{stem}.txt"))
        if text is not None:
            tree[section][key] = text
    review_dir = os.path.join(metadata_dir, "review_information")
    for stem in _REVIEW_FILES:
        text = _non_empty_text(os.path.join(review_dir, f"{stem}.txt"))
        if text is not None:
            tree["review"][stem] = text
    default = {}
    for entry in sorted(os.listdir(metadata_dir)):
        folder = os.path.join(metadata_dir, entry)
        if not os.path.isdir(folder):
            continue
        if entry != "default" and not _LOCALE_DIR.match(entry):
            continue
        values = read_locale_files(folder)
        if entry == "default":
            default = values
        elif values:
            tree["localizations"][entry] = values
    if default:
        tree["localizations"] = {
            locale: _with_defaults(default, values)
            for locale, values in tree["localizations"].items()}
    return tree


def read_locale_files(folder):
    """Raw {config key: text} of one locale folder (deliver and andp names)."""
    values = {}
    for stem, key in _LOCALE_FILES.items():
        text = _non_empty_text(os.path.join(folder, f"{stem}.txt"))
        if text is not None:
            values[key] = text
    return values


def version_localization_files(folder):
    """(attributes, errors) of the version-localization fields of one locale
    folder — the app-info files (name, subtitle, privacy URLs) are left out."""
    keys = {k for f in spec.VERSION_LOCALIZATION_FIELDS for k in f.keys}
    raw = {k: v for k, v in read_locale_files(folder).items() if k in keys}
    attrs, errors, _ = spec.pick(spec.VERSION_LOCALIZATION_FIELDS, raw,
                                 where=os.path.basename(folder))
    return attrs, errors


def _with_defaults(default, values):
    """Default-folder values for the fields this locale does not set (any key)."""
    known = {}
    for field in _LOCALIZATION_FIELDS:
        for key in field.keys:
            known[key] = field.api
    present = {known.get(k) for k in values}
    merged = {k: v for k, v in default.items() if known.get(k) not in present}
    merged.update(values)
    return merged


# -- assembly ------------------------------------------------------------------------

def _pick_into(fields, mapping, where, errors, warnings):
    attrs, errs, warns = spec.pick(fields, mapping, where=where)
    errors.extend(errs)
    warnings.extend(warns)
    return attrs


def _localizations(raw, where, errors, warnings):
    info, version = {}, {}
    for locale, mapping in sorted((raw or {}).items()):
        attrs = _pick_into(_LOCALIZATION_FIELDS, mapping, locale if not where
                           else f"{where}.{locale}", errors, warnings)
        app_info = {k: v for k, v in attrs.items() if k in _APP_INFO_APIS}
        version_loc = {k: v for k, v in attrs.items() if k not in _APP_INFO_APIS}
        if app_info:
            info[locale] = app_info
        if version_loc:
            version[locale] = version_loc
    return info, version


def _merge_locales(base, override):
    merged = {locale: dict(values) for locale, values in base.items()}
    for locale, values in override.items():
        merged.setdefault(locale, {}).update(values)
    return merged


def _accessibility(raw, errors, warnings):
    declared = {}
    for family, mapping in (raw or {}).items():
        name = str(family).upper()
        if name not in spec.DEVICE_FAMILIES:
            errors.append(f"store.accessibility: unknown device family {family!r} "
                          f"(one of {', '.join(sorted(spec.DEVICE_FAMILIES))})")
            continue
        declared[name] = _pick_into(spec.ACCESSIBILITY_FIELDS, mapping,
                                    f"store.accessibility.{name}", errors, warnings)
    return declared


def _encryption(raw, project_root, errors, warnings):
    if not raw:
        return None, None
    mapping = dict(raw)
    document = mapping.pop("document", None)
    attrs = _pick_into(spec.ENCRYPTION_FIELDS, mapping, "store.encryption", errors, warnings)
    for field in spec.ENCRYPTION_FIELDS:
        if field.required and field.api not in attrs:
            errors.append(f"store.encryption: {field.api} is required")
    path = None
    if document:
        path = _project_path(project_root, document)
        if not os.path.isfile(path):
            errors.append(f"store.encryption: document {document!r} does not exist")
    return attrs, path


def _eula(raw, project_root, errors):
    if raw is None:
        return None
    if raw == "standard":
        return {"standard": True}
    if not isinstance(raw, dict) or "file" not in raw:
        errors.append("store.eula: expected 'standard' or {file: <path>, territories: all|[…]}")
        return None
    path = _project_path(project_root, raw["file"])
    if not os.path.isfile(path):
        errors.append(f"store.eula: file {raw['file']!r} does not exist")
        return None
    territories = raw.get("territories", "all")
    if territories != "all":
        territories = sorted(str(t).strip().upper() for t in territories)
    return {"text": spec.normalize_text(_read(path)), "territories": territories}


def load_desired(store, project_root=".", metadata_dir=None, environ=None):
    """Pure-ish (reads local files only): the desired listing + its findings."""
    store = store or {}
    errors, warnings = [], []
    for section in store:
        if section not in KNOWN_SECTIONS:
            errors.append(f"store: unknown section {section!r}")

    env = dict(os.environ if environ is None else environ)
    if store.get("env_file"):
        env_path = _project_path(project_root, store["env_file"])
        if os.path.isfile(env_path):
            env = {**_read_dotenv(env_path), **env}
        else:
            warnings.append(f"store.env_file {store['env_file']!r} does not exist")

    tree = {"version": {}, "categories": {}, "review": {}, "localizations": {}}
    metadata_dir = metadata_dir or store.get("metadata_dir")
    if metadata_dir:
        full = _project_path(project_root, metadata_dir)
        if os.path.isdir(full):
            tree = _tree(full)
        else:
            errors.append(f"metadata directory {metadata_dir!r} does not exist")

    def section(name):
        return _resolve_refs(store.get(name) or {}, f"store.{name}", project_root, env, errors)

    app = _pick_into(spec.APP_FIELDS, section("app"), "store.app", errors, warnings)
    categories = {
        **_pick_into(spec.CATEGORY_FIELDS, tree["categories"], "categories files",
                     errors, warnings),
        **_pick_into(spec.CATEGORY_FIELDS, section("categories"), "store.categories",
                     errors, warnings),
    }
    warnings.extend(spec.category_warnings(categories))

    version_cfg = section("version")
    phased = version_cfg.pop("phased_release", None)
    version = {
        **_pick_into(spec.VERSION_FIELDS, tree["version"], "copyright.txt", errors, warnings),
        **_pick_into(spec.VERSION_FIELDS, version_cfg, "store.version", errors, warnings),
    }
    errors.extend(spec.version_rules(version))
    phased_release = None
    if phased is not None:
        value, error = spec.coerce(spec.Field("phased_release", spec.BOOL), phased)
        if error:
            errors.append(f"store.version: {error}")
        phased_release = value

    review_cfg = section("review")
    attachments = [_project_path(project_root, p) for p in review_cfg.pop("attachments", []) or []]
    for path in attachments:
        if not os.path.isfile(path):
            errors.append(f"store.review: attachment {path!r} does not exist")
    review = {
        **_pick_into(spec.REVIEW_FIELDS, tree["review"], "review_information", errors, warnings),
        **_pick_into(spec.REVIEW_FIELDS, review_cfg, "store.review", errors, warnings),
    }
    errors.extend(spec.review_rules(review))

    tree_info, tree_version = _localizations(tree["localizations"], "", errors, warnings)
    yml_raw = {loc: _resolve_refs(m, f"store.localizations.{loc}", project_root, env, errors)
               for loc, m in (store.get("localizations") or {}).items()}
    yml_info, yml_version = _localizations(yml_raw, "store.localizations", errors, warnings)

    encryption, encryption_document = _encryption(
        section("encryption"), project_root, errors, warnings)

    return {
        "platform": str(store.get("platform") or "IOS").upper(),
        "app": app,
        "categories": categories,
        "app_info_localizations": _merge_locales(tree_info, yml_info),
        "version": version,
        "phased_release": phased_release,
        "version_localizations": _merge_locales(tree_version, yml_version),
        "review": review,
        "review_attachments": attachments,
        "accessibility": _accessibility(store.get("accessibility"), errors, warnings),
        "encryption": encryption,
        "encryption_document": encryption_document,
        "eula": _eula(store.get("eula"), project_root, errors),
        "errors": errors,
        "warnings": warnings,
    }
