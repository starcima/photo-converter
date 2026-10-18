# PyInstaller spec — one-folder build (fast start-up, reliable with native libs).
# Build with:  pyinstaller packaging/sony_raw_converter.spec --noconfirm
from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parent

hidden = collect_submodules("rawpy")
binaries = collect_dynamic_libs("rawpy")

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=[(str(ROOT / "resources"), "resources")],
    hiddenimports=hidden + [
        "bootstrap", "version",
        "app.main_window", "app.settings", "app.theme",
        "core.batch_processor", "core.converter", "core.metadata", "core.output_manager",
        "core.raw_decoder", "core.validation", "core.errors",
        "models.conversion_job", "workers.conversion_worker",
        "PIL.ImageCms",
    ],
    excludes=[
        "tkinter", "matplotlib", "scipy", "pandas", "pytest", "IPython",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
        "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtPdf",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SonyRawConverter",
    icon=str(ROOT / "resources" / "icons" / "app_icon.ico"),
    version=str(ROOT / "packaging" / "version_info.txt"),
    console=False,          # GUI app: no console window
    upx=False,              # UPX triggers antivirus false positives
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="SonyRawConverter")
