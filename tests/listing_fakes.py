"""In-memory App Store Connect stand-ins for the listing plan/apply tests.

The HTTP contract of each resource is pinned in test_listing_manager.py; these
fakes only hold state so the orchestration (read → diff → write) is testable
without replaying dozens of canned responses in order. Every write is recorded.
"""
import copy


class FakeListing:
    def __init__(self, state, writes):
        self.s, self.writes = state, writes

    def app(self, app_id):
        return {"id": app_id, "attributes": copy.deepcopy(self.s["app"])}

    def update_app(self, app_id, attrs):
        self.writes.append(("update_app", attrs))
        self.s["app"].update(attrs)

    def editable_app_info(self, app_id):
        info = self.s["app_info"]
        return {"id": info["id"], "attributes": {"state": info["state"]}}, info["editable"]

    def categories(self, info_id):
        return dict(self.s["categories"])

    def update_categories(self, info_id, cats):
        self.writes.append(("update_categories", cats))
        self.s["categories"].update(cats)

    def app_info_localizations(self, info_id):
        return {loc: {"id": f"ail-{loc}", "attributes": dict(a, locale=loc)}
                for loc, a in self.s["app_info_localizations"].items()}

    def create_app_info_localization(self, info_id, locale, attrs):
        self.writes.append(("create_app_info_localization", locale, attrs))
        self.s["app_info_localizations"][locale] = dict(attrs)

    def update_app_info_localization(self, loc_id, attrs):
        self.writes.append(("update_app_info_localization", loc_id, attrs))
        self.s["app_info_localizations"][loc_id[len("ail-"):]].update(attrs)

    def territory_age_ratings(self, info_id):
        return dict(self.s.get("territory_age_ratings", {}))

    def update_version(self, version_id, attrs):
        self.writes.append(("update_version", attrs))
        self.s["version"]["attributes"].update(attrs)

    def phased_release(self, version_id):
        return copy.deepcopy(self.s.get("phased"))

    def create_phased_release(self, version_id):
        self.writes.append(("create_phased_release",))
        self.s["phased"] = {"id": "pr", "attributes": {"phasedReleaseState": "INACTIVE"}}

    def delete_phased_release(self, pr_id):
        self.writes.append(("delete_phased_release", pr_id))
        self.s["phased"] = None

    def review_detail(self, version_id):
        return copy.deepcopy(self.s.get("review"))

    def save_review_detail(self, version_id, rid, attrs):
        self.writes.append(("save_review_detail", rid, attrs))
        if rid is None:
            self.s["review"] = {"id": "rd", "attributes": dict(attrs)}
        else:
            self.s["review"]["attributes"].update(attrs)
        return {"id": "rd"}

    def review_attachment_names(self, rid):
        return set(self.s.get("attachments", set()))

    def upload_review_attachment(self, rid, path):
        self.writes.append(("upload_review_attachment", rid, path))

    def accessibility_declarations(self, app_id):
        return copy.deepcopy(self.s.get("accessibility", []))

    def declare_accessibility(self, app_id, family, draft_id, attrs):
        self.writes.append(("declare_accessibility", family, draft_id, attrs))

    def encryption_declarations(self, app_id):
        return copy.deepcopy(self.s.get("encryption", []))

    def create_encryption_declaration(self, app_id, attrs):
        self.writes.append(("create_encryption_declaration", attrs))
        return {"id": "enc-new"}

    def upload_encryption_document(self, decl_id, path):
        self.writes.append(("upload_encryption_document", decl_id, path))

    def eula(self, app_id):
        return copy.deepcopy(self.s.get("eula"))

    def save_eula(self, app_id, eula_id, text, territories):
        self.writes.append(("save_eula", eula_id, text, sorted(territories)))

    def delete_eula(self, eula_id):
        self.writes.append(("delete_eula", eula_id))


class FakeAppStore:
    def __init__(self, state, writes):
        self.s, self.writes = state, writes

    def find_version(self, app_id, version, platform="IOS"):
        v = self.s.get("version")
        return copy.deepcopy(v) if v and v["attributes"]["versionString"] == version else None

    def list_versions(self, app_id, platform=None):
        v = self.s.get("version")
        return [copy.deepcopy(v)] if v else []

    def list_version_localizations(self, version_id):
        return [{"id": f"vl-{loc}", "attributes": dict(a, locale=loc)}
                for loc, a in self.s["version_localizations"].items()]

    def upsert_version_localization(self, version_id, locale, attrs):
        self.writes.append(("upsert_version_localization", locale, attrs))
        self.s["version_localizations"].setdefault(locale, {}).update(attrs)
        return {"id": f"vl-{locale}"}, False


class FakeAgeRating:
    def __init__(self, state, writes):
        self.s, self.writes = state, writes

    def get_declaration(self, app_id):
        d = self.s.get("age_rating")
        return {"id": "ard", "attributes": dict(d)} if d is not None else None

    def update_declaration(self, decl_id, attrs):
        self.writes.append(("update_age_rating", attrs))
        self.s["age_rating"].update(attrs)


class FakeAvailability:
    def __init__(self, state):
        self.s = state

    def list_all_territories(self):
        return set(self.s.get("all_territories", {"FRA", "USA", "DEU"}))

    def availability_snapshot(self, app_id):
        return copy.deepcopy(self.s.get("availability"))


class FakePricing:
    def __init__(self, state):
        self.s = state

    def current_base_price_point_id(self, app_id, territory):
        return self.s.get("price_point")

    def find_free_price_point(self, app_id, territory):
        return {"id": "pp-free"}

    def find_price_point(self, app_id, territory, price):
        return {"id": f"pp-{price}"}


class FakeManagers:
    def __init__(self, state):
        self.writes = []
        self.listing = FakeListing(state, self.writes)
        self.appstore = FakeAppStore(state, self.writes)
        self.age_rating = FakeAgeRating(state, self.writes)
        self.availability = FakeAvailability(state)
        self.pricing = FakePricing(state)


def live_state(**overrides):
    state = {
        "app": {"contentRightsDeclaration": "DOES_NOT_USE_THIRD_PARTY_CONTENT",
                "primaryLocale": "fr-FR", "accessibilityUrl": None},
        "app_info": {"id": "ai", "state": "PREPARE_FOR_SUBMISSION", "editable": True},
        "categories": {"primaryCategory": "SOCIAL_NETWORKING", "secondaryCategory": None},
        "app_info_localizations": {"fr-FR": {"name": "Acme", "subtitle": "Chat",
                                             "privacyPolicyUrl": "https://acme.io/privacy"}},
        "version": {"id": "v1", "attributes": {
            "versionString": "1.2.0", "appVersionState": "PREPARE_FOR_SUBMISSION",
            "copyright": "2025 Acme", "releaseType": "MANUAL",
            "earliestReleaseDate": None, "downloadable": True}},
        "version_localizations": {"fr-FR": {"description": "Une app.", "keywords": "chat",
                                            "supportUrl": "https://acme.io/help",
                                            "whatsNew": "Corrections."}},
        "review": {"id": "rd", "attributes": {
            "contactFirstName": "Ada", "contactLastName": "L", "contactPhone": "+33100000000",
            "contactEmail": "ada@acme.io", "demoAccountRequired": True,
            "demoAccountName": "rev", "demoAccountPassword": "old", "notes": "Hi"}},
        "attachments": set(),
        "phased": None,
        "age_rating": {"messagingAndChat": True, "socialMedia": None},
        "territory_age_ratings": {"THIRTEEN_PLUS": 174},
        "accessibility": [],
        "encryption": [],
        "eula": None,
        "availability": {"territories": {"FRA", "USA", "DEU"},
                         "available_in_new_territories": True},
        "price_point": "pp-free",
    }
    state.update(overrides)
    return state


class FakeApps:
    def __init__(self, found=True):
        self.found = found

    def find_app(self, bundle_id):
        return {"id": "APP", "attributes": {"bundleId": bundle_id}} if self.found else None


def fake_managers_with_app(state, found=True):
    managers = FakeManagers(state)
    managers.apps = FakeApps(found)
    return managers


class FakeAssetLibrary:
    """Asset Library state: library assets and placements per localization id."""

    def __init__(self, state, writes):
        self.s, self.writes = state, writes
        self._next = 0

    def library_id(self, app_id):
        if self.s.get("library_unavailable"):
            from andp.asc.client import ASCAPIError
            raise ASCAPIError(404, [{"detail": "The resource does not exist"}])
        return "LIB"

    def ref_data(self):
        from andp.asc.asset_refdata import REF_DATA
        return REF_DATA

    def assets(self, library_id, media_type):
        return [dict(a) for a in self.s.setdefault("library", []) if a["mediaType"] == media_type]

    def placements(self, loc_id):
        return [dict(p) for p in self.s.setdefault("placements", {}).get(loc_id, [])]

    def upload(self, library_id, path, category):
        import os
        self._next += 1
        media_type = "VIDEO" if path.endswith((".mp4", ".mov", ".m4v")) else "IMAGE"
        asset = {"id": f"new{self._next}", "fileName": os.path.basename(path),
                 "fileSize": os.path.getsize(path), "state": "UPLOAD_COMPLETE",
                 "mediaType": media_type}
        self.s.setdefault("library", []).append(asset)
        self.writes.append(("upload", os.path.basename(path), category))
        return dict(asset)

    def place(self, loc_id, placement_type, group, media_type, media_id):
        self._next += 1
        name = next(a["fileName"] for a in self.s["library"] if a["id"] == media_id)
        size = next(a["fileSize"] for a in self.s["library"] if a["id"] == media_id)
        placement = {"id": f"pl{self._next}", "placementType": placement_type,
                     "placementGroup": group, "state": "ASSET_PROCESSING",
                     "mediaType": media_type, "mediaId": media_id, "fileName": name,
                     "fileSize": size}
        self.s.setdefault("placements", {}).setdefault(loc_id, []).append(placement)
        self.writes.append(("place", loc_id, placement_type, group, name))
        return {"id": placement["id"]}

    def unplace(self, placement_id):
        for loc, items in self.s.get("placements", {}).items():
            self.s["placements"][loc] = [p for p in items if p["id"] != placement_id]
        self.writes.append(("unplace", placement_id))

    def order(self, loc_id, group, ids):
        items = self.s["placements"][loc_id]
        others = [p for p in items if p["placementGroup"] != group]
        by_id = {p["id"]: p for p in items}
        self.s["placements"][loc_id] = others + [by_id[i] for i in ids]
        self.writes.append(("order", loc_id, group, [by_id[i]["fileName"] for i in ids]))


class FakeLegacySets:
    """appScreenshotSets / appPreviewSets for the fallback path."""

    def __init__(self, state, writes, kind):
        self.s, self.writes, self.kind = state, writes, kind

    def _sets(self):
        return self.s.setdefault("legacy", {})

    def ensure_screenshot_set(self, loc_id, display_type):
        self._sets().setdefault((loc_id, display_type), [])
        return {"id": f"{loc_id}|{display_type}"}

    ensure_preview_set = ensure_screenshot_set

    def existing_filenames(self, set_id):
        loc_id, display_type = set_id.split("|")
        return set(self._sets().get((loc_id, display_type), []))

    def upload_screenshot_to_set(self, set_id, path):
        import os
        loc_id, display_type = set_id.split("|")
        self._sets()[(loc_id, display_type)].append(os.path.basename(path))
        self.writes.append(("legacy_upload", display_type, os.path.basename(path)))

    upload_preview_to_set = upload_screenshot_to_set


def media_managers(state):
    managers = FakeManagers(state)
    managers.apps = FakeApps(True)
    managers.asset_library = FakeAssetLibrary(state, managers.writes)
    managers.screenshots = FakeLegacySets(state, managers.writes, "screenshots")
    managers.previews = FakeLegacySets(state, managers.writes, "previews")
    return managers
