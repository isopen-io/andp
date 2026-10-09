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
