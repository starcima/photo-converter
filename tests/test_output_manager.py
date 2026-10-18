from pathlib import Path

import pytest
from PIL import Image

from core.errors import OutputError
from core.output_manager import OutputPlanner, atomic_write, validate_jpeg
from models.conversion_job import CollisionPolicy, OutputSettings


def planner(tmp_path, sources=(), **kw):
    return OutputPlanner(OutputSettings(output_dir=tmp_path / "out", **kw), list(sources))


def test_default_name_replaces_extension(tmp_path):
    p = planner(tmp_path)
    assert p.plan(Path("/x/DSC01234.ARW"), CollisionPolicy.SKIP) == tmp_path / "out" / "DSC01234.jpg"


def test_prefix_suffix(tmp_path):
    p = planner(tmp_path, prefix="trip_", suffix="_web")
    assert p.desired_path(Path("/x/DSC1.ARW")).name == "trip_DSC1_web.jpg"


def test_existing_file_policies(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "DSC01234.jpg").write_bytes(b"old")
    src = Path("/x/DSC01234.ARW")
    assert planner(tmp_path).plan(src, CollisionPolicy.SKIP) is None
    assert planner(tmp_path).plan(src, CollisionPolicy.UNIQUE).name == "DSC01234_1.jpg"
    assert planner(tmp_path).plan(src, CollisionPolicy.OVERWRITE).name == "DSC01234.jpg"
    (out / "DSC01234_1.jpg").write_bytes(b"old")
    assert planner(tmp_path).plan(src, CollisionPolicy.UNIQUE).name == "DSC01234_2.jpg"


@pytest.mark.parametrize("policy", list(CollisionPolicy))
def test_same_basename_from_different_folders_never_collide(tmp_path, policy):
    p = planner(tmp_path)
    a = p.plan(Path("/card1/DSC01234.ARW"), policy)
    b = p.plan(Path("/card2/DSC01234.ARW"), policy)
    assert a is not None and b is not None and a != b


def test_preserve_structure(tmp_path):
    srcs = [tmp_path / "in" / "day1" / "a.ARW", tmp_path / "in" / "day2" / "a.ARW"]
    for s in srcs:
        s.parent.mkdir(parents=True, exist_ok=True)
    p = planner(tmp_path, srcs, preserve_structure=True)
    assert p.plan(srcs[0], CollisionPolicy.SKIP) == tmp_path / "out" / "day1" / "a.jpg"
    assert p.plan(srcs[1], CollisionPolicy.SKIP) == tmp_path / "out" / "day2" / "a.jpg"


def test_atomic_write_leaves_nothing_on_failure(tmp_path):
    target = tmp_path / "x.jpg"

    def bad_write(tmp: Path):
        tmp.write_bytes(b"garbage")

    with pytest.raises(OutputError):
        atomic_write(target, bad_write, validate_jpeg)
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_atomic_write_success(tmp_path):
    target = tmp_path / "x.jpg"
    atomic_write(target, lambda t: Image.new("RGB", (10, 10)).save(t, "JPEG"), validate_jpeg)
    assert target.read_bytes()[:3] == b"\xff\xd8\xff"
    assert [p.name for p in tmp_path.iterdir()] == ["x.jpg"]
