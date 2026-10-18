"""Single-file conversion pipeline, split into small testable stages."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageFilter

from core import metadata, raw_decoder
from core.errors import CancelledError, OutputError, ValidationError
from core.output_manager import atomic_write, validate_jpeg
from core.validation import validate_source
from models.conversion_job import ConversionSettings, JpegSettings, ResizeMode, ResizeSettings

log = logging.getLogger(__name__)

Decoder = Callable[[Path, "object"], Image.Image]
CancelCheck = Callable[[], bool]


def compute_output_size(width: int, height: int, rs: ResizeSettings) -> tuple[int, int]:
    """Target dimensions preserving aspect ratio; never upscales unless allowed."""
    if width <= 0 or height <= 0:
        raise ValidationError("Image has invalid dimensions.")
    if rs.mode == ResizeMode.ORIGINAL:
        return width, height
    if rs.mode == ResizeMode.PERCENT:
        if not 1 <= rs.percent <= 400:
            raise ValidationError("Resize percentage must be between 1 and 400.")
        scale = rs.percent / 100.0
    elif rs.mode == ResizeMode.MAX_DIMENSIONS:
        if rs.max_width < 1 or rs.max_height < 1:
            raise ValidationError("Maximum width and height must be at least 1 pixel.")
        scale = min(rs.max_width / width, rs.max_height / height)
    else:  # pragma: no cover
        raise ValidationError(f"Unknown resize mode {rs.mode}")
    if scale > 1.0 and not rs.allow_upscale:
        scale = 1.0
    return max(1, round(width * scale)), max(1, round(height * scale))


def resize_image(img: Image.Image, rs: ResizeSettings) -> Image.Image:
    size = compute_output_size(img.width, img.height, rs)
    if size == img.size:
        return img
    return img.resize(size, Image.Resampling.LANCZOS, reducing_gap=3.0)


def sharpen_image(img: Image.Image, amount: int) -> Image.Image:
    if amount <= 0:
        return img
    return img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=int(amount * 1.5), threshold=2))


def jpeg_save_kwargs(js: JpegSettings, exif: Optional[Image.Exif]) -> dict:
    if not 1 <= js.quality <= 100:
        raise ValidationError("JPEG quality must be between 1 and 100.")
    kw: dict = dict(
        format="JPEG", quality=js.quality, optimize=js.optimize,
        progressive=js.progressive, subsampling=js.subsampling,
    )
    if js.embed_srgb_profile:
        kw["icc_profile"] = metadata.srgb_icc_bytes()
    if js.preserve_metadata and exif is not None:
        kw["exif"] = exif.tobytes()
    return kw


def convert_file(
    source: Path,
    target: Path,
    settings: ConversionSettings,
    decoder: Optional[Decoder] = None,
    is_cancelled: CancelCheck = lambda: False,
) -> tuple[int, int]:
    """Convert one RAW file to *target*. Returns the output (width, height).

    Raises a ConversionError subclass on failure. The source is only ever read.
    """
    decoder = decoder or raw_decoder.decode
    validate_source(source)                                   # 1. validate
    if is_cancelled():
        raise CancelledError("Cancelled")
    img = decoder(source, settings.raw)                       # 2-5. decode, develop, sRGB, orient
    if is_cancelled():
        raise CancelledError("Cancelled")
    img = resize_image(img, settings.resize)                  # 6. resize
    img = sharpen_image(img, settings.raw.sharpen)
    exif = metadata.read_exif(source) if settings.jpeg.preserve_metadata else None
    save_kw = jpeg_save_kwargs(settings.jpeg, exif)           # 7-8. encoding + metadata
    out_size = img.size

    def write(tmp: Path) -> None:
        try:
            img.save(tmp, **save_kw)
        except (ValueError, OSError) as exc:
            # Rare libjpeg buffer/EXIF edge cases: retry once with a conservative encoder setup.
            log.warning("JPEG encode failed (%s); retrying without optimisation", exc)
            save_kw["optimize"] = False
            try:
                img.save(tmp, **save_kw)
            except (ValueError, OSError):
                if "exif" not in save_kw:
                    raise
                log.warning("Retrying without EXIF metadata")
                save_kw.pop("exif")
                img.save(tmp, **save_kw)

    if is_cancelled():
        raise CancelledError("Cancelled")
    try:
        atomic_write(target, write, lambda p: validate_jpeg(p, out_size))  # 9-11
    except OSError as exc:
        raise OutputError(f"Could not write JPEG: {exc.strerror or exc}") from exc
    img.close()
    return out_size
