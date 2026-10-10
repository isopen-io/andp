"""The App Asset Library (App Store Connect API 4.5.1, opened 2026-10-05).

The library holds an app's images and videos once; a *placement* puts one of
them on a version localization (or a custom product page, an experiment
treatment, an in-app event) for one placement type and one placement group —
a group being a display class on a store, e.g. IPHONE_DUO_PROFILE.

Upload follows the screenshot flow — reserve, PUT the bytes, commit with
`uploaded: true` (the update request carries no checksum) — then a placement
is created and the group is reordered by an ordering request.
"""
import os

from .assets import _default_upload_transport, _transfer_bytes

_VIDEO_EXT = (".mp4", ".mov", ".m4v")
_RESOURCE = {"IMAGE": "appAssetLibraryImages", "VIDEO": "appAssetLibraryVideos"}
_RELATION = {"IMAGE": "image", "VIDEO": "video"}
# What a placement sits on: the relationship name -> its resource type.
VERSION_LOCALIZATION = "appStoreVersionLocalization"
EVENT_LOCALIZATION = "appEventLocalization"
_PARENT_TYPES = {VERSION_LOCALIZATION: "appStoreVersionLocalizations",
                 EVENT_LOCALIZATION: "appEventLocalizations"}


def media_type_of(path):
    return "VIDEO" if os.path.splitext(path)[1].lower() in _VIDEO_EXT else "IMAGE"


def normalize_ref_data(attributes):
    """The compact form ANDP validates against (same shape as asset_refdata)."""
    def spec(s, kind):
        d = s.get("dimensions") or {}
        out = {"kind": kind, "name": s.get("shortName"),
               "w": [d.get("minWidth"), d.get("maxWidth")],
               "h": [d.get("minHeight"), d.get("maxHeight")],
               "ext": s.get("fileExtensions") or [], "max_size": s.get("maxFileSize")}
        if kind == "video":
            out["fps"] = [[f.get("minFps"), f.get("maxFps")] for f in s.get("frameRates") or []]
            duration = s.get("duration")
            out["duration"] = [duration.get("min"), duration.get("max")] if duration else None
        else:
            out["alpha"] = bool(s.get("alphaAllowed"))
        return out

    specs = {s["specId"]: spec(s, "image") for s in attributes.get("imageSpecs") or []}
    specs.update({s["specId"]: spec(s, "video") for s in attributes.get("videoSpecs") or []})
    placement_types = attributes.get("placementTypes") or []
    return {
        "specs": specs,
        "mappings": {p["placementTypeId"]: {m["placementGroupId"]: m["specs"]
                                            for m in p.get("specMappings") or []}
                     for p in placement_types},
        "categories": {p["placementTypeId"]: p.get("acceptsAssetCategories") or []
                       for p in placement_types},
        "limits": {f["featureId"]: {p["placementType"]: max(
            (g.get("maxCount") or 0) for g in p.get("groupLimits") or [{}])
            for p in f.get("placementPolicies") or []}
            for f in attributes.get("features") or []},
        "groups": {g["placementProfileGroupId"]: {"platform": g.get("platform"),
                                                  "display_class": g.get("displayClassId")}
                   for g in attributes.get("placementProfileGroups") or []},
        "display_classes": {d["displayClassId"]: {"device_family": d.get("deviceFamily"),
                                                  "screens": d.get("screenDimensions") or []}
                            for d in attributes.get("displayClasses") or []},
    }


def _asset_view(item, media_type):
    attrs = item.get("attributes") or {}
    return {"id": item["id"], "fileName": attrs.get("fileName"),
            "fileSize": attrs.get("fileSize"), "state": attrs.get("state"),
            "mediaType": media_type}


class AssetLibraryManager:
    def __init__(self, client, upload_transport=None):
        self.client = client
        self.upload_transport = upload_transport or _default_upload_transport
        self._ref = None

    def library_id(self, app_id):
        data = (self.client.get(f"/v1/apps/{app_id}/assetLibrary") or {}).get("data")
        return data and data["id"]

    def ref_data(self):
        if self._ref is None:
            data = (self.client.get("/v1/appAssetLibraryRefData") or {}).get("data") or []
            record = data[0] if isinstance(data, list) and data else (data or {})
            self._ref = normalize_ref_data(record.get("attributes") or {})
        return self._ref

    def assets(self, library_id, media_type):
        """The library's images or videos. Observed 2026-10-09: listed at
        /v1/appAssetLibraries/{id}/images|videos (absent from the OpenAPI file)."""
        kind = "images" if media_type == "IMAGE" else "videos"
        items = self.client.get_all(f"/v1/appAssetLibraries/{library_id}/{kind}",
                                    params={"limit": 200})
        return [_asset_view(i, media_type) for i in items]

    def placements(self, localization_id, parent=VERSION_LOCALIZATION):
        """The localization's placements in display order, with their file names.
        `parent` is the relationship the localization fills (version or in-app
        event — /v1/appEventLocalizations/{id}/placements, OpenAPI 4.5.1)."""
        response = self.client.get(
            f"/v1/{_PARENT_TYPES[parent]}/{localization_id}/placements",
            params={"include": "image,video", "sort": "placementGroupPosition",
                    "limit": 200}) or {}
        included = {(i.get("type"), i.get("id")): i.get("attributes") or {}
                    for i in response.get("included") or []}
        views = []
        for item in response.get("data") or []:
            attrs = item.get("attributes") or {}
            rels = item.get("relationships") or {}
            media_type = attrs.get("mediaType") or ("VIDEO" if (rels.get("video") or {})
                                                    .get("data") else "IMAGE")
            ref = (rels.get(_RELATION[media_type]) or {}).get("data") or {}
            file_attrs = included.get((_RESOURCE[media_type], ref.get("id")), {})
            views.append({"id": item["id"], "placementType": attrs.get("placementType"),
                          "placementGroup": attrs.get("placementGroup"),
                          "state": attrs.get("state"), "mediaType": media_type,
                          "mediaId": ref.get("id"), "fileName": file_attrs.get("fileName"),
                          "fileSize": file_attrs.get("fileSize")})
        return views

    def upload(self, library_id, path, category):
        """Reserve → PUT → commit an image or a video; returns the asset view."""
        media_type = media_type_of(path)
        resource = _RESOURCE[media_type]
        name = os.path.basename(path)
        reserved = (self.client.post(f"/v1/{resource}", {
            "data": {"type": resource,
                     "attributes": {"category": category, "fileName": name,
                                    "fileSize": os.path.getsize(path), "referenceName": name},
                     "relationships": {"assetLibrary": {"data": {
                         "type": "appAssetLibraries", "id": library_id}}}}}) or {})["data"]
        _transfer_bytes(path, (reserved.get("attributes") or {}).get("uploadOperations") or [],
                        self.upload_transport)
        committed = (self.client.patch(f"/v1/{resource}/{reserved['id']}", {
            "data": {"type": resource, "id": reserved["id"],
                     "attributes": {"uploaded": True}}}) or {}).get("data") or reserved
        return _asset_view(committed, media_type)

    def place(self, localization_id, placement_type, group, media_type, media_id,
              parent=VERSION_LOCALIZATION):
        return (self.client.post("/v1/appAssetLibraryPlacements", {
            "data": {"type": "appAssetLibraryPlacements",
                     "attributes": {"placementType": placement_type, "placementGroup": group},
                     "relationships": {
                         _RELATION[media_type]: {"data": {"type": _RESOURCE[media_type],
                                                          "id": media_id}},
                         parent: {"data": {"type": _PARENT_TYPES[parent],
                                           "id": localization_id}}}}}) or {}).get("data")

    def unplace(self, placement_id):
        self.client.delete(f"/v1/appAssetLibraryPlacements/{placement_id}")

    def order(self, localization_id, group, placement_ids):
        return (self.client.post("/v1/appAssetLibraryPlacementOrderingRequests", {
            "data": {"type": "appAssetLibraryPlacementOrderingRequests",
                     "attributes": {"placementGroup": group},
                     "relationships": {
                         "orderedPlacements": {"data": [
                             {"type": "appAssetLibraryPlacements", "id": pid}
                             for pid in placement_ids]},
                         "appStoreVersionLocalization": {"data": {
                             "type": "appStoreVersionLocalizations",
                             "id": localization_id}}}}}) or {}).get("data")
