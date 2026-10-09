"""Asset Library sync: plan (read-only) and apply, with the legacy fallback."""
import os

from andp.media_sync import apply_media, plan_media
from listing_fakes import live_state, media_managers
from media_files import png


def _duo(tmp_path, *names):
    folder = tmp_path / "md" / "fr-FR" / "screenshots" / "IPHONE_DUO"
    folder.mkdir(parents=True, exist_ok=True)
    return [png(folder / n, 1398, 2034) for n in names]


def _tree(paths, group="IPHONE_DUO_PROFILE", ptype="APP_SCREENSHOT", locale="fr-FR"):
    return {locale: {(ptype, group): list(paths)}}


def test_plan_uploads_and_places_new_files_and_writes_nothing(tmp_path):
    managers = media_managers(live_state())
    plan = plan_media(managers, "APP", "v1", _tree(_duo(tmp_path, "01.png", "02.png")))
    assert managers.writes == []
    assert plan["backend"] == "asset_library"
    assert [(c["field"], c["action"]) for c in plan["changes"]] == [
        ("01.png", "upload"), ("02.png", "upload")]
    assert plan["changes"][0]["scope"] == "fr-FR · APP_SCREENSHOT · IPHONE_DUO_PROFILE"


def test_a_file_already_in_the_library_is_placed_not_uploaded(tmp_path):
    paths = _duo(tmp_path, "01.png")
    state = live_state(library=[{"id": "i1", "fileName": "01.png",
                                 "fileSize": os.path.getsize(paths[0]),
                                 "state": "APPROVED", "mediaType": "IMAGE"}])
    plan = plan_media(media_managers(state), "APP", "v1", _tree(paths))
    assert [(c["field"], c["action"]) for c in plan["changes"]] == [("01.png", "place")]


def test_placed_files_in_order_are_unchanged_and_a_new_order_is_a_reorder(tmp_path):
    paths = _duo(tmp_path, "01.png", "02.png")
    placed = [{"id": "p1", "placementType": "APP_SCREENSHOT",
               "placementGroup": "IPHONE_DUO_PROFILE", "mediaType": "IMAGE", "mediaId": "i1",
               "fileName": "02.png", "fileSize": 1},
              {"id": "p2", "placementType": "APP_SCREENSHOT",
               "placementGroup": "IPHONE_DUO_PROFILE", "mediaType": "IMAGE", "mediaId": "i2",
               "fileName": "01.png", "fileSize": 1}]
    plan = plan_media(media_managers(live_state(placements={"vl-fr-FR": placed})), "APP", "v1",
                      _tree(paths))
    assert [(c["field"], c["action"], c["current"], c["desired"]) for c in plan["changes"]] == [
        ("order", "reorder", ["02.png", "01.png"], ["01.png", "02.png"])]
    plan = plan_media(media_managers(live_state(placements={"vl-fr-FR": placed[::-1]})),
                      "APP", "v1", _tree(paths))
    assert plan["changes"] == [] and plan["unchanged"] == 2


def test_extra_placements_are_kept_unless_pruned(tmp_path):
    paths = _duo(tmp_path, "01.png")
    placed = [{"id": "p9", "placementType": "APP_SCREENSHOT",
               "placementGroup": "IPHONE_DUO_PROFILE", "mediaType": "IMAGE", "mediaId": "i9",
               "fileName": "old.png", "fileSize": 1}]
    state = live_state(placements={"vl-fr-FR": placed})
    plan = plan_media(media_managers(state), "APP", "v1", _tree(paths))
    assert any("old.png" in n and "kept" in n for n in plan["notes"])
    plan = plan_media(media_managers(state), "APP", "v1", _tree(paths), prune=True)
    assert ("old.png", "remove") in [(c["field"], c["action"]) for c in plan["changes"]]


def test_apply_uploads_places_orders_and_a_replan_is_empty(tmp_path):
    state = live_state()
    managers = media_managers(state)
    tree = _tree(_duo(tmp_path, "01.png", "02.png"))
    plan = plan_media(managers, "APP", "v1", tree)
    writes = apply_media(managers, plan)
    assert writes >= 4
    kinds = [w[0] for w in managers.writes]
    assert kinds[:4] == ["upload", "place", "upload", "place"]
    assert managers.writes[0][2] == "APP_SCREENSHOTS_AND_PREVIEWS"
    replan = plan_media(media_managers(state), "APP", "v1", tree)
    assert replan["changes"] == []


def test_creative_assets_are_uploaded_in_their_category(tmp_path):
    folder = tmp_path / "md" / "fr-FR" / "product_page_header"
    folder.mkdir(parents=True)
    path = png(folder / "header.png", 3840, 1646)
    managers = media_managers(live_state())
    plan = plan_media(managers, "APP", "v1",
                      _tree([path], group="DEFAULT_PROFILE", ptype="PRODUCT_PAGE_HEADER_ASSET"))
    apply_media(managers, plan)
    assert ("upload", "header.png", "CREATIVE_ASSETS") in managers.writes


def test_a_locked_version_marks_media_changes_locked(tmp_path):
    managers = media_managers(live_state())
    plan = plan_media(managers, "APP", "v1", _tree(_duo(tmp_path, "01.png")), locked=True)
    assert all(c["locked"] for c in plan["changes"])
    assert apply_media(managers, plan) == 0 and managers.writes == []


def test_a_missing_localization_is_an_error(tmp_path):
    plan = plan_media(media_managers(live_state()), "APP", "v1",
                      _tree(_duo(tmp_path, "01.png"), locale="it"))
    assert plan["errors"] == ["media it: the version has no it localization yet "
                              "(add its texts first)"]


def test_without_asset_library_legacy_types_fall_back_and_duo_is_refused(tmp_path):
    folder = tmp_path / "md" / "fr-FR" / "screenshots" / "APP_IPHONE_67"
    folder.mkdir(parents=True)
    legacy = png(folder / "01.png", 1290, 2796)
    tree = {"fr-FR": {("APP_SCREENSHOT", "IPHONE_DYNAMIC_ISLAND_LARGE_PROFILE"): [legacy],
                      ("APP_SCREENSHOT", "IPHONE_DUO_PROFILE"): _duo(tmp_path, "01.png")}}
    state = live_state(library_unavailable=True)
    managers = media_managers(state)
    plan = plan_media(managers, "APP", "v1", tree)
    assert plan["backend"] == "legacy"
    assert [(c["field"], c["action"]) for c in plan["changes"]] == [("01.png", "upload")]
    assert any("IPHONE_DUO_PROFILE" in e and "App Asset Library" in e for e in plan["errors"])
    plan["errors"] = []
    apply_media(managers, plan)
    assert ("legacy_upload", "APP_IPHONE_67", "01.png") in managers.writes


def test_apply_puts_new_files_at_their_folder_position_and_extras_last(tmp_path):
    paths = _duo(tmp_path, "01.png", "02.png", "03.png")
    placed = [{"id": f"p{n}", "placementType": "APP_SCREENSHOT",
               "placementGroup": "IPHONE_DUO_PROFILE", "mediaType": "IMAGE", "mediaId": f"i{n}",
               "fileName": name, "fileSize": 1}
              for n, name in enumerate(["old.png", "03.png", "01.png"])]
    state = live_state(placements={"vl-fr-FR": placed})
    managers = media_managers(state)
    apply_media(managers, plan_media(managers, "APP", "v1", _tree(paths)))
    orders = [w for w in managers.writes if w[0] == "order"]
    assert orders[-1][3] == ["01.png", "02.png", "03.png", "old.png"]
    assert [p["fileName"] for p in state["placements"]["vl-fr-FR"]] == \
        ["01.png", "02.png", "03.png", "old.png"]
