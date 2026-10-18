"""RAW decoding via rawpy/LibRaw. Kept free of GUI and JPEG concerns."""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

from core.errors import DecodeError
from models.conversion_job import HighlightMode, RawSettings, WhiteBalance

log = logging.getLogger(__name__)

try:  # rawpy is a hard runtime dependency, but import lazily-friendly for tests
    import rawpy
except ImportError:  # pragma: no cover
    rawpy = None  # type: ignore[assignment]


@dataclass
class RawInfo:
    width: int
    height: int
    thumbnail: Optional[Image.Image] = None


def libraw_version() -> str:
    if rawpy is None:
        return "unavailable"
    return ".".join(str(v) for v in rawpy.libraw_version)


def _open(path: Path):
    if rawpy is None:
        raise DecodeError("RAW decoding library (rawpy/LibRaw) is not available.")
    try:
        # Read via Python so Unicode paths work on every Windows code page.
        with open(path, "rb") as fh:
            return rawpy.imread(io.BytesIO(fh.read()))
    except MemoryError as exc:
        raise DecodeError("Not enough memory to open this RAW file.") from exc
    except Exception as exc:  # rawpy raises LibRawError subclasses
        raise DecodeError(f"Could not read RAW data ({type(exc).__name__}): {exc}") from exc


def read_info(path: Path, thumb_size: int = 160) -> RawInfo:
    """Fast metadata + embedded preview extraction; no full demosaic."""
    with _open(path) as raw:
        s = raw.sizes
        w, h = s.width, s.height
        if s.flip in (5, 6):  # rotated 90 degrees
            w, h = h, w
        thumb = None
        try:
            t = raw.extract_thumb()
            if t.format == rawpy.ThumbFormat.JPEG:
                thumb = Image.open(io.BytesIO(t.data))
                thumb.draft("RGB", (thumb_size * 2, thumb_size * 2))
                from PIL import ImageOps
                thumb = ImageOps.exif_transpose(thumb.convert("RGB"))
                thumb.thumbnail((thumb_size, thumb_size))
        except Exception as exc:  # thumbnails are best-effort
            log.debug("No embedded thumbnail: %s", exc)
        return RawInfo(w, h, thumb)


def decode(path: Path, settings: RawSettings) -> Image.Image:
    """Fully develop *path* into an 8-bit, correctly oriented sRGB PIL image."""
    with _open(path) as raw:
        params = dict(
            use_camera_wb=settings.white_balance == WhiteBalance.CAMERA,
            use_auto_wb=settings.white_balance == WhiteBalance.AUTO,
            output_color=rawpy.ColorSpace.sRGB,
            output_bps=8,
            demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
            no_auto_bright=not settings.auto_brightness,
            bright=float(settings.brightness),
            highlight_mode=(rawpy.HighlightMode.Blend if settings.highlight_mode == HighlightMode.BLEND
                            else rawpy.HighlightMode.Clip),
        )
        if settings.exposure_ev:
            # LibRaw's exp_shift is linear, valid range 0.25 (-2 EV) .. 8.0 (+3 EV).
            params["exp_shift"] = max(0.25, min(8.0, 2.0 ** settings.exposure_ev))
            params["exp_preserve_highlights"] = 0.5
        try:
            rgb = raw.postprocess(**params)  # applies camera orientation (flip)
        except MemoryError as exc:
            raise DecodeError("Not enough memory to develop this RAW file. Close other programs and retry.") from exc
        except Exception as exc:
            raise DecodeError(f"RAW development failed ({type(exc).__name__}): {exc}") from exc
    img = Image.fromarray(rgb, "RGB")
    del rgb
    return img
