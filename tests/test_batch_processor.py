import os
import threading

import pytest
from PIL import Image

from conftest import fake_decoder, make_fake_arw
from core.batch_processor import BatchProcessor
from core.errors import OutputError
from models.conversion_job import CollisionPolicy, ConversionJob, JobStatus


def jobs_for(paths):
    return [ConversionJob(p) for p in paths]


def test_batch_of_many_files(tmp_path, settings):
    srcs = [make_fake_arw(tmp_path / "in" / f"DSC{i:05}.ARW", size=(60, 40)) for i in range(25)]
    summary = BatchProcessor(jobs_for(srcs), settings, decoder=fake_decoder).run()
    assert summary.completed == 25 and summary.failed == 0
    assert len(list(settings.output.output_dir.glob("*.jpg"))) == 25


@pytest.mark.parametrize("workers", [1, 3])
def test_failure_does_not_stop_batch(tmp_path, settings, workers):
    settings.max_workers = workers
    good = [make_fake_arw(tmp_path / f"g{i}.ARW", size=(40, 30)) for i in range(3)]
    bad = tmp_path / "bad.ARW"
    bad.write_bytes(b"not a raw file at all" * 5000)
    jobs = jobs_for([good[0], bad, good[1], good[2]])
    summary = BatchProcessor(jobs, settings, decoder=fake_decoder).run()
    assert summary.completed == 3 and summary.failed == 1
    assert jobs[1].status == JobStatus.FAILED and jobs[1].error
    assert all(j.status == JobStatus.COMPLETED for j in (jobs[0], jobs[2], jobs[3]))


def test_skip_existing_is_default(tmp_path, settings):
    src = make_fake_arw(tmp_path / "a.ARW", size=(40, 30))
    out = settings.output.output_dir
    out.mkdir(parents=True)
    (out / "a.jpg").write_bytes(b"precious")
    jobs = jobs_for([src])
    summary = BatchProcessor(jobs, settings, decoder=fake_decoder).run()
    assert summary.skipped == 1 and jobs[0].status == JobStatus.SKIPPED
    assert (out / "a.jpg").read_bytes() == b"precious"


def test_ask_policy_uses_per_job_override(tmp_path, settings):
    settings.output.collision = CollisionPolicy.ASK
    src = make_fake_arw(tmp_path / "a.ARW", size=(40, 30))
    out = settings.output.output_dir
    out.mkdir(parents=True)
    (out / "a.jpg").write_bytes(b"old")
    job = ConversionJob(src, collision_override=CollisionPolicy.OVERWRITE)
    BatchProcessor([job], settings, decoder=fake_decoder).run()
    assert job.status == JobStatus.COMPLETED and (out / "a.jpg").read_bytes()[:3] == b"\xff\xd8\xff"


def test_cross_directory_name_collision(tmp_path, settings):
    a = make_fake_arw(tmp_path / "card1" / "DSC1.ARW", size=(40, 30))
    b = make_fake_arw(tmp_path / "card2" / "DSC1.ARW", size=(40, 30))
    jobs = jobs_for([a, b])
    BatchProcessor(jobs, settings, decoder=fake_decoder).run()
    assert {j.output_path.name for j in jobs} == {"DSC1.jpg", "DSC1_1.jpg"}


def test_cancellation_mid_batch(tmp_path, settings):
    srcs = [make_fake_arw(tmp_path / f"{i}.ARW", size=(40, 30)) for i in range(10)]
    holder = {}

    def on_finished(i, job):
        if i == 2:
            holder["bp"].cancel()

    bp = BatchProcessor(jobs_for(srcs), settings, decoder=fake_decoder, on_job_finished=on_finished)
    holder["bp"] = bp
    summary = bp.run()
    assert summary.completed == 3 and summary.cancelled == 7


def test_unwritable_output_folder(tmp_path, settings):
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    settings.output.output_dir = blocker / "out"
    with pytest.raises(OutputError):
        BatchProcessor(jobs_for([make_fake_arw(tmp_path / "a.ARW")]), settings, decoder=fake_decoder).run()


def test_memory_error_isolated(tmp_path, settings):
    calls = {"n": 0}

    def flaky(path, rs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise MemoryError
        return fake_decoder(path, rs)

    srcs = [make_fake_arw(tmp_path / f"{i}.ARW", size=(40, 30)) for i in range(2)]
    summary = BatchProcessor(jobs_for(srcs), settings, decoder=flaky).run()
    assert summary.failed == 1 and summary.completed == 1
