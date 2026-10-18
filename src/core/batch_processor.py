"""GUI-independent batch processing with bounded concurrency and cancellation."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence

from core.converter import Decoder, convert_file
from core.errors import CancelledError, ConversionError
from core.output_manager import OutputPlanner
from core.validation import ensure_writable_dir
from models.conversion_job import CollisionPolicy, ConversionJob, ConversionSettings, JobStatus

log = logging.getLogger(__name__)


@dataclass
class BatchSummary:
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    cancelled: int = 0
    errors: list[tuple[Path, str]] = field(default_factory=list)


class BatchProcessor:
    """Converts a list of jobs. Callbacks are invoked from worker threads."""

    def __init__(
        self,
        jobs: Sequence[ConversionJob],
        settings: ConversionSettings,
        decoder: Optional[Decoder] = None,
        on_job_started: Callable[[int, ConversionJob], None] = lambda i, j: None,
        on_job_finished: Callable[[int, ConversionJob], None] = lambda i, j: None,
    ):
        self.jobs = list(jobs)
        self.settings = settings
        self.decoder = decoder
        self.on_job_started = on_job_started
        self.on_job_finished = on_job_finished
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self.summary = BatchSummary()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def _policy_for(self, job: ConversionJob) -> CollisionPolicy:
        policy = job.collision_override or self.settings.output.collision
        return CollisionPolicy.SKIP if policy == CollisionPolicy.ASK else policy

    def run(self) -> BatchSummary:
        ensure_writable_dir(Path(self.settings.output.output_dir))
        planner = OutputPlanner(self.settings.output, [j.source for j in self.jobs])
        workers = max(1, min(int(self.settings.max_workers), 4))
        if workers == 1:
            for i, job in enumerate(self.jobs):
                self._process(i, job, planner)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(lambda a: self._process(a[0], a[1], planner), enumerate(self.jobs)))
        return self.summary

    def _finish(self, index: int, job: ConversionJob, status: JobStatus, error: Optional[str] = None) -> None:
        job.status, job.error = status, error
        with self._lock:
            if status == JobStatus.COMPLETED:
                self.summary.completed += 1
            elif status == JobStatus.FAILED:
                self.summary.failed += 1
                self.summary.errors.append((job.source, error or ""))
            elif status == JobStatus.SKIPPED:
                self.summary.skipped += 1
            elif status == JobStatus.CANCELLED:
                self.summary.cancelled += 1
        self.on_job_finished(index, job)

    def _process(self, index: int, job: ConversionJob, planner: OutputPlanner) -> None:
        if self.cancelled:
            self._finish(index, job, JobStatus.CANCELLED)
            return
        job.status = JobStatus.PROCESSING
        self.on_job_started(index, job)
        try:
            target = planner.plan(job.source, self._policy_for(job))
            if target is None:
                job.output_path = planner.desired_path(job.source)
                self._finish(index, job, JobStatus.SKIPPED, "Output file already exists")
                return
            job.output_path = target
            w, h = convert_file(job.source, target, self.settings, self.decoder, lambda: self.cancelled)
            job.width, job.height = w, h
            log.info("Converted %s -> %s (%dx%d)", job.source.name, target.name, w, h)
            self._finish(index, job, JobStatus.COMPLETED)
        except CancelledError:
            self._finish(index, job, JobStatus.CANCELLED)
        except ConversionError as exc:
            log.warning("Failed %s: %s", job.source.name, exc)
            self._finish(index, job, JobStatus.FAILED, str(exc))
        except MemoryError:
            log.error("Out of memory on %s", job.source.name)
            self._finish(index, job, JobStatus.FAILED, "Out of memory. Try converting with 1 worker.")
        except Exception as exc:  # isolate unexpected errors to this file
            log.exception("Unexpected error on %s", job.source.name)
            self._finish(index, job, JobStatus.FAILED, f"Unexpected error: {exc}")
