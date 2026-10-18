"""Application start-up: logging, Qt application, icon, self-test mode."""
from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from version import APP_NAME, APP_VERSION, ORG_NAME


def resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath("resources", *parts)


def log_directory() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    d = Path(base) / "SonyRawConverter" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup_logging() -> Path:
    log_dir = log_directory()
    handler = RotatingFileHandler(log_dir / "converter.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None:  # windowed builds have no console
        root.addHandler(logging.StreamHandler())
    return log_dir


def self_test(out_dir: Path) -> int:
    """Non-interactive check used by CI on the packaged .exe.

    Verifies that the bundled native libraries load and the pipeline works end to end.
    Results are written to ``self_test.json`` because windowed builds have no stdout.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"version": APP_VERSION, "checks": {}}
    ok = True

    def check(name, fn):
        nonlocal ok
        try:
            report["checks"][name] = {"ok": True, "detail": fn()}
        except Exception:
            ok = False
            report["checks"][name] = {"ok": False, "detail": traceback.format_exc()}

    def rawpy_loads():
        import rawpy
        return "LibRaw " + ".".join(map(str, rawpy.libraw_version))

    def rawpy_rejects_corrupt():
        from core.errors import DecodeError
        from core.raw_decoder import decode
        from models.conversion_job import RawSettings
        bad = out_dir / "corrupt_test.ARW"
        bad.write_bytes(b"II*\x00" + b"\x13" * 200_000)
        try:
            decode(bad, RawSettings())
        except DecodeError as exc:
            return f"rejected cleanly: {exc}"
        finally:
            bad.unlink(missing_ok=True)
        raise AssertionError("corrupt file was not rejected")

    def pipeline():
        from PIL import Image
        from core.converter import convert_file
        from models.conversion_job import ConversionSettings
        src = out_dir / "synthetic_ünïcødé test.ARW"
        Image.new("RGB", (300, 200), (90, 140, 200)).save(src, format="TIFF")
        settings = ConversionSettings()
        target = out_dir / "synthetic_ünïcødé test.jpg"
        size = convert_file(src, target, settings,
                            decoder=lambda p, rs: Image.open(p).convert("RGB"))
        with Image.open(target) as im:
            assert im.format == "JPEG" and im.size == size and "icc_profile" in im.info
        return f"wrote {target.name} {size}"

    def qt_gui():
        from PySide6.QtWidgets import QApplication
        from app.main_window import MainWindow
        app = QApplication.instance() or QApplication([sys.argv[0]])
        app.setOrganizationName(ORG_NAME)
        app.setApplicationName(APP_NAME + " SelfTest")
        w = MainWindow(log_directory())
        w.close()
        return f"Qt platform: {app.platformName()}"

    check("rawpy_loads", rawpy_loads)
    check("rawpy_rejects_corrupt", rawpy_rejects_corrupt)
    check("pipeline", pipeline)
    check("qt_gui", qt_gui)
    sample = os.environ.get("SONY_ARW_SAMPLE")
    if sample:
        def real_sample():
            from core.converter import convert_file
            from models.conversion_job import ConversionSettings
            return str(convert_file(Path(sample), out_dir / "real_sample.jpg", ConversionSettings()))
        check("real_arw", real_sample)
    report["ok"] = ok
    (out_dir / "self_test.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] == "--self-test":
        return self_test(Path(argv[2]))

    log_dir = setup_logging()
    log = logging.getLogger("app")
    log.info("Starting %s %s", APP_NAME, APP_VERSION)

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    from app.main_window import MainWindow
    from app.theme import STYLESHEET

    if sys.platform == "win32":
        try:  # own taskbar icon/grouping instead of python's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Starcima.SonyRawConverter")
        except Exception:
            pass

    app = QApplication(argv)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    icon = QIcon(str(resource_path("icons", "app_icon.ico")))
    app.setWindowIcon(icon)

    def excepthook(exc_type, exc, tb):
        log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
        QMessageBox.critical(None, APP_NAME, f"An unexpected error occurred:\n\n{exc}\n\nDetails were "
                                             f"written to the log in:\n{log_dir}")
    sys.excepthook = excepthook

    window = MainWindow(log_dir)
    window.setWindowIcon(icon)
    window.show()
    return app.exec()
