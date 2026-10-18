"""Data models shared by the conversion engine, the worker and the GUI."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class JobStatus(str, Enum):
    PENDING = "Pending"
    PROCESSING = "Processing"
    COMPLETED = "Completed"
    FAILED = "Failed"
    SKIPPED = "Skipped"
    CANCELLED = "Cancelled"


class WhiteBalance(str, Enum):
    CAMERA = "camera"   # as recorded by the camera (default)
    AUTO = "auto"       # LibRaw automatic (grey-world)
    DAYLIGHT = "daylight"  # neutral: LibRaw daylight multipliers


class ResizeMode(str, Enum):
    ORIGINAL = "original"
    PERCENT = "percent"
    MAX_DIMENSIONS = "max"


class CollisionPolicy(str, Enum):
    SKIP = "skip"            # safe default
    UNIQUE = "unique"        # DSC01234_1.jpg, DSC01234_2.jpg ...
    ASK = "ask"              # resolved by the GUI before the batch starts
    OVERWRITE = "overwrite"  # only when explicitly selected


class HighlightMode(str, Enum):
    CLIP = "clip"
    BLEND = "blend"


@dataclass
class RawSettings:
    """RAW development (rendering) settings, independent of JPEG encoding."""
    white_balance: WhiteBalance = WhiteBalance.CAMERA
    exposure_ev: float = 0.0          # -2 .. +3 EV, applied linearly by LibRaw
    highlight_mode: HighlightMode = HighlightMode.CLIP
    auto_brightness: bool = True      # LibRaw default tone handling
    brightness: float = 1.0           # LibRaw "bright" multiplier
    sharpen: int = 0                  # 0..100 unsharp-mask strength after resize


@dataclass
class JpegSettings:
    quality: int = 95
    optimize: bool = True
    progressive: bool = False
    subsampling: str = "4:4:4"   # 4:4:4 keeps full colour resolution; 4:2:0 smaller files
    embed_srgb_profile: bool = True
    preserve_metadata: bool = True


@dataclass
class ResizeSettings:
    mode: ResizeMode = ResizeMode.ORIGINAL
    percent: int = 50
    max_width: int = 3840
    max_height: int = 3840
    allow_upscale: bool = False


@dataclass
class OutputSettings:
    output_dir: Path = Path(".")
    preserve_structure: bool = False
    prefix: str = ""
    suffix: str = ""
    collision: CollisionPolicy = CollisionPolicy.SKIP


@dataclass
class ConversionSettings:
    raw: RawSettings = field(default_factory=RawSettings)
    jpeg: JpegSettings = field(default_factory=JpegSettings)
    resize: ResizeSettings = field(default_factory=ResizeSettings)
    output: OutputSettings = field(default_factory=OutputSettings)
    max_workers: int = 1


@dataclass
class ConversionJob:
    source: Path
    status: JobStatus = JobStatus.PENDING
    output_path: Optional[Path] = None
    error: Optional[str] = None
    # Per-job collision override (set by the GUI when the policy is ASK).
    collision_override: Optional[CollisionPolicy] = None
    width: Optional[int] = None
    height: Optional[int] = None

    @property
    def size_bytes(self) -> int:
        try:
            return self.source.stat().st_size
        except OSError:
            return 0
