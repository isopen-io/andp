"""Tiny but well-formed media files for the Asset Library tests."""
import struct
import zlib


def png(path, width, height):
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"\x00" + b"\x00\x00\x00" * 1
    body = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(body)
    return str(path)


def jpeg(path, width, height):
    sof = (b"\xff\xc0" + struct.pack(">H", 17) + b"\x08"
           + struct.pack(">HH", height, width) + b"\x03" + b"\x01\x11\x00\x02\x11\x00\x03\x11\x00")
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    with open(path, "wb") as f:
        f.write(b"\xff\xd8" + app0 + sof + b"\xff\xd9")
    return str(path)


def _box(kind, payload):
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def mp4(path, width, height, seconds):
    mvhd = (b"\x00\x00\x00\x00" + b"\x00" * 8 + struct.pack(">II", 600, int(seconds * 600))
            + b"\x00" * 80)
    tkhd = (b"\x00\x00\x00\x00" + b"\x00" * 76
            + struct.pack(">II", width << 16, height << 16))
    moov = _box(b"moov", _box(b"mvhd", mvhd) + _box(b"trak", _box(b"tkhd", tkhd)))
    with open(path, "wb") as f:
        f.write(_box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41") + moov)
    return str(path)
