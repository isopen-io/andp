"""App Asset Library media rules — pure, no network.

The metadata folder carries the listing's visuals per locale:

    <locale>/screenshots/<GROUP>/*.png|jpg       → APP_SCREENSHOT
    <locale>/previews/<GROUP>/*.mp4|mov|m4v      → APP_PREVIEW
    <locale>/imessage_screenshots/<GROUP>/*      → IMESSAGE_APP_SCREENSHOT
    <locale>/product_page_header/*               → PRODUCT_PAGE_HEADER_ASSET
    <locale>/search_results/*                    → APP_STORE_SEARCH_RESULTS_ASSET

<GROUP> may be an Asset Library placement group (`IPHONE_DUO_PROFILE`), a
display class (`IPHONE_DUO`, `IPAD_11_DISPLAY`) or a legacy screenshot / preview
type (`APP_IPHONE_67`, `IPHONE_67`) — the legacy names map to the group that
replaced them. Files are placed in name order. Every file is checked against
the Asset Library specifications (GET /v1/appAssetLibraryRefData) before it is
sent: extension, exact dimensions, file size, and for videos the duration.
"""
import os
import re
import struct

_IMAGE_EXT = (".png", ".jpg", ".jpeg")
_VIDEO_EXT = (".mp4", ".mov", ".m4v")

# folder -> (placementType, takes a <GROUP> sub-folder)
PLACEMENT_FOLDERS = {
    "screenshots": ("APP_SCREENSHOT", True),
    "previews": ("APP_PREVIEW", True),
    "imessage_screenshots": ("IMESSAGE_APP_SCREENSHOT", True),
    "product_page_header": ("PRODUCT_PAGE_HEADER_ASSET", False),
    "search_results": ("APP_STORE_SEARCH_RESULTS_ASSET", False),
}
VIDEO_PLACEMENTS = frozenset({"APP_PREVIEW"})

# Legacy screenshotDisplayType / previewType (suffix after APP_ / IMESSAGE_APP_)
# -> the Asset Library placement group that replaced it. Observed 2026-10-09 on
# me.meeshy.app: the APP_IPHONE_67 and APP_IPAD_PRO_3GEN_129 sets are mirrored
# as IPHONE_DYNAMIC_ISLAND_LARGE_PROFILE and IPAD_13_PROFILE placements.
_LEGACY_GROUPS = {
    "IPHONE_67": "IPHONE_DYNAMIC_ISLAND_LARGE_PROFILE",
    "IPHONE_61": "IPHONE_DYNAMIC_ISLAND_MEDIUM_PROFILE",
    "IPHONE_65": "IPHONE_FACE_ID_LARGE_PROFILE",
    "IPHONE_58": "IPHONE_FACE_ID_MEDIUM_PROFILE",
    "IPHONE_55": "IPHONE_HOME_BUTTON_LARGE_PROFILE",
    "IPHONE_47": "IPHONE_HOME_BUTTON_MEDIUM_PROFILE",
    "IPHONE_40": "IPHONE_HOME_BUTTON_40_PROFILE",
    "IPHONE_35": "IPHONE_HOME_BUTTON_35_PROFILE",
    "IPAD_PRO_3GEN_129": "IPAD_13_PROFILE",
    "IPAD_PRO_3GEN_11": "IPAD_11_PROFILE",
    "IPAD_PRO_129": "IPAD_129_PROFILE",
    "IPAD_105": "IPAD_105_PROFILE",
    "IPAD_97": "IPAD_97_PROFILE",
    "DESKTOP": "MAC_PROFILE",
    "APPLE_TV": "TV_PROFILE",
    "APPLE_VISION_PRO": "VISION_PRO_PROFILE",
    "WATCH_ULTRA": "WATCH_ULTRA_PROFILE",
    "WATCH_SERIES_10": "WATCH_SERIES_10_PROFILE",
    "WATCH_SERIES_7": "WATCH_SERIES_7_PROFILE",
    "WATCH_SERIES_4": "WATCH_SERIES_4_PROFILE",
    "WATCH_SERIES_3": "WATCH_SERIES_3_PROFILE",
}
_GROUP_TO_LEGACY = {group: legacy for legacy, group in _LEGACY_GROUPS.items()}


def _base_group(name):
    name = name.upper()
    for prefix in ("IMESSAGE_APP_", "APP_", "IMESSAGE_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    if name in _LEGACY_GROUPS:
        return _LEGACY_GROUPS[name]
    if name.endswith("_PROFILE"):
        return name
    if name.endswith("_DISPLAY"):
        return name[:-len("_DISPLAY")] + "_PROFILE"
    return name + "_PROFILE"


def group_for(placement_type, folder, ref=None):
    """The placement group a folder name designates, or None if unknown."""
    from .asc.asset_refdata import REF_DATA
    groups = (ref or REF_DATA)["groups"]
    group = _base_group(folder)
    if placement_type == "IMESSAGE_APP_SCREENSHOT":
        group = "IMESSAGE_" + group
    return group if group in groups else None


def legacy_type_for(placement_type, group):
    """The legacy screenshot / preview type of a group, or None (Asset Library only)."""
    base = group[len("IMESSAGE_"):] if group.startswith("IMESSAGE_") else group
    legacy = _GROUP_TO_LEGACY.get(base)
    if legacy is None:
        return None
    if placement_type == "APP_SCREENSHOT":
        return f"APP_{legacy}"
    if placement_type == "IMESSAGE_APP_SCREENSHOT":
        return f"IMESSAGE_APP_{legacy}"
    if placement_type == "APP_PREVIEW":
        return legacy
    return None


# -- reading media files -------------------------------------------------------------

def _png_size(head):
    if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
        return struct.unpack(">II", head[16:24])
    return None


def _jpeg_size(path):
    with open(path, "rb") as f:
        if f.read(2) != b"\xff\xd8":
            return None
        while True:
            marker = f.read(2)
            if len(marker) < 2 or marker[0] != 0xFF:
                return None
            if marker[1] in (0xD8, 0x01) or 0xD0 <= marker[1] <= 0xD7:
                continue
            length = struct.unpack(">H", f.read(2))[0]
            if marker[1] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                             0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                f.read(1)
                height, width = struct.unpack(">HH", f.read(4))
                return width, height
            f.seek(length - 2, os.SEEK_CUR)


def _boxes(data, start, end):
    pos = start
    while pos + 8 <= end:
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        header = 8
        if size == 1:
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header:
            return
        yield kind, pos + header, pos + size
        pos += size


def _video_info(path):
    """Width, height (first track with a size) and duration from moov/tkhd/mvhd."""
    with open(path, "rb") as f:
        data = f.read()
    info = {}
    for kind, start, end in _boxes(data, 0, len(data)):
        if kind != b"moov":
            continue
        for sub, s_start, s_end in _boxes(data, start, end):
            if sub == b"mvhd":
                version = data[s_start]
                if version == 1:
                    scale, duration = struct.unpack(">IQ", data[s_start + 20:s_start + 32])
                else:
                    scale, duration = struct.unpack(">II", data[s_start + 12:s_start + 20])
                if scale:
                    info["seconds"] = round(duration / scale, 3)
            if sub == b"trak" and "width" not in info:
                for leaf, l_start, l_end in _boxes(data, s_start, s_end):
                    if leaf == b"tkhd":
                        w, h = struct.unpack(">II", data[l_end - 8:l_end])
                        if w and h:
                            info["width"], info["height"] = w >> 16, h >> 16
    return info if "width" in info else None


def media_info(path):
    """{width, height} for an image, plus `seconds` for a video; None if unreadable."""
    ext = os.path.splitext(path)[1].lower()
    if ext in _VIDEO_EXT:
        return _video_info(path)
    with open(path, "rb") as f:
        head = f.read(32)
    size = _png_size(head) if ext == ".png" else _jpeg_size(path)
    if size is None:
        size = _png_size(head) or _jpeg_size(path)
    return None if size is None else {"width": size[0], "height": size[1]}


# -- checking against the specifications ---------------------------------------------

_DURATION = re.compile(r"^PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$")


def _seconds(iso):
    match = _DURATION.match(iso or "")
    if not match:
        return None
    return int(match.group(1) or 0) * 60 + float(match.group(2) or 0)


def _dims(spec):
    (w0, w1), (h0, h1) = spec["w"], spec["h"]
    width = f"{w0}" if w0 == w1 else f"{w0}–{w1}"
    height = f"{h0}" if h0 == h1 else f"{h0}–{h1}"
    return f"{width}×{height}"


def specs_for(placement_type, group, ref):
    ids = ref["mappings"].get(placement_type, {}).get(group, [])
    return [dict(ref["specs"][i], id=i) for i in ids if i in ref["specs"]]


def check_media(path, placement_type, group, ref):
    """(spec, None) when the file matches one accepted spec, else (None, reason)."""
    specs = specs_for(placement_type, group, ref)
    if not specs:
        return None, f"{placement_type} has no specification for {group}"
    ext = os.path.splitext(path)[1].lower()
    info = media_info(path)
    if info is None:
        return None, "cannot read the image or video dimensions"
    size = os.path.getsize(path)
    accepted = ", ".join(sorted({_dims(s) for s in specs}))
    reasons = []
    for spec in specs:
        if ext not in spec["ext"]:
            reasons.append(f"{ext} is not one of {', '.join(spec['ext'])}")
            continue
        (w0, w1), (h0, h1) = spec["w"], spec["h"]
        if not (w0 <= info["width"] <= w1 and h0 <= info["height"] <= h1):
            continue
        if size > spec["max_size"]:
            reasons.append(f"{size} bytes, the limit is {spec['max_size']}")
            continue
        if spec["kind"] == "video" and spec.get("duration") and "seconds" in info:
            low, high = (_seconds(v) for v in spec["duration"])
            if not (low <= info["seconds"] <= high):
                reasons.append(f"{info['seconds']:g} s, the video must last "
                               f"{low:g}–{high:g} s")
                continue
        return spec, None
    found = f"{info['width']}×{info['height']}"
    detail = f"; {reasons[0]}" if reasons else ""
    return None, f"{found} {ext} does not match {placement_type} {group} (accepted: {accepted}){detail}"


def max_count(placement_type, ref, feature="APP_STORE_VERSIONS"):
    return ref["limits"].get(feature, {}).get(placement_type)


def _media_files(folder, placement_type):
    extensions = _VIDEO_EXT if placement_type in VIDEO_PLACEMENTS else _IMAGE_EXT + _VIDEO_EXT
    return sorted(os.path.join(folder, f) for f in os.listdir(folder)
                  if os.path.splitext(f)[1].lower() in extensions and not f.startswith("."))


def read_media_tree(metadata_dir, ref):
    """({locale: {(placementType, group): [paths]}}, errors). Reads local files only."""
    tree, errors = {}, []
    for locale in sorted(os.listdir(metadata_dir)):
        locale_dir = os.path.join(metadata_dir, locale)
        if not os.path.isdir(locale_dir) or locale.startswith((".", "_")):
            continue
        for folder, (placement_type, grouped) in PLACEMENT_FOLDERS.items():
            base = os.path.join(locale_dir, folder)
            if not os.path.isdir(base):
                continue
            entries = ([(name, os.path.join(base, name)) for name in sorted(os.listdir(base))
                        if os.path.isdir(os.path.join(base, name)) and not name.startswith(".")]
                       if grouped else [("DEFAULT_PROFILE", base)])
            for name, path in entries:
                group = group_for(placement_type, name, ref) if grouped else name
                rel = os.path.relpath(path, metadata_dir)
                if group is None:
                    errors.append(f"{rel}: unknown display group {name!r}")
                    continue
                files = _media_files(path, placement_type)
                if not files:
                    continue
                limit = max_count(placement_type, ref)
                if limit and len(files) > limit:
                    errors.append(f"{rel}: {len(files)} files, the App Store allows {limit}")
                for file_path in files:
                    _spec, problem = check_media(file_path, placement_type, group, ref)
                    if problem:
                        errors.append(f"{os.path.relpath(file_path, metadata_dir)}: {problem}")
                tree.setdefault(locale, {})[(placement_type, group)] = files
    return tree, errors
