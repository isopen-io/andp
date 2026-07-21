"""Age rating declaration via the App Store Connect API (2025 overhaul).

The declaration is app-global, reachable from appInfo. An app has more than one
appInfo (live + editable); patching the live one 409s, so reads/writes target
the EDITABLE appInfo. The field taxonomy matches deliver's app_rating_config
keys plus the 2025 additions, kept in one place so it is trivial to extend.
"""

# appInfo states in which the declaration is editable (mirrors the version model).
EDITABLE_APP_INFO_STATES = frozenset({
    "PREPARE_FOR_SUBMISSION", "READY_FOR_REVIEW", "DEVELOPER_REJECTED",
    "REJECTED", "METADATA_REJECTED", "INVALID_BINARY", "WAITING_FOR_REVIEW",
})

# Ternary content descriptors: NONE | INFREQUENT_OR_MILD | FREQUENT_OR_INTENSE.
TERNARY_FIELDS = frozenset({
    "alcoholTobaccoOrDrugUseOrReferences", "contests", "gamblingSimulated",
    "gunsOrOtherWeapons", "horrorOrFearThemes", "matureOrSuggestiveThemes",
    "medicalOrTreatmentInformation", "profanityOrCrudeHumor",
    "sexualContentGraphicAndNudity", "sexualContentOrNudity",
    "violenceCartoonOrFantasy", "violenceRealistic",
    "violenceRealisticProlongedGraphicOrSadistic",
})
TERNARY_VALUES = frozenset({"NONE", "INFREQUENT_OR_MILD", "FREQUENT_OR_INTENSE"})

# Boolean fields (incl. 2025 interactivity additions).
BOOLEAN_FIELDS = frozenset({
    "gambling", "unrestrictedWebAccess", "seventeenPlus", "lootBox",
    "advertising", "ageAssurance", "healthOrWellnessTopics", "messagingAndChat",
    "parentalControls", "userGeneratedContent",
})

# Enum fields with their own allowed sets (None also allowed to clear).
ENUM_FIELDS = {
    "kidsAgeBand": frozenset({"FIVE_AND_UNDER", "SIX_TO_EIGHT", "NINE_TO_ELEVEN"}),
    "ageRatingOverride": frozenset({"NONE", "SEVENTEEN_PLUS", "UNRATED"}),
    "koreaAgeRatingOverride": frozenset({"NONE", "FIFTEEN_PLUS", "NINETEEN_PLUS"}),
}

_TRUE = {"true", "1", "yes"}
_FALSE = {"false", "0", "no"}


def _as_bool(value):
    if isinstance(value, bool):
        return value, True
    if isinstance(value, str):
        low = value.strip().lower()
        if low in _TRUE:
            return True, True
        if low in _FALSE:
            return False, True
    if isinstance(value, int):
        return bool(value), True
    return None, False


def validate_declaration(config):
    """Pure: (attributes, errors, warnings). No I/O — usable in dry-run.

    Unknown keys are errors (typo guard); unknown enum VALUES on a known key
    pass through with a warning so a value Apple adds later still works."""
    attributes, errors, warnings = {}, [], []
    for key, value in (config or {}).items():
        if key == "config_path":
            continue  # resolved by the caller, not a declaration attribute
        if key in TERNARY_FIELDS:
            if value not in TERNARY_VALUES:
                warnings.append(f"{key}: unrecognised value {value!r} (passing through)")
            attributes[key] = value
        elif key in ENUM_FIELDS:
            if value is not None and value not in ENUM_FIELDS[key]:
                warnings.append(f"{key}: unrecognised value {value!r} (passing through)")
            attributes[key] = value
        elif key in BOOLEAN_FIELDS:
            coerced, ok = _as_bool(value)
            if not ok:
                errors.append(f"{key}: expected a boolean, got {value!r}")
            else:
                attributes[key] = coerced
        else:
            errors.append(f"unknown age rating field {key!r}")
    return attributes, errors, warnings


class AgeRatingManager:
    def __init__(self, client):
        self.client = client

    def validate(self, config):
        return validate_declaration(config)

    def get_declaration(self, app_id):
        """The editable appInfo's ageRatingDeclaration {id, attributes}, or None."""
        app_infos = self.client.get_all(f"/v1/apps/{app_id}/appInfos")
        if not app_infos:
            return None
        editable = next(
            (ai for ai in app_infos
             if ai.get("attributes", {}).get("state") in EDITABLE_APP_INFO_STATES),
            app_infos[0],
        )
        return (self.client.get(
            f"/v1/appInfos/{editable['id']}/ageRatingDeclaration") or {}).get("data")

    def update_declaration(self, declaration_id, attributes):
        payload = {
            "data": {
                "type": "ageRatingDeclarations",
                "id": declaration_id,
                "attributes": attributes,
            }
        }
        return (self.client.patch(
            f"/v1/ageRatingDeclarations/{declaration_id}", payload) or {}).get("data")
