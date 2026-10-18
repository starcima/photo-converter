"""Persist user preferences with QSettings (per-user registry key on Windows)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

from models.conversion_job import (CollisionPolicy, ConversionSettings, HighlightMode, ResizeMode,
                                   WhiteBalance)


def default_output_dir() -> Path:
    pictures = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    return Path(pictures or Path.home()) / "Converted JPG"


class AppSettings:
    def __init__(self) -> None:
        self.qs = QSettings()

    def _get(self, key, default, typ):
        value = self.qs.value(key, default)
        try:
            if typ is bool:
                return value in (True, "true", "1", 1)
            return typ(value)
        except (TypeError, ValueError):
            return default

    def load(self) -> ConversionSettings:
        s = ConversionSettings()
        g = self._get
        s.jpeg.quality = max(1, min(100, g("jpeg/quality", 95, int)))
        s.jpeg.subsampling = g("jpeg/subsampling", "4:4:4", str)
        s.jpeg.progressive = g("jpeg/progressive", False, bool)
        s.jpeg.preserve_metadata = g("jpeg/metadata", True, bool)
        s.jpeg.embed_srgb_profile = g("jpeg/icc", True, bool)
        try:
            s.resize.mode = ResizeMode(g("resize/mode", "original", str))
            s.raw.white_balance = WhiteBalance(g("raw/wb", "camera", str))
            s.raw.highlight_mode = HighlightMode(g("raw/highlights", "clip", str))
            s.output.collision = CollisionPolicy(g("output/collision", "skip", str))
        except ValueError:
            pass
        s.resize.percent = g("resize/percent", 50, int)
        s.resize.max_width = g("resize/max_w", 3840, int)
        s.resize.max_height = g("resize/max_h", 3840, int)
        s.raw.exposure_ev = g("raw/exposure", 0.0, float)
        s.raw.auto_brightness = g("raw/auto_bright", True, bool)
        s.raw.sharpen = g("raw/sharpen", 0, int)
        s.output.output_dir = Path(g("output/dir", str(default_output_dir()), str))
        s.output.preserve_structure = g("output/preserve", False, bool)
        s.output.prefix = g("output/prefix", "", str)
        s.output.suffix = g("output/suffix", "", str)
        s.max_workers = max(1, min(4, g("perf/workers", 1, int)))
        return s

    def save(self, s: ConversionSettings) -> None:
        v = self.qs.setValue
        v("jpeg/quality", s.jpeg.quality); v("jpeg/subsampling", s.jpeg.subsampling)
        v("jpeg/progressive", s.jpeg.progressive); v("jpeg/metadata", s.jpeg.preserve_metadata)
        v("jpeg/icc", s.jpeg.embed_srgb_profile)
        v("resize/mode", s.resize.mode.value); v("resize/percent", s.resize.percent)
        v("resize/max_w", s.resize.max_width); v("resize/max_h", s.resize.max_height)
        v("raw/wb", s.raw.white_balance.value); v("raw/exposure", s.raw.exposure_ev)
        v("raw/highlights", s.raw.highlight_mode.value); v("raw/auto_bright", s.raw.auto_brightness)
        v("raw/sharpen", s.raw.sharpen)
        v("output/dir", str(s.output.output_dir)); v("output/preserve", s.output.preserve_structure)
        v("output/prefix", s.output.prefix); v("output/suffix", s.output.suffix)
        v("output/collision", s.output.collision.value)
        v("perf/workers", s.max_workers)
        self.qs.sync()

    def recursive_scan(self) -> bool:
        return self._get("ui/recursive", False, bool)

    def set_recursive_scan(self, value: bool) -> None:
        self.qs.setValue("ui/recursive", value)

    def last_input_dir(self) -> str:
        return self._get("ui/last_input", "", str)

    def set_last_input_dir(self, value: str) -> None:
        self.qs.setValue("ui/last_input", value)
