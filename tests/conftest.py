"""Shared fixtures. Unit tests use synthetic TIFF-structured '.ARW' files plus a fake
decoder, so they run anywhere. A real Sony ARW can be supplied for integration tests
via the SONY_ARW_SAMPLE environment variable."""
from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest
from PIL import Image

from core.validation import MIN_RAW_SIZE
from models.conversion_job import ConversionSettings


def _ifd(entries, offset, next_ifd=0):
    """Serialise little-endian TIFF IFD entries [(tag, type, count, payload_bytes)].

    Returns (ifd_bytes, data_bytes) where data is placed right after the IFD.
    """
    n = len(entries)
    data_off = offset + 2 + n * 12 + 4
    head, data = struct.pack("<H", n), b""
    for tag, typ, count, payload in sorted(entries):
        if len(payload) <= 4:
            head += struct.pack("<HHI", tag, typ, count) + payload.ljust(4, b"\0")
        else:
            head += struct.pack("<HHII", tag, typ, count, data_off + len(data))
            data += payload + (b"\0" if len(payload) % 2 else b"")
    return head + struct.pack("<I", next_ifd), data


def _ascii(tag, text):
    b = text.encode() + b"\0"
    return (tag, 2, len(b), b)


def make_fake_arw(path: Path, size=(600, 400), color=(120, 80, 40)) -> Path:
    """Write a minimal uncompressed RGB TIFF with Sony-like EXIF and an .ARW extension.

    Built by hand so that it carries a real Exif sub-IFD, like a genuine ARW.
    """
    w, h = size
    pixels = Image.new("RGB", size, color).tobytes()
    # Layout: header(8) | IFD0+data | ExifIFD+data | pixels
    def ifd0_entries(exif_off, strip_off):
        return [
            (256, 4, 1, struct.pack("<I", w)), (257, 4, 1, struct.pack("<I", h)),
            (258, 3, 3, struct.pack("<HHH", 8, 8, 8)), (259, 3, 1, struct.pack("<H", 1)),
            (262, 3, 1, struct.pack("<H", 2)), (273, 4, 1, struct.pack("<I", strip_off)),
            (274, 3, 1, struct.pack("<H", 6)), (277, 3, 1, struct.pack("<H", 3)),
            (278, 4, 1, struct.pack("<I", h)), (279, 4, 1, struct.pack("<I", len(pixels))),
            _ascii(271, "SONY"), _ascii(272, "ILCE-7M3"),
            (0x8769, 4, 1, struct.pack("<I", exif_off)),
        ]
    exif_entries = [
        _ascii(0x9003, "2024:05:01 10:20:30"), (0x8827, 3, 1, struct.pack("<H", 400)),
        (0x829D, 5, 1, struct.pack("<II", 28, 10)), _ascii(0xA434, "FE 24-70mm F2.8 GM"),
    ]
    a, b = _ifd(ifd0_entries(0, 0), 8)
    exif_off = 8 + len(a) + len(b)
    c, d = _ifd(exif_entries, exif_off)
    strip_off = exif_off + len(c) + len(d)
    a, b = _ifd(ifd0_entries(exif_off, strip_off), 8)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = b"II*\0" + struct.pack("<I", 8) + a + b + c + d + pixels
    path.write_bytes(data.ljust(MIN_RAW_SIZE + 1, b"\0"))  # real ARWs are tens of MB
    return path


def fake_decoder(path: Path, raw_settings) -> Image.Image:
    with Image.open(path) as im:
        return im.convert("RGB")


@pytest.fixture
def settings(tmp_path) -> ConversionSettings:
    s = ConversionSettings()
    s.output.output_dir = tmp_path / "out"
    return s


@pytest.fixture
def real_arw() -> Path:
    p = os.environ.get("SONY_ARW_SAMPLE")
    if not p or not Path(p).is_file():
        pytest.skip("Set SONY_ARW_SAMPLE to a real Sony .ARW file to run integration tests")
    return Path(p)
