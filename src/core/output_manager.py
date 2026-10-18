"""Output path planning, collision handling and atomic file writes."""
from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Iterable, Optional

from core.errors import OutputError
from models.conversion_job import CollisionPolicy, OutputSettings

JPEG_SOI = b"\xff\xd8\xff"


def common_root(sources: Iterable[Path]) -> Optional[Path]:
    parents = [str(p.parent.resolve()) for p in sources]
    if not parents:
        return None
    try:
        return Path(os.path.commonpath(parents))
    except ValueError:  # different drives on Windows
        return None


class OutputPlanner:
    """Plans unique output paths for a batch.

    Keeps track of names already claimed *within this batch* so two sources
    with the same base name (e.g. DSC01234.ARW from two cards) never write
    to the same JPEG, even when the target files do not exist yet.
    """

    def __init__(self, settings: OutputSettings, sources: Iterable[Path]):
        self.settings = settings
        self.root = common_root(list(sources)) if settings.preserve_structure else None
        self._claimed: set[str] = set()
        self._lock = threading.Lock()

    def desired_path(self, source: Path) -> Path:
        s = self.settings
        name = f"{s.prefix}{source.stem}{s.suffix}.jpg"
        folder = Path(s.output_dir)
        if self.root is not None:
            try:
                rel = source.parent.resolve().relative_to(self.root)
                folder = folder / rel
            except ValueError:
                pass
        return folder / name

    def plan(self, source: Path, policy: CollisionPolicy) -> Optional[Path]:
        """Return the target path, or None if the file should be skipped.

        ``policy`` must already be resolved (never ASK here).
        """
        desired = self.desired_path(source)
        with self._lock:
            key = os.path.normcase(str(desired))
            exists_on_disk = desired.exists()
            claimed = key in self._claimed
            if not exists_on_disk and not claimed:
                self._claimed.add(key)
                return desired
            if claimed or policy == CollisionPolicy.UNIQUE:
                # In-batch duplicates always get a unique name: never silently overwrite a sibling.
                path = self._unique(desired)
                self._claimed.add(os.path.normcase(str(path)))
                return path
            if policy == CollisionPolicy.OVERWRITE:
                self._claimed.add(key)
                return desired
            return None  # SKIP

    def _unique(self, desired: Path) -> Path:
        n = 1
        while True:
            candidate = desired.with_name(f"{desired.stem}_{n}{desired.suffix}")
            if not candidate.exists() and os.path.normcase(str(candidate)) not in self._claimed:
                return candidate
            n += 1


def atomic_write(target: Path, write_fn: Callable[[Path], None], validate_fn: Callable[[Path], None]) -> None:
    """Write via a temporary file in the destination folder, validate, then move into place."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.stem}.", suffix=".partial", dir=target.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        write_fn(tmp)
        validate_fn(tmp)
        os.replace(tmp, target)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def validate_jpeg(path: Path, expected_size: Optional[tuple[int, int]] = None) -> None:
    from PIL import Image

    if path.stat().st_size < 100:
        raise OutputError("Written JPEG is empty or truncated.")
    with open(path, "rb") as fh:
        if fh.read(3) != JPEG_SOI:
            raise OutputError("Written file does not have a JPEG signature.")
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            if im.format != "JPEG":
                raise OutputError(f"Written file is {im.format}, not JPEG.")
            if expected_size and im.size != expected_size:
                raise OutputError(f"JPEG size {im.size} does not match expected {expected_size}.")
            im.load()
    except OutputError:
        raise
    except Exception as exc:
        raise OutputError(f"Written JPEG failed validation: {exc}") from exc
