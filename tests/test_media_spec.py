"""App Asset Library media rules (pure): folders, groups, dimensions, limits."""
import os

from andp import media_spec as ms
from andp.asc.asset_refdata import REF_DATA
from media_files import jpeg, mp4, png


def test_folder_names_map_to_placement_groups():
    assert ms.group_for("APP_SCREENSHOT", "APP_IPHONE_67") == "IPHONE_DYNAMIC_ISLAND_LARGE_PROFILE"
    assert ms.group_for("APP_SCREENSHOT", "APP_IPAD_PRO_3GEN_129") == "IPAD_13_PROFILE"
    assert ms.group_for("APP_SCREENSHOT", "IPHONE_DUO") == "IPHONE_DUO_PROFILE"
    assert ms.group_for("APP_SCREENSHOT", "IPHONE_DUO_PROFILE") == "IPHONE_DUO_PROFILE"
    assert ms.group_for("APP_SCREENSHOT", "IPAD_11_DISPLAY") == "IPAD_11_PROFILE"
    assert ms.group_for("APP_PREVIEW", "IPHONE_67") == "IPHONE_DYNAMIC_ISLAND_LARGE_PROFILE"
    assert ms.group_for("IMESSAGE_APP_SCREENSHOT", "IPHONE_DUO") == "IMESSAGE_IPHONE_DUO_PROFILE"
    assert ms.group_for("IMESSAGE_APP_SCREENSHOT", "IMESSAGE_APP_IPHONE_67") == \
        "IMESSAGE_IPHONE_DYNAMIC_ISLAND_LARGE_PROFILE"
    assert ms.group_for("APP_SCREENSHOT", "APP_IPHONE_99") is None


def test_only_legacy_representable_groups_have_a_fallback_type():
    assert ms.legacy_type_for("APP_SCREENSHOT", "IPHONE_DYNAMIC_ISLAND_LARGE_PROFILE") == "APP_IPHONE_67"
    assert ms.legacy_type_for("APP_PREVIEW", "IPAD_13_PROFILE") == "IPAD_PRO_3GEN_129"
    assert ms.legacy_type_for("APP_SCREENSHOT", "IPHONE_DUO_PROFILE") is None
    assert ms.legacy_type_for("PRODUCT_PAGE_HEADER_ASSET", "DEFAULT_PROFILE") is None


def test_image_and_video_sizes_are_read_from_the_file(tmp_path):
    assert ms.media_info(png(tmp_path / "a.png", 1398, 2034)) == {"width": 1398, "height": 2034}
    assert ms.media_info(jpeg(tmp_path / "b.jpg", 2853, 2007)) == {"width": 2853, "height": 2007}
    info = ms.media_info(mp4(tmp_path / "c.mp4", 886, 1920, 20))
    assert info == {"width": 886, "height": 1920, "seconds": 20.0}


def test_iphone_duo_accepts_both_screens_in_both_orientations(tmp_path):
    for i, (w, h) in enumerate([(1398, 2034), (2034, 1398), (2007, 2853), (2853, 2007)]):
        spec, error = ms.check_media(png(tmp_path / f"{i}.png", w, h), "APP_SCREENSHOT",
                                     "IPHONE_DUO_PROFILE", REF_DATA)
        assert error is None and spec["name"]


def test_a_wrong_size_is_refused_with_the_accepted_ones(tmp_path):
    _, error = ms.check_media(png(tmp_path / "x.png", 1290, 2796), "APP_SCREENSHOT",
                              "IPHONE_DUO_PROFILE", REF_DATA)
    assert "1290×2796" in error and "1398×2034" in error and "2007×2853" in error


def test_creative_header_accepts_its_specs_only(tmp_path):
    spec, error = ms.check_media(png(tmp_path / "h.png", 3840, 1646),
                                 "PRODUCT_PAGE_HEADER_ASSET", "DEFAULT_PROFILE", REF_DATA)
    assert error is None
    _, error = ms.check_media(jpeg(tmp_path / "h.jpg", 3840, 1646),
                              "PRODUCT_PAGE_HEADER_ASSET", "DEFAULT_PROFILE", REF_DATA)
    assert error and ".jpg" in error


def test_video_duration_is_checked(tmp_path):
    _, error = ms.check_media(mp4(tmp_path / "v.mp4", 886, 1920, 20), "APP_PREVIEW",
                              "IPHONE_DUO_PROFILE", REF_DATA)
    assert error is None
    _, error = ms.check_media(mp4(tmp_path / "w.mp4", 886, 1920, 40), "APP_PREVIEW",
                              "IPHONE_DUO_PROFILE", REF_DATA)
    assert error and "40" in error


def _tree(root, rel, maker, *args):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return maker(path, *args)


def test_media_tree_reads_every_placement_family_in_file_order(tmp_path):
    root = str(tmp_path)
    _tree(root, "fr-FR/screenshots/IPHONE_DUO/02.png", png, 2007, 2853)
    _tree(root, "fr-FR/screenshots/IPHONE_DUO/01.png", png, 1398, 2034)
    _tree(root, "fr-FR/previews/APP_IPHONE_67/01.mp4", mp4, 886, 1920, 20)
    _tree(root, "fr-FR/product_page_header/header.png", png, 3840, 1646)
    _tree(root, "fr-FR/search_results/card.png", png, 1920, 1280)
    _tree(root, "fr-FR/imessage_screenshots/APP_IPHONE_67/01.png", png, 1290, 2796)
    tree, errors = ms.read_media_tree(root, REF_DATA)
    assert errors == []
    fr = tree["fr-FR"]
    assert [os.path.basename(p) for p in fr[("APP_SCREENSHOT", "IPHONE_DUO_PROFILE")]] == \
        ["01.png", "02.png"]
    assert ("APP_PREVIEW", "IPHONE_DYNAMIC_ISLAND_LARGE_PROFILE") in fr
    assert ("PRODUCT_PAGE_HEADER_ASSET", "DEFAULT_PROFILE") in fr
    assert ("APP_STORE_SEARCH_RESULTS_ASSET", "DEFAULT_PROFILE") in fr
    assert ("IMESSAGE_APP_SCREENSHOT", "IMESSAGE_IPHONE_DYNAMIC_ISLAND_LARGE_PROFILE") in fr


def test_media_tree_reports_unknown_groups_bad_sizes_and_limits(tmp_path):
    root = str(tmp_path)
    _tree(root, "en-US/screenshots/PHONE_BIG/01.png", png, 1290, 2796)
    _tree(root, "en-US/screenshots/IPHONE_DUO/01.png", png, 100, 100)
    for i in range(11):
        _tree(root, f"en-US/screenshots/APP_IPHONE_67/{i:02}.png", png, 1290, 2796)
    _tree(root, "en-US/product_page_header/a.png", png, 3840, 1646)
    _tree(root, "en-US/product_page_header/b.png", png, 3840, 1646)
    _, errors = ms.read_media_tree(root, REF_DATA)
    text = " | ".join(errors)
    assert "PHONE_BIG" in text
    assert "en-US/screenshots/IPHONE_DUO/01.png" in text and "100×100" in text
    assert "11 files" in text and "allows 10" in text
    assert "product_page_header" in text and "allows 1" in text


def test_screenshots_without_media_folders_is_an_empty_tree(tmp_path):
    (tmp_path / "fr-FR").mkdir()
    (tmp_path / "fr-FR" / "description.txt").write_text("x")
    assert ms.read_media_tree(str(tmp_path), REF_DATA) == ({}, [])
