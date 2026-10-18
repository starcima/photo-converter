"""Qt background workers: batch conversion and thumbnail loading."""
from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QObject, QRunnable, Signal, Slot
from PySide6.QtGui import QImage

from core.batch_processor import BatchProcessor, BatchSummary
from core.raw_decoder import read_info
from models.conversion_job import ConversionJob, ConversionSettings

log = logging.getLogger(__name__)


class ConversionWorker(QObject):
    """Runs a BatchProcessor inside a QThread; communicates only via signals."""

    job_started = Signal(int, str)            # row index, file name
    job_finished = Signal(int, object)        # row index, ConversionJob snapshot
    finished = Signal(object)                 # BatchSummary
    error = Signal(str)                       # fatal (whole batch) error

    def __init__(self, jobs: Sequence[ConversionJob], settings: ConversionSettings, rows: Sequence[int]):
        super().__init__()
        self._rows = list(rows)
        self._processor = BatchProcessor(
            jobs, copy.deepcopy(settings),
            on_job_started=lambda i, j: self.job_started.emit(self._rows[i], j.source.name),
            on_job_finished=lambda i, j: self.job_finished.emit(self._rows[i], copy.copy(j)),
        )

    @Slot()
    def run(self) -> None:
        try:
            summary = self._processor.run()
        except Exception as exc:
            log.exception("Batch aborted")
            self.error.emit(str(exc))
            summary = self._processor.summary
        self.finished.emit(summary)

    def cancel(self) -> None:
        self._processor.cancel()


class ThumbnailSignals(QObject):
    loaded = Signal(str, object, int, int)  # key, QImage|None, width, height


class ThumbnailTask(QRunnable):
    """Reads the embedded preview + dimensions without a full RAW decode."""

    def __init__(self, key: str, path: Path, signals: ThumbnailSignals):
        super().__init__()
        self.key, self.path, self.signals = key, path, signals
        self.setAutoDelete(True)

    def run(self) -> None:
        qimg, w, h = None, 0, 0
        try:
            info = read_info(self.path, thumb_size=96)
            w, h = info.width, info.height
            if info.thumbnail is not None:
                t = info.thumbnail.convert("RGB")
                qimg = QImage(t.tobytes(), t.width, t.height, t.width * 3, QImage.Format.Format_RGB888).copy()
        except Exception as exc:
            log.debug("Thumbnail failed for %s: %s", self.path.name, exc)
        try:
            self.signals.loaded.emit(self.key, qimg, w, h)
        except RuntimeError:  # window closed while loading
            pass
