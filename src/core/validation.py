"""Input validation, folder scanning and destination checks."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterable, Iterator

from core.errors import OutputError, ValidationError

SUPPORTED_EXTENSIONS = frozenset({".arw"})
MIN_RAW_SIZE = 64 * 1024  # anything smaller is certainly not a real ARW


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def validate_source(path: Path) -> None:
    """Raise ValidationError if *path* is not a plausible Sony ARW file."""
    if not is_supported(path):
        raise ValidationError(f"Unsupported file type '{path.suffix}'. Only Sony .ARW files are supported.")
    if not path.is_file():
        raise ValidationError("Source file no longer exists or is not a file.")
    size = path.stat().st_size
    if size < MIN_RAW_SIZE:
        raise ValidationError(f"File is too small ({size} bytes) to be a valid ARW image; it may be corrupted.")
    with open(path, "rb") as fh:
        header = fh.read(4)
    # ARW is TIFF-based: little-endian "II*\0" (or big-endian "MM\0*").
    if header not in (b"II*\x00", b"MM\x00*"):
        raise ValidationError("File does not have a valid ARW/TIFF header; it may be corrupted or renamed.")


def scan_folder(folder: Path, recursive: bool = False) -> list[Path]:
    """Return supported files in *folder*, sorted, optionally recursing."""
    iterator: Iterable[Path] = folder.rglob("*") if recursive else folder.iterdir()
    found = [p for p in iterator if p.is_file() and is_supported(p)]
    return sorted(found, key=lambda p: str(p).lower())


def dedupe_key(path: Path) -> str:
    """Normalised key so the same file is never queued twice (case-insensitive on Windows)."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    return os.path.normcase(str(resolved))


def unique_new_paths(candidates: Iterable[Path], existing_keys: set[str]) -> Iterator[Path]:
    """Yield candidates not already in *existing_keys* (updated in place)."""
    for p in candidates:
        key = dedupe_key(p)
        if key in existing_keys:
            continue
        existing_keys.add(key)
        yield p


def ensure_writable_dir(folder: Path) -> None:
    """Create *folder* if needed and verify a file can be written there."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OutputError(f"Cannot create output folder: {exc.strerror or exc}") from exc
    try:
        fd, probe = tempfile.mkstemp(prefix=".write_test_", dir=folder)
        os.close(fd)
        os.remove(probe)
    except OSError as exc:
        raise OutputError(f"Output folder is not writable: {exc.strerror or exc}") from exc


def free_space_bytes(folder: Path) -> int:
    probe = folder
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free
