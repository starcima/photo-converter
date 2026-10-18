"""EXIF extraction from ARW (TIFF-structured) files and sRGB ICC handling.

Only a whitelist of well-understood photographic tags is copied. Sony
MakerNotes, RAW-specific strip/tile tags and sub-IFDs are deliberately
dropped because they are meaningless (or harmful) inside a JPEG.
"""
from __future__ import annotations

import logging
import struct
from functools import lru_cache
from pathlib import Path
from typing import Optional

from PIL import Image, ImageCms
from PIL.TiffImagePlugin import ImageFileDirectory_v2

log = logging.getLogger(__name__)

EXIF_IFD_POINTER = 0x8769
ORIENTATION = 0x0112

IFD0_TAGS = {
    0x010F: "Make", 0x0110: "Model", 0x0131: "Software", 0x0132: "DateTime",
    0x013B: "Artist", 0x8298: "Copyright", 0x010E: "ImageDescription",
}
EXIF_TAGS = {
    0x829A: "ExposureTime", 0x829D: "FNumber", 0x8822: "ExposureProgram",
    0x8827: "ISOSpeedRatings", 0x8830: "SensitivityType", 0x8832: "RecommendedExposureIndex",
    0x9000: "ExifVersion", 0x9003: "DateTimeOriginal", 0x9004: "DateTimeDigitized",
    0x9010: "OffsetTime", 0x9011: "OffsetTimeOriginal", 0x9012: "OffsetTimeDigitized",
    0x9201: "ShutterSpeedValue", 0x9202: "ApertureValue", 0x9203: "BrightnessValue",
    0x9204: "ExposureBiasValue", 0x9205: "MaxApertureValue", 0x9207: "MeteringMode",
    0x9208: "LightSource", 0x9209: "Flash", 0x920A: "FocalLength",
    0x9290: "SubSecTime", 0x9291: "SubSecTimeOriginal", 0x9292: "SubSecTimeDigitized",
    0xA401: "CustomRendered", 0xA402: "ExposureMode", 0xA403: "WhiteBalance",
    0xA404: "DigitalZoomRatio", 0xA405: "FocalLengthIn35mmFilm", 0xA406: "SceneCaptureType",
    0xA408: "Contrast", 0xA409: "Saturation", 0xA40A: "Sharpness",
    0xA431: "BodySerialNumber", 0xA432: "LensSpecification", 0xA433: "LensMake", 0xA434: "LensModel",
}


def _read_ifd(fh, header: bytes, offset: int) -> ImageFileDirectory_v2:
    ifd = ImageFileDirectory_v2(ifh=header)
    fh.seek(offset)
    ifd.load(fh)
    return ifd


def read_exif(path: Path) -> Optional[Image.Exif]:
    """Return a cleaned Image.Exif built from the ARW's IFD0 + Exif IFD, or None."""
    try:
        with open(path, "rb") as fh:
            header = fh.read(8)
            prefix = header[:2]
            if prefix not in (b"II", b"MM"):
                return None
            endian = "<" if prefix == b"II" else ">"
            ifd0_offset = struct.unpack(endian + "I", header[4:8])[0]
            ifd0 = _read_ifd(fh, header, ifd0_offset)
            exif = Image.Exif()
            for tag in IFD0_TAGS:
                if tag in ifd0:
                    exif[tag] = ifd0[tag]
            if EXIF_IFD_POINTER in ifd0:
                sub = _read_ifd(fh, header, int(ifd0[EXIF_IFD_POINTER]))
                exif_ifd = exif.get_ifd(EXIF_IFD_POINTER)
                for tag in EXIF_TAGS:
                    if tag in sub:
                        exif_ifd[tag] = sub[tag]
            # Pixels are already rotated during RAW development.
            exif[ORIENTATION] = 1
            return exif
    except Exception as exc:  # never fail a conversion because of metadata
        log.warning("Could not read EXIF from %s: %s", path.name, exc)
        return None


@lru_cache(maxsize=1)
def srgb_icc_bytes() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
