"""App Store listing resources via the App Store Connect API (4.5.1).

The records that define an app and its submission, beyond the version
localizations AppStoreManager already drives: app attributes, the editable
appInfo (categories, localizations, territory age ratings), version attributes,
App Review details and attachments, phased release, accessibility declarations,
export-compliance declarations and the custom licence agreement.
"""
import os

from .agerating import EDITABLE_APP_INFO_STATES
from .assets import _default_upload_transport, _transfer_bytes

CATEGORY_RELATIONSHIPS = (
    "primaryCategory", "primarySubcategoryOne", "primarySubcategoryTwo",
    "secondaryCategory", "secondarySubcategoryOne", "secondarySubcategoryTwo",
)


def _rel(type_, id_):
    return {"data": {"type": type_, "id": id_}}


def _data(response):
    return (response or {}).get("data")


class ListingManager:
    def __init__(self, client, upload_transport=None):
        self.client = client
        self.upload_transport = upload_transport or _default_upload_transport

    # -- app -------------------------------------------------------------------

    def app(self, app_id):
        return _data(self.client.get(f"/v1/apps/{app_id}"))

    def update_app(self, app_id, attributes):
        return _data(self.client.patch(f"/v1/apps/{app_id}", {
            "data": {"type": "apps", "id": app_id, "attributes": attributes}}))

    # -- appInfo -----------------------------------------------------------------

    def editable_app_info(self, app_id):
        """(appInfo, editable). The live appInfo 409s on writes: prefer the
        editable one, else return the first with editable=False."""
        infos = self.client.get_all(f"/v1/apps/{app_id}/appInfos")
        if not infos:
            return None, False
        for info in infos:
            if (info.get("attributes") or {}).get("state") in EDITABLE_APP_INFO_STATES:
                return info, True
        return infos[0], False

    def categories(self, app_info_id):
        response = self.client.get(f"/v1/appInfos/{app_info_id}",
                                   params={"include": ",".join(CATEGORY_RELATIONSHIPS)})
        rels = (_data(response) or {}).get("relationships") or {}
        return {name: ((rels.get(name) or {}).get("data") or {}).get("id")
                for name in CATEGORY_RELATIONSHIPS}

    def update_categories(self, app_info_id, categories):
        relationships = {
            name: (_rel("appCategories", value) if value else {"data": None})
            for name, value in categories.items()}
        return _data(self.client.patch(f"/v1/appInfos/{app_info_id}", {
            "data": {"type": "appInfos", "id": app_info_id,
                     "relationships": relationships}}))

    def app_info_localizations(self, app_info_id):
        """{locale: {id, attributes}}."""
        items = self.client.get_all(f"/v1/appInfos/{app_info_id}/appInfoLocalizations")
        return {(i.get("attributes") or {}).get("locale"): i for i in items}

    def create_app_info_localization(self, app_info_id, locale, attributes):
        return _data(self.client.post("/v1/appInfoLocalizations", {
            "data": {"type": "appInfoLocalizations",
                     "attributes": {"locale": locale, **attributes},
                     "relationships": {"appInfo": _rel("appInfos", app_info_id)}}}))

    def update_app_info_localization(self, localization_id, attributes):
        return _data(self.client.patch(f"/v1/appInfoLocalizations/{localization_id}", {
            "data": {"type": "appInfoLocalizations", "id": localization_id,
                     "attributes": attributes}}))

    def territory_age_ratings(self, app_info_id):
        """{appStoreAgeRating: territory count} — computed by Apple, read-only."""
        summary = {}
        for item in self.client.get_all(f"/v1/appInfos/{app_info_id}/territoryAgeRatings",
                                        params={"limit": 200}):
            rating = (item.get("attributes") or {}).get("appStoreAgeRating")
            summary[rating] = summary.get(rating, 0) + 1
        return summary

    # -- version -------------------------------------------------------------------

    def update_version(self, version_id, attributes):
        return _data(self.client.patch(f"/v1/appStoreVersions/{version_id}", {
            "data": {"type": "appStoreVersions", "id": version_id,
                     "attributes": attributes}}))

    def phased_release(self, version_id):
        return _data(self.client.get(
            f"/v1/appStoreVersions/{version_id}/appStoreVersionPhasedRelease"))

    def create_phased_release(self, version_id):
        return _data(self.client.post("/v1/appStoreVersionPhasedReleases", {
            "data": {"type": "appStoreVersionPhasedReleases",
                     "attributes": {"phasedReleaseState": "INACTIVE"},
                     "relationships": {
                         "appStoreVersion": _rel("appStoreVersions", version_id)}}}))

    def delete_phased_release(self, phased_release_id):
        self.client.delete(f"/v1/appStoreVersionPhasedReleases/{phased_release_id}")

    # -- App Review --------------------------------------------------------------------

    def review_detail(self, version_id):
        return _data(self.client.get(f"/v1/appStoreVersions/{version_id}/appStoreReviewDetail"))

    def save_review_detail(self, version_id, review_detail_id, attributes):
        if review_detail_id is None:
            return _data(self.client.post("/v1/appStoreReviewDetails", {
                "data": {"type": "appStoreReviewDetails", "attributes": attributes,
                         "relationships": {
                             "appStoreVersion": _rel("appStoreVersions", version_id)}}}))
        return _data(self.client.patch(f"/v1/appStoreReviewDetails/{review_detail_id}", {
            "data": {"type": "appStoreReviewDetails", "id": review_detail_id,
                     "attributes": attributes}}))

    def review_attachment_names(self, review_detail_id):
        items = self.client.get_all(
            f"/v1/appStoreReviewDetails/{review_detail_id}/appStoreReviewAttachments")
        return {(i.get("attributes") or {}).get("fileName") for i in items}

    def upload_review_attachment(self, review_detail_id, path):
        return self._upload("appStoreReviewAttachments", "appStoreReviewDetail",
                            "appStoreReviewDetails", review_detail_id, path)

    # -- accessibility (Accessibility Nutrition Labels) ---------------------------------

    def accessibility_declarations(self, app_id):
        return self.client.get_all(f"/v1/apps/{app_id}/accessibilityDeclarations")

    def declare_accessibility(self, app_id, device_family, draft_id, attributes):
        """Create (then publish) or update-and-publish a DRAFT declaration."""
        if draft_id is None:
            created = _data(self.client.post("/v1/accessibilityDeclarations", {
                "data": {"type": "accessibilityDeclarations",
                         "attributes": {"deviceFamily": device_family, **attributes},
                         "relationships": {"app": _rel("apps", app_id)}}}))
            return self._patch_accessibility(created["id"], {"publish": True})
        return self._patch_accessibility(draft_id, {**attributes, "publish": True})

    def _patch_accessibility(self, declaration_id, attributes):
        return _data(self.client.patch(f"/v1/accessibilityDeclarations/{declaration_id}", {
            "data": {"type": "accessibilityDeclarations", "id": declaration_id,
                     "attributes": attributes}}))

    # -- export compliance ---------------------------------------------------------------

    def encryption_declarations(self, app_id):
        # Observed 2026-10-09: /v1/apps/{id}/appEncryptionDeclarations answers 404
        # ("The relationship 'appEncryptionDeclarations' does not exist").
        return self.client.get_all("/v1/appEncryptionDeclarations",
                                   params={"filter[app]": app_id, "limit": 200})

    def create_encryption_declaration(self, app_id, attributes):
        return _data(self.client.post("/v1/appEncryptionDeclarations", {
            "data": {"type": "appEncryptionDeclarations", "attributes": attributes,
                     "relationships": {"app": _rel("apps", app_id)}}}))

    def upload_encryption_document(self, declaration_id, path):
        return self._upload("appEncryptionDeclarationDocuments", "appEncryptionDeclaration",
                            "appEncryptionDeclarations", declaration_id, path)

    # -- licence agreement ---------------------------------------------------------------

    def eula(self, app_id):
        """{id, text, territories:set} of the custom EULA, or None (standard EULA)."""
        record = _data(self.client.get(f"/v1/apps/{app_id}/endUserLicenseAgreement"))
        if not record:
            return None
        territories = {t["id"] for t in self.client.get_all(
            f"/v1/endUserLicenseAgreements/{record['id']}/territories",
            params={"limit": 200})}
        return {"id": record["id"],
                "text": (record.get("attributes") or {}).get("agreementText"),
                "territories": territories}

    def save_eula(self, app_id, eula_id, text, territories):
        territory_refs = {"data": [{"type": "territories", "id": t}
                                   for t in sorted(territories)]}
        if eula_id is None:
            return _data(self.client.post("/v1/endUserLicenseAgreements", {
                "data": {"type": "endUserLicenseAgreements",
                         "attributes": {"agreementText": text},
                         "relationships": {"app": _rel("apps", app_id),
                                           "territories": territory_refs}}}))
        return _data(self.client.patch(f"/v1/endUserLicenseAgreements/{eula_id}", {
            "data": {"type": "endUserLicenseAgreements", "id": eula_id,
                     "attributes": {"agreementText": text},
                     "relationships": {"territories": territory_refs}}}))

    def delete_eula(self, eula_id):
        self.client.delete(f"/v1/endUserLicenseAgreements/{eula_id}")

    # -- uploads -------------------------------------------------------------------------

    def _upload(self, resource, parent_rel, parent_type, parent_id, path):
        """Reserve → PUT the bytes → commit with the MD5, like screenshots."""
        reserved = _data(self.client.post(f"/v1/{resource}", {
            "data": {"type": resource,
                     "attributes": {"fileName": os.path.basename(path),
                                    "fileSize": os.path.getsize(path)},
                     "relationships": {parent_rel: _rel(parent_type, parent_id)}}}))
        checksum = _transfer_bytes(path, reserved["attributes"]["uploadOperations"],
                                   self.upload_transport)
        return _data(self.client.patch(f"/v1/{resource}/{reserved['id']}", {
            "data": {"type": resource, "id": reserved["id"],
                     "attributes": {"uploaded": True, "sourceFileChecksum": checksum}}}))
