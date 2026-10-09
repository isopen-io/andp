"""The App Store listing fields ANDP drives — one registry, pure validation.

Every field App Store Connect API 4.5.1 exposes for defining an app and its
submission is declared once here: its API attribute, the config keys that set
it (snake_case and the API camelCase are both accepted), its kind, its limit,
and whether App Review refuses a submission without it. The loader, the plan,
the apply and the readiness checks all read this table — none of them
re-declares a limit.

Reference (meaning, scope, sources): Documentation/AppStoreFields.md.
"""
import datetime
import re

# -- field kinds ---------------------------------------------------------------

TEXT, URL, BOOL, ENUM, DATETIME, LOCALE, CATEGORY = (
    "text", "url", "bool", "enum", "datetime", "locale", "category")


class Field:
    __slots__ = ("api", "keys", "kind", "max_len", "values", "required",
                 "deprecated", "secret")

    def __init__(self, api, kind, keys=(), max_len=None, values=None,
                 required=False, deprecated=None, secret=False):
        self.api = api
        self.kind = kind
        self.keys = tuple(keys) + (api,)
        self.max_len = max_len
        self.values = frozenset(values) if values else None
        self.required = required
        self.deprecated = deprecated
        self.secret = secret


# -- families --------------------------------------------------------------------

# apps/{id} — app-wide attributes.
APP_FIELDS = (
    Field("primaryLocale", LOCALE, ("primary_locale",)),
    Field("contentRightsDeclaration", ENUM, ("content_rights", "content_rights_declaration"),
          values={"DOES_NOT_USE_THIRD_PARTY_CONTENT", "USES_THIRD_PARTY_CONTENT"},
          required=True),
    Field("accessibilityUrl", URL, ("accessibility_url",)),
    Field("subscriptionStatusUrl", URL, ("subscription_status_url",)),
    Field("subscriptionStatusUrlVersion", ENUM, ("subscription_status_url_version",),
          values={"V1", "V2"}),
    Field("subscriptionStatusUrlForSandbox", URL, ("subscription_status_url_sandbox",)),
    Field("subscriptionStatusUrlVersionForSandbox", ENUM,
          ("subscription_status_url_version_sandbox",), values={"V1", "V2"}),
    Field("streamlinedPurchasingEnabled", BOOL, ("streamlined_purchasing",)),
)

# appInfos/{id} relationships — the categories (editable appInfo).
CATEGORY_FIELDS = (
    Field("primaryCategory", CATEGORY, ("primary",), required=True),
    Field("primarySubcategoryOne", CATEGORY, ("primary_subcategory_one",)),
    Field("primarySubcategoryTwo", CATEGORY, ("primary_subcategory_two",)),
    Field("secondaryCategory", CATEGORY, ("secondary",)),
    Field("secondarySubcategoryOne", CATEGORY, ("secondary_subcategory_one",)),
    Field("secondarySubcategoryTwo", CATEGORY, ("secondary_subcategory_two",)),
)

# appInfoLocalizations — per language, app-wide.
APP_INFO_LOCALIZATION_FIELDS = (
    Field("name", TEXT, (), max_len=30, required=True),
    Field("subtitle", TEXT, (), max_len=30),
    Field("privacyPolicyUrl", URL, ("privacy_policy_url", "privacy_url"), required=True),
    Field("privacyChoicesUrl", URL, ("privacy_choices_url",)),
    Field("privacyPolicyText", TEXT, ("privacy_policy_text",)),
)

# appStoreVersions/{id} — per version.
VERSION_FIELDS = (
    Field("copyright", TEXT, (), required=True),
    Field("releaseType", ENUM, ("release_type",),
          values={"MANUAL", "AFTER_APPROVAL", "SCHEDULED"}),
    Field("earliestReleaseDate", DATETIME, ("earliest_release_date",)),
    Field("downloadable", BOOL, ()),
    Field("reviewType", ENUM, ("review_type",), values={"APP_STORE", "NOTARIZATION"}),
    Field("usesIdfa", BOOL, ("uses_idfa",),
          deprecated="deprecated by Apple; advertising identifier use is declared in App Privacy"),
)

# appStoreVersionLocalizations — per version and language.
VERSION_LOCALIZATION_FIELDS = (
    Field("description", TEXT, (), max_len=4000, required=True),
    Field("keywords", TEXT, (), max_len=100),
    Field("whatsNew", TEXT, ("whats_new", "release_notes"), max_len=4000),
    Field("promotionalText", TEXT, ("promotional_text",), max_len=170),
    Field("marketingUrl", URL, ("marketing_url",)),
    Field("supportUrl", URL, ("support_url",), required=True),
)

# appStoreReviewDetails — per version.
REVIEW_FIELDS = (
    Field("contactFirstName", TEXT, ("contact_first_name", "first_name"), required=True),
    Field("contactLastName", TEXT, ("contact_last_name", "last_name"), required=True),
    Field("contactPhone", TEXT, ("contact_phone", "phone_number"), required=True,
          secret=True),
    Field("contactEmail", TEXT, ("contact_email", "email_address"), required=True,
          secret=True),
    Field("demoAccountRequired", BOOL, ("demo_account_required", "demo_required")),
    Field("demoAccountName", TEXT, ("demo_account_name", "demo_user"), secret=True),
    Field("demoAccountPassword", TEXT, ("demo_account_password", "demo_password"),
          secret=True),
    Field("notes", TEXT, (), max_len=4000),
)

# accessibilityDeclarations — per app and device family (Accessibility Nutrition Labels).
ACCESSIBILITY_FIELDS = (
    Field("supportsVoiceover", BOOL, ("voiceover",)),
    Field("supportsVoiceControl", BOOL, ("voice_control",)),
    Field("supportsLargerText", BOOL, ("larger_text",)),
    Field("supportsDarkInterface", BOOL, ("dark_interface",)),
    Field("supportsDifferentiateWithoutColorAlone", BOOL,
          ("differentiate_without_color_alone",)),
    Field("supportsSufficientContrast", BOOL, ("sufficient_contrast",)),
    Field("supportsReducedMotion", BOOL, ("reduced_motion",)),
    Field("supportsCaptions", BOOL, ("captions",)),
    Field("supportsAudioDescriptions", BOOL, ("audio_descriptions",)),
)
DEVICE_FAMILIES = frozenset({"IPHONE", "IPAD", "APPLE_TV", "APPLE_WATCH", "MAC", "VISION"})

# appEncryptionDeclarations — per app (export compliance, non-exempt encryption).
ENCRYPTION_FIELDS = (
    Field("appDescription", TEXT, ("app_description",), required=True),
    Field("containsProprietaryCryptography", BOOL,
          ("contains_proprietary_cryptography",), required=True),
    Field("containsThirdPartyCryptography", BOOL,
          ("contains_third_party_cryptography",), required=True),
    Field("availableOnFrenchStore", BOOL, ("available_on_french_store",), required=True),
)

# Top-level iOS categories (GET /v1/appCategories?filter[platforms]=IOS, 2026-10-09).
# Only GAMES and STICKERS have subcategories, all prefixed by their parent.
KNOWN_CATEGORIES = frozenset({
    "BOOKS", "BUSINESS", "DEVELOPER_TOOLS", "EDUCATION", "ENTERTAINMENT", "FINANCE",
    "FOOD_AND_DRINK", "GAMES", "GRAPHICS_AND_DESIGN", "HEALTH_AND_FITNESS",
    "LIFESTYLE", "MAGAZINES_AND_NEWSPAPERS", "MEDICAL", "MUSIC", "NAVIGATION",
    "NEWS", "PHOTO_AND_VIDEO", "PRODUCTIVITY", "REFERENCE", "SHOPPING",
    "SOCIAL_NETWORKING", "SPORTS", "STICKERS", "TRAVEL", "UTILITIES", "WEATHER",
})
CATEGORIES_WITH_SUBCATEGORIES = frozenset({"GAMES", "STICKERS"})

_LOCALE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,4})?$")


# -- pure helpers --------------------------------------------------------------

def is_http_url(value):
    if not isinstance(value, str):
        return False
    text = value.strip()
    return (text.startswith(("https://", "http://")) and " " not in text
            and len(text) > len("https://"))


def normalize_text(value):
    """The form ASC stores and compares: CRLF folded, outer whitespace dropped."""
    if value is None:
        return None
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def _parse_datetime(value):
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def coerce(field, value):
    """Return (value, error). Pure. `None` passes through (field not managed)."""
    if value is None:
        return None, None
    kind = field.kind
    if kind == BOOL:
        if isinstance(value, bool):
            return value, None
        token = str(value).strip().lower()
        if token in ("true", "yes", "1"):
            return True, None
        if token in ("false", "no", "0"):
            return False, None
        return None, f"{field.api}: expected a boolean, got {value!r}"
    text = normalize_text(value)
    if kind == URL and not is_http_url(text):
        return None, f"{field.api}: expected an http(s) URL, got {value!r}"
    if kind == ENUM and text not in field.values:
        return None, (f"{field.api}: {text!r} is not one of "
                      f"{', '.join(sorted(field.values))}")
    if kind == LOCALE and not _LOCALE.match(text):
        return None, f"{field.api}: {text!r} is not an App Store locale code"
    if kind == DATETIME:
        if _parse_datetime(text) is None:
            return None, (f"{field.api}: {value!r} is not an ISO 8601 date-time "
                          "with a time zone (e.g. 2026-11-02T08:00:00Z)")
        return text, None
    if kind == CATEGORY:
        return text.upper(), None
    if field.max_len is not None and len(text) > field.max_len:
        return None, (f"{field.api}: {len(text)} characters, the App Store "
                      f"allows {field.max_len}")
    return text, None


def pick(fields, source, where=""):
    """Read `fields` out of a config mapping. Returns (attributes, errors, warnings).

    A field may be set by any of its keys; two keys with different values is an
    error (ambiguous), an unknown key is an error (typo guard)."""
    attributes, errors, warnings = {}, [], []
    known = {}
    for field in fields:
        for key in field.keys:
            known[key] = field
    prefix = f"{where}: " if where else ""
    for key, raw in (source or {}).items():
        field = known.get(key)
        if field is None:
            errors.append(f"{prefix}unknown field {key!r}")
            continue
        value, error = coerce(field, raw)
        if error:
            errors.append(prefix + error)
            continue
        if value is None:
            continue
        if field.api in attributes and attributes[field.api] != value:
            errors.append(f"{prefix}{field.api} is set twice with different values")
            continue
        if field.deprecated:
            warnings.append(f"{prefix}{field.api}: {field.deprecated}")
        attributes[field.api] = value
    return attributes, errors, warnings


def category_warnings(categories):
    """Advisory checks on a {api_field: category_id} map. Pure."""
    warnings = []
    for api, value in sorted(categories.items()):
        if value is None:
            continue
        if "Subcategory" in api:
            parent = categories.get(api.replace("SubcategoryOne", "Category")
                                    .replace("SubcategoryTwo", "Category"))
            if parent not in CATEGORIES_WITH_SUBCATEGORIES or not value.startswith(f"{parent}_"):
                warnings.append(f"{api}: {value!r} is not a subcategory of {parent!r} "
                                "(only GAMES and STICKERS have subcategories)")
        elif value not in KNOWN_CATEGORIES:
            warnings.append(f"{api}: unknown category {value!r} (checked live by the plan)")
    return warnings


def version_rules(attributes, now=None):
    """Cross-field rules on version attributes. Returns errors. Pure."""
    errors = []
    release_type = attributes.get("releaseType")
    date = attributes.get("earliestReleaseDate")
    if release_type == "SCHEDULED" and not date:
        errors.append("earliestReleaseDate is required when releaseType is SCHEDULED")
    if date and release_type not in (None, "SCHEDULED"):
        errors.append("earliestReleaseDate only applies to releaseType SCHEDULED")
    if date:
        parsed = _parse_datetime(date)
        moment = now or datetime.datetime.now(datetime.timezone.utc)
        if parsed is not None and parsed <= moment:
            errors.append(f"earliestReleaseDate {date} is in the past")
    return errors


def review_rules(attributes):
    """Cross-field rules on review details. Returns errors. Pure."""
    errors = []
    if attributes.get("demoAccountRequired") is True:
        for name in ("demoAccountName", "demoAccountPassword"):
            if not attributes.get(name):
                errors.append(f"{name} is required when demoAccountRequired is true")
    email = attributes.get("contactEmail")
    if email and "@" not in email:
        errors.append("contactEmail is not an e-mail address")
    return errors
