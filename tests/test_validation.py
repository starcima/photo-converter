from pathlib import Path

import pytest

from conftest import make_fake_arw
from core.errors import OutputError, ValidationError
from core.validation import (dedupe_key, ensure_writable_dir, is_supported, scan_folder,
                             unique_new_paths, validate_source)


def test_supported_extensions_case_insensitive():
    assert is_supported(Path("DSC0001.ARW"))
    assert is_supported(Path("dsc0001.arw"))
    assert not is_supported(Path("photo.jpg"))
    assert not is_supported(Path("photo.CR2"))


def test_validate_accepts_tiff_structured_arw(tmp_path):
    validate_source(make_fake_arw(tmp_path / "a.ARW"))


@pytest.mark.parametrize("name,content", [
    ("notes.txt", b"x" * 100_000),           # unsupported type
    ("tiny.ARW", b"II*\x00" + b"\0" * 100),   # truncated
    ("fake.ARW", b"\xff\xd8\xff" + b"\0" * 100_000),  # renamed JPEG
])
def test_validate_rejects_bad_inputs(tmp_path, name, content):
    p = tmp_path / name
    p.write_bytes(content)
    with pytest.raises(ValidationError):
        validate_source(p)


def test_validate_missing_file(tmp_path):
    with pytest.raises(ValidationError):
        validate_source(tmp_path / "gone.ARW")


def test_scan_folder_flat_and_recursive(tmp_path):
    make_fake_arw(tmp_path / "a.ARW")
    make_fake_arw(tmp_path / "b.arw")
    (tmp_path / "c.jpg").write_bytes(b"x")
    make_fake_arw(tmp_path / "sub" / "d.ARW")
    assert {p.name for p in scan_folder(tmp_path)} == {"a.ARW", "b.arw"}
    assert {p.name for p in scan_folder(tmp_path, recursive=True)} == {"a.ARW", "b.arw", "d.ARW"}


def test_duplicate_queue_entries_are_ignored(tmp_path):
    a = make_fake_arw(tmp_path / "a.ARW")
    keys: set[str] = set()
    first = list(unique_new_paths([a, tmp_path / "." / "a.ARW"], keys))
    second = list(unique_new_paths([a], keys))
    assert first == [a] and second == []
    assert dedupe_key(a) in keys


def test_unicode_and_space_paths(tmp_path):
    p = make_fake_arw(tmp_path / "Fotos de viaje 東京" / "DSC 0001 é.ARW")
    validate_source(p)
    assert scan_folder(p.parent) == [p]


def test_writable_dir_created(tmp_path):
    ensure_writable_dir(tmp_path / "new" / "nested")
    assert (tmp_path / "new" / "nested").is_dir()


def test_unwritable_dir_reports_error(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(OutputError):
        ensure_writable_dir(blocker / "sub")  # parent is a file -> cannot create
