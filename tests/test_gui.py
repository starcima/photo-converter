"""Offscreen GUI tests: queueing, drag-and-drop paths and a full background batch
while verifying the event loop stays responsive."""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QCoreApplication, QSettings, QTimer  # noqa: E402

from conftest import fake_decoder, make_fake_arw  # noqa: E402
from models.conversion_job import JobStatus  # noqa: E402


@pytest.fixture
def window(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    QCoreApplication.setOrganizationName("SonyRawConverterTests")
    QCoreApplication.setApplicationName(f"gui-{os.getpid()}")
    QSettings().clear()
    from core import raw_decoder
    monkeypatch.setattr(raw_decoder, "decode", fake_decoder)
    from app.main_window import MainWindow
    w = MainWindow(tmp_path)
    w.out_edit.setText(str(tmp_path / "out"))
    yield w
    w.close()
    QSettings().clear()


def pump_until(cond, timeout=20.0):
    app = QtWidgets.QApplication.instance()
    end = time.time() + timeout
    while time.time() < end and not cond():
        app.processEvents()
        time.sleep(0.005)
    return cond()


def test_queue_add_dedupe_remove_clear(window, tmp_path):
    files = [make_fake_arw(tmp_path / "in" / f"DSC{i}.ARW", size=(40, 30)) for i in range(5)]
    (tmp_path / "in" / "note.txt").write_text("x")
    window.add_paths(files[:3])
    window.add_paths([tmp_path / "in"])  # folder: adds the remaining 2, dedupes 3
    window.add_paths([tmp_path / "in" / "note.txt"])
    assert len(window.jobs) == 5 and window.tree.topLevelItemCount() == 5
    window.tree.topLevelItem(0).setSelected(True)
    window.remove_selected()
    assert len(window.jobs) == 4
    window.clear_queue()
    assert window.jobs == [] and window.stack.currentIndex() == 0


def test_full_batch_keeps_gui_responsive(window, tmp_path):
    files = [make_fake_arw(tmp_path / "in" / f"DSC{i:03}.ARW", size=(400, 300)) for i in range(30)]
    window.add_paths([tmp_path / "in"])
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(time.time()))
    timer.start(10)
    window.start_conversion()
    assert window.busy and not window.convert_btn.isEnabled() and window.cancel_btn.isEnabled()
    assert pump_until(lambda: not window.busy)
    timer.stop()
    assert all(j.status == JobStatus.COMPLETED for j in window.jobs)
    assert len(list((tmp_path / "out").glob("*.jpg"))) == len(files)
    assert window.progress.value() == len(files)
    assert len(ticks) >= 2  # timer kept firing while the worker thread converted


def test_cancel_from_gui(window, tmp_path):
    for i in range(40):
        make_fake_arw(tmp_path / "in" / f"DSC{i:03}.ARW", size=(800, 600))
    window.add_paths([tmp_path / "in"])
    window.start_conversion()
    window.cancel_conversion()
    assert pump_until(lambda: not window.busy)
    statuses = {j.status for j in window.jobs}
    assert JobStatus.CANCELLED in statuses
    assert JobStatus.PENDING not in statuses and JobStatus.PROCESSING not in statuses
