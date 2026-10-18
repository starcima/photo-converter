"""Main application window."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, QThread, QThreadPool, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QPixmap, QShortcut, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSlider, QSpinBox, QStackedWidget,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from app.settings import AppSettings
from app.theme import STATUS_COLORS
from core.converter import compute_output_size
from core.errors import OutputError
from core.output_manager import OutputPlanner
from core.raw_decoder import libraw_version
from core.validation import (ensure_writable_dir, free_space_bytes, is_supported, scan_folder,
                             unique_new_paths, dedupe_key)
from models.conversion_job import (CollisionPolicy, ConversionJob, ConversionSettings, HighlightMode,
                                   JobStatus, ResizeMode, WhiteBalance)
from version import APP_NAME, APP_VERSION
from workers.conversion_worker import ConversionWorker, ThumbnailSignals, ThumbnailTask

log = logging.getLogger(__name__)

COL_FILE, COL_SIZE, COL_DIMS, COL_STATUS, COL_OUTPUT, COL_ERROR = range(6)
EST_BYTES_PER_OUTPUT = 30 * 1024 * 1024  # generous upper bound for a full-res 61 MP JPEG


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def section(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setObjectName("sectionTitle")
    return lbl


def hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("hint")
    lbl.setWordWrap(True)
    return lbl


class DropZone(QFrame):
    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("dropZone")
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        big = QLabel("Drop Sony .ARW photos or folders here")
        big.setStyleSheet("font-size: 15pt; font-weight: 600;")
        big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        small = QLabel("or use Add Photos / Add Folder on the left. Hundreds of files at once are fine.")
        small.setObjectName("muted")
        small.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(big)
        lay.addWidget(small)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class PreferencesDialog(QDialog):
    def __init__(self, parent, settings: ConversionSettings, recursive: bool, log_dir: Path):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        form = QFormLayout(self)
        self.recursive = QCheckBox("Include subfolders when using Add Folder / dropping folders")
        self.recursive.setChecked(recursive)
        self.workers = QSpinBox()
        self.workers.setRange(1, 4)
        self.workers.setValue(settings.max_workers)
        self.workers.setToolTip("Files converted in parallel. Each needs ~1-2 GB RAM for 40-60 MP files.")
        form.addRow(self.recursive)
        form.addRow("Parallel conversions:", self.workers)
        form.addRow(hint("Use 1 on computers with 8 GB RAM or less. 2 is a good choice for 16 GB+."))
        logs = QPushButton("Open log folder")
        logs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir))))
        form.addRow(logs)
        form.addRow(hint(f"{APP_NAME} {APP_VERSION} · LibRaw {libraw_version()}\n"
                         "All processing happens locally on this computer. No photos or metadata are uploaded."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class MainWindow(QMainWindow):
    def __init__(self, log_dir: Path) -> None:
        super().__init__()
        self.log_dir = log_dir
        self.app_settings = AppSettings()
        self.settings = self.app_settings.load()
        self.jobs: list[ConversionJob] = []
        self.items: list[QTreeWidgetItem] = []
        self.keys: set[str] = set()
        self.thread: Optional[QThread] = None
        self.worker: Optional[ConversionWorker] = None
        self.thumb_pool = QThreadPool(self)
        self.thumb_pool.setMaxThreadCount(max(1, min(4, (os.cpu_count() or 2) // 2)))
        self.thumb_signals = ThumbnailSignals()
        self.thumb_signals.loaded.connect(self._on_thumbnail)
        self.counts = {"done": 0, "failed": 0, "skipped": 0, "cancelled": 0, "total": 0}

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1000, 640)
        self.resize(1280, 800)
        self.setAcceptDrops(True)
        self._build_ui()
        self._apply_settings_to_ui()
        self._refresh()

    # ------------------------------------------------------------------ UI construction
    def _build_ui(self) -> None:
        root = QWidget(objectName="root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_top_bar())
        middle = QHBoxLayout()
        middle.setSpacing(0)
        middle.addWidget(self._build_side_panel())
        middle.addWidget(self._build_main_panel(), 1)
        outer.addLayout(middle, 1)
        outer.addWidget(self._build_bottom_bar())
        self.setCentralWidget(root)
        QShortcut(QKeySequence.StandardKey.Delete, self.tree, self.remove_selected)
        QShortcut(QKeySequence("Ctrl+O"), self, self.add_photos)
        QShortcut(QKeySequence("Ctrl+Shift+O"), self, self.add_folder)
        QShortcut(QKeySequence("Ctrl+Return"), self, self.start_conversion)

    def _build_top_bar(self) -> QWidget:
        bar = QWidget(objectName="topBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 10, 18, 10)
        icon = QLabel()
        icon.setPixmap(self.windowIcon().pixmap(26, 26))
        title = QLabel(APP_NAME, objectName="title")
        ver = QLabel(f"v{APP_VERSION}", objectName="version")
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.open_preferences)
        lay.addWidget(icon)
        lay.addWidget(title)
        lay.addWidget(ver)
        lay.addStretch(1)
        lay.addWidget(settings_btn)
        return bar

    def _build_side_panel(self) -> QWidget:
        panel = QWidget(objectName="sidePanel")
        panel.setFixedWidth(330)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(16, 14, 20, 14)
        lay.setSpacing(8)

        self.add_photos_btn = QPushButton("Add Photos…", objectName="primary")
        self.add_photos_btn.setToolTip("Select one or many .ARW files (Ctrl+O). Use Ctrl/Shift to multi-select.")
        self.add_photos_btn.clicked.connect(self.add_photos)
        self.add_folder_btn = QPushButton("Add Folder…")
        self.add_folder_btn.setToolTip("Add every .ARW file in a folder (Ctrl+Shift+O)")
        self.add_folder_btn.clicked.connect(self.add_folder)
        lay.addWidget(self.add_photos_btn)
        lay.addWidget(self.add_folder_btn)

        # Output
        lay.addWidget(section("Output folder"))
        row = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setAccessibleName("Output folder")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.choose_output)
        row.addWidget(self.out_edit, 1)
        row.addWidget(browse)
        lay.addLayout(row)
        self.preserve_cb = QCheckBox("Keep original subfolder structure")
        lay.addWidget(self.preserve_cb)
        form = QFormLayout()
        self.prefix_edit = QLineEdit(placeholderText="optional")
        self.suffix_edit = QLineEdit(placeholderText="optional")
        self.collision_combo = QComboBox()
        for label, pol in (("Skip (keep existing file)", CollisionPolicy.SKIP),
                           ("Save with a new name (_1, _2…)", CollisionPolicy.UNIQUE),
                           ("Ask me before overwriting", CollisionPolicy.ASK),
                           ("Overwrite existing files", CollisionPolicy.OVERWRITE)):
            self.collision_combo.addItem(label, pol.value)
        form.addRow("Prefix", self.prefix_edit)
        form.addRow("Suffix", self.suffix_edit)
        form.addRow("If file exists", self.collision_combo)
        lay.addLayout(form)
        lay.addWidget(hint("Original .ARW files are never modified, moved or deleted."))

        # JPEG
        lay.addWidget(section("JPEG quality"))
        qrow = QHBoxLayout()
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setAccessibleName("JPEG quality")
        self.quality_label = QLabel("95")
        self.quality_label.setMinimumWidth(28)
        self.quality_slider.valueChanged.connect(lambda v: self.quality_label.setText(str(v)))
        qrow.addWidget(self.quality_slider, 1)
        qrow.addWidget(self.quality_label)
        lay.addLayout(qrow)
        lay.addWidget(hint("Quality controls compression and file size only. It cannot recover detail "
                           "lost during RAW development. 90–95 is visually lossless for most photos."))
        form = QFormLayout()
        self.subsampling_combo = QComboBox()
        self.subsampling_combo.addItem("4:4:4 (best colour detail)", "4:4:4")
        self.subsampling_combo.addItem("4:2:2", "4:2:2")
        self.subsampling_combo.addItem("4:2:0 (smallest files)", "4:2:0")
        form.addRow("Chroma", self.subsampling_combo)
        lay.addLayout(form)
        self.metadata_cb = QCheckBox("Copy camera metadata (EXIF)")
        self.icc_cb = QCheckBox("Embed sRGB colour profile")
        lay.addWidget(self.metadata_cb)
        lay.addWidget(self.icc_cb)

        # Resize
        lay.addWidget(section("Size"))
        self.resize_combo = QComboBox()
        self.resize_combo.addItem("Original resolution", ResizeMode.ORIGINAL.value)
        self.resize_combo.addItem("Scale by percentage", ResizeMode.PERCENT.value)
        self.resize_combo.addItem("Fit within width × height", ResizeMode.MAX_DIMENSIONS.value)
        lay.addWidget(self.resize_combo)
        self.percent_spin = QSpinBox(suffix=" %")
        self.percent_spin.setRange(1, 100)
        self.maxw_spin = QSpinBox(suffix=" px")
        self.maxh_spin = QSpinBox(suffix=" px")
        for s in (self.maxw_spin, self.maxh_spin):
            s.setRange(16, 20000)
        self.percent_row = QWidget()
        pr = QHBoxLayout(self.percent_row)
        pr.setContentsMargins(0, 0, 0, 0)
        pr.addWidget(QLabel("Scale"))
        pr.addWidget(self.percent_spin, 1)
        self.max_row = QWidget()
        mr = QHBoxLayout(self.max_row)
        mr.setContentsMargins(0, 0, 0, 0)
        mr.addWidget(self.maxw_spin, 1)
        mr.addWidget(QLabel("×"))
        mr.addWidget(self.maxh_spin, 1)
        lay.addWidget(self.percent_row)
        lay.addWidget(self.max_row)
        self.expected_label = hint("")
        lay.addWidget(self.expected_label)
        self.resize_combo.currentIndexChanged.connect(self._update_resize_ui)
        for s in (self.percent_spin, self.maxw_spin, self.maxh_spin):
            s.valueChanged.connect(self._update_resize_ui)

        # RAW development
        group = QGroupBox("RAW development")
        gform = QFormLayout(group)
        self.wb_combo = QComboBox()
        self.wb_combo.addItem("As shot (camera)", WhiteBalance.CAMERA.value)
        self.wb_combo.addItem("Automatic", WhiteBalance.AUTO.value)
        self.wb_combo.addItem("Daylight (neutral)", WhiteBalance.DAYLIGHT.value)
        self.exposure_spin = QDoubleSpinBox(suffix=" EV")
        self.exposure_spin.setRange(-2.0, 3.0)
        self.exposure_spin.setSingleStep(0.25)
        self.highlight_combo = QComboBox()
        self.highlight_combo.addItem("Clip", HighlightMode.CLIP.value)
        self.highlight_combo.addItem("Blend (soft recovery)", HighlightMode.BLEND.value)
        self.autobright_cb = QCheckBox("Auto brightness")
        self.sharpen_spin = QSpinBox()
        self.sharpen_spin.setRange(0, 100)
        self.sharpen_spin.setSpecialValueText("Off")
        gform.addRow("White balance", self.wb_combo)
        gform.addRow("Exposure", self.exposure_spin)
        gform.addRow("Highlights", self.highlight_combo)
        gform.addRow("Sharpening", self.sharpen_spin)
        gform.addRow(self.autobright_cb)
        gform.addRow(hint("Rendered with LibRaw. Colours may differ slightly from Sony Imaging Edge "
                          "or the camera's own JPEGs."))
        lay.addWidget(group)
        lay.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        return panel

    def _build_main_panel(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 14, 16, 10)
        head = QHBoxLayout()
        self.count_label = QLabel(objectName="muted")
        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.clicked.connect(self.remove_selected)
        self.clear_btn = QPushButton("Clear Queue")
        self.clear_btn.clicked.connect(self.clear_queue)
        head.addWidget(self.count_label)
        head.addStretch(1)
        head.addWidget(self.remove_btn)
        head.addWidget(self.clear_btn)
        lay.addLayout(head)

        self.stack = QStackedWidget()
        self.drop_zone = DropZone()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File", "Size", "Dimensions", "Status", "Output", "Details"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setIconSize(QSize(48, 32))
        hdr = self.tree.header()
        hdr.setSectionResizeMode(COL_FILE, QHeaderView.ResizeMode.Interactive)
        hdr.resizeSection(COL_FILE, 260)
        for c in (COL_SIZE, COL_DIMS, COL_STATUS):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        hdr.resizeSection(COL_OUTPUT, 200)
        hdr.setStretchLastSection(True)
        self.tree.itemSelectionChanged.connect(self._refresh)
        self.stack.addWidget(self.drop_zone)
        self.stack.addWidget(self.tree)
        lay.addWidget(self.stack, 1)
        return panel

    def _build_bottom_bar(self) -> QWidget:
        bar = QWidget(objectName="bottomBar")
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(18, 10, 18, 12)
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        lay.addWidget(self.progress)
        row = QHBoxLayout()
        self.current_label = QLabel("Ready", objectName="muted")
        self.stats_label = QLabel(objectName="muted")
        self.open_out_btn = QPushButton("Open Output Folder")
        self.open_out_btn.clicked.connect(self.open_output_folder)
        self.cancel_btn = QPushButton("Cancel", objectName="danger")
        self.cancel_btn.clicked.connect(self.cancel_conversion)
        self.convert_btn = QPushButton("Convert to JPG", objectName="primary")
        self.convert_btn.clicked.connect(self.start_conversion)
        row.addWidget(self.current_label, 1)
        row.addWidget(self.stats_label)
        row.addSpacing(16)
        row.addWidget(self.open_out_btn)
        row.addWidget(self.cancel_btn)
        row.addWidget(self.convert_btn)
        lay.addLayout(row)
        return bar

    # ------------------------------------------------------------------ settings <-> UI
    @staticmethod
    def _select_data(combo: QComboBox, value) -> None:
        idx = combo.findData(getattr(value, "value", value))
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _apply_settings_to_ui(self) -> None:
        s = self.settings
        self.out_edit.setText(str(s.output.output_dir))
        self.preserve_cb.setChecked(s.output.preserve_structure)
        self.prefix_edit.setText(s.output.prefix)
        self.suffix_edit.setText(s.output.suffix)
        self._select_data(self.collision_combo, s.output.collision)
        self.quality_slider.setValue(s.jpeg.quality)
        self._select_data(self.subsampling_combo, s.jpeg.subsampling)
        self.metadata_cb.setChecked(s.jpeg.preserve_metadata)
        self.icc_cb.setChecked(s.jpeg.embed_srgb_profile)
        self._select_data(self.resize_combo, s.resize.mode)
        self.percent_spin.setValue(s.resize.percent)
        self.maxw_spin.setValue(s.resize.max_width)
        self.maxh_spin.setValue(s.resize.max_height)
        self._select_data(self.wb_combo, s.raw.white_balance)
        self.exposure_spin.setValue(s.raw.exposure_ev)
        self._select_data(self.highlight_combo, s.raw.highlight_mode)
        self.autobright_cb.setChecked(s.raw.auto_brightness)
        self.sharpen_spin.setValue(s.raw.sharpen)
        self._update_resize_ui()

    def _collect_settings(self) -> ConversionSettings:
        s = self.settings
        s.output.output_dir = Path(self.out_edit.text().strip())
        s.output.preserve_structure = self.preserve_cb.isChecked()
        s.output.prefix = self.prefix_edit.text().strip()
        s.output.suffix = self.suffix_edit.text().strip()
        s.output.collision = CollisionPolicy(self.collision_combo.currentData())
        s.jpeg.quality = self.quality_slider.value()
        s.jpeg.subsampling = self.subsampling_combo.currentData()
        s.jpeg.preserve_metadata = self.metadata_cb.isChecked()
        s.jpeg.embed_srgb_profile = self.icc_cb.isChecked()
        s.resize.mode = ResizeMode(self.resize_combo.currentData())
        s.resize.percent = self.percent_spin.value()
        s.resize.max_width = self.maxw_spin.value()
        s.resize.max_height = self.maxh_spin.value()
        s.raw.white_balance = WhiteBalance(self.wb_combo.currentData())
        s.raw.exposure_ev = self.exposure_spin.value()
        s.raw.highlight_mode = HighlightMode(self.highlight_combo.currentData())
        s.raw.auto_brightness = self.autobright_cb.isChecked()
        s.raw.sharpen = self.sharpen_spin.value()
        return s

    def _update_resize_ui(self) -> None:
        mode = ResizeMode(self.resize_combo.currentData())
        self.percent_row.setVisible(mode == ResizeMode.PERCENT)
        self.max_row.setVisible(mode == ResizeMode.MAX_DIMENSIONS)
        sample = next((j for j in self.jobs if j.width and j.height), None)
        if sample is None:
            self.expected_label.setText("Aspect ratio is always preserved; images are never enlarged.")
            return
        rs = self._collect_settings().resize
        w, h = compute_output_size(sample.width, sample.height, rs)
        self.expected_label.setText(f"Example: {sample.width}×{sample.height} → {w}×{h} px "
                                    "(aspect ratio preserved, never enlarged)")

    # ------------------------------------------------------------------ queue management
    @property
    def busy(self) -> bool:
        return self.thread is not None

    def add_photos(self) -> None:
        if self.busy:
            return
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add Sony RAW photos", self.app_settings.last_input_dir(),
            "Sony RAW (*.arw *.ARW);;All files (*)")
        if files:
            self.app_settings.set_last_input_dir(str(Path(files[0]).parent))
            self.add_paths([Path(f) for f in files])

    def add_folder(self) -> None:
        if self.busy:
            return
        folder = QFileDialog.getExistingDirectory(self, "Add folder of .ARW photos",
                                                  self.app_settings.last_input_dir())
        if folder:
            self.app_settings.set_last_input_dir(folder)
            self.add_paths([Path(folder)])

    def add_paths(self, paths: list[Path]) -> None:
        recursive = self.app_settings.recursive_scan()
        files: list[Path] = []
        ignored = 0
        for p in paths:
            if p.is_dir():
                try:
                    files.extend(scan_folder(p, recursive))
                except OSError as exc:
                    QMessageBox.warning(self, "Cannot read folder", f"{p}\n\n{exc}")
            elif is_supported(p):
                files.append(p)
            else:
                ignored += 1
        before = len(self.jobs)
        new = list(unique_new_paths(files, self.keys))
        self.tree.setUpdatesEnabled(False)
        for f in new:
            self._append_job(ConversionJob(f))
        self.tree.setUpdatesEnabled(True)
        dupes = len(files) - len(new)
        msgs = [f"Added {len(self.jobs) - before} photo(s)."]
        if dupes:
            msgs.append(f"{dupes} already in the queue.")
        if ignored:
            msgs.append(f"{ignored} unsupported file(s) ignored (only .ARW).")
        if not files and any(p.is_dir() for p in paths):
            msgs = ["No .ARW files found in that folder" +
                    ("" if recursive else " (subfolders are off; enable them in Settings)") + "."]
        self.current_label.setText(" ".join(msgs))
        self._refresh()

    def _append_job(self, job: ConversionJob) -> None:
        item = QTreeWidgetItem([job.source.name, human_size(job.size_bytes), "…", job.status.value, "", ""])
        item.setToolTip(COL_FILE, str(job.source))
        item.setData(COL_FILE, Qt.ItemDataRole.UserRole, dedupe_key(job.source))
        self._paint_status(item, job.status)
        self.jobs.append(job)
        self.items.append(item)
        self.tree.addTopLevelItem(item)
        self.thumb_pool.start(ThumbnailTask(dedupe_key(job.source), job.source, self.thumb_signals))

    def _on_thumbnail(self, key: str, qimg, w: int, h: int) -> None:
        for job, item in zip(self.jobs, self.items):
            if item.data(COL_FILE, Qt.ItemDataRole.UserRole) == key:
                if w and h:
                    job.width, job.height = w, h
                    item.setText(COL_DIMS, f"{w} × {h}")
                else:
                    item.setText(COL_DIMS, "unknown")
                if qimg is not None:
                    item.setIcon(COL_FILE, QIcon(QPixmap.fromImage(qimg)))
                break
        self._update_resize_ui()

    def remove_selected(self) -> None:
        if self.busy:
            return
        rows = sorted((self.tree.indexOfTopLevelItem(i) for i in self.tree.selectedItems()), reverse=True)
        for r in rows:
            self.keys.discard(dedupe_key(self.jobs[r].source))
            self.tree.takeTopLevelItem(r)
            del self.jobs[r]
            del self.items[r]
        self._refresh()

    def clear_queue(self) -> None:
        if self.busy or not self.jobs:
            return
        self.tree.clear()
        self.jobs.clear()
        self.items.clear()
        self.keys.clear()
        self.progress.setValue(0)
        self.current_label.setText("Queue cleared")
        self._refresh()

    def _paint_status(self, item: QTreeWidgetItem, status: JobStatus) -> None:
        item.setText(COL_STATUS, status.value)
        item.setForeground(COL_STATUS, QColor(STATUS_COLORS.get(status.value, "#e6e6e6")))

    def _refresh(self) -> None:
        n = len(self.jobs)
        self.stack.setCurrentIndex(1 if n else 0)
        total = sum(j.size_bytes for j in self.jobs) if n < 5000 else 0
        self.count_label.setText(f"{n} photo{'s' if n != 1 else ''} · {human_size(total)}" if n
                                 else "No photos in the queue")
        busy = self.busy
        for w in (self.add_photos_btn, self.add_folder_btn, self.clear_btn):
            w.setEnabled(not busy)
        self.remove_btn.setEnabled(not busy and bool(self.tree.selectedItems()))
        self.convert_btn.setEnabled(not busy and any(j.status != JobStatus.COMPLETED for j in self.jobs))
        self.cancel_btn.setEnabled(busy)
        c = self.counts
        remaining = max(0, c["total"] - c["done"] - c["failed"] - c["skipped"] - c["cancelled"])
        self.stats_label.setText(f"Completed {c['done']}  ·  Failed {c['failed']}  ·  "
                                 f"Skipped {c['skipped']}  ·  Remaining {remaining}")

    # ------------------------------------------------------------------ drag & drop
    def dragEnterEvent(self, event) -> None:
        if not self.busy and event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_zone.set_active(True)

    def dragLeaveEvent(self, event) -> None:
        self.drop_zone.set_active(False)

    def dropEvent(self, event) -> None:
        self.drop_zone.set_active(False)
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.add_paths(paths)
            event.acceptProposedAction()

    # ------------------------------------------------------------------ output folder
    def choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose output folder", self.out_edit.text())
        if folder:
            self.out_edit.setText(str(Path(folder)))

    def open_output_folder(self) -> None:
        folder = Path(self.out_edit.text().strip())
        if not folder.is_dir():
            if QMessageBox.question(self, "Folder does not exist",
                                    f"{folder}\n\ndoes not exist yet. Create it now?") != QMessageBox.StandardButton.Yes:
                return
            try:
                ensure_writable_dir(folder)
            except OutputError as exc:
                QMessageBox.warning(self, "Cannot create folder", str(exc))
                return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def open_preferences(self) -> None:
        dlg = PreferencesDialog(self, self.settings, self.app_settings.recursive_scan(), self.log_dir)
        if dlg.exec():
            self.app_settings.set_recursive_scan(dlg.recursive.isChecked())
            self.settings.max_workers = dlg.workers.value()
            self.app_settings.save(self._collect_settings())

    # ------------------------------------------------------------------ conversion
    def _resolve_ask_policy(self, settings: ConversionSettings, rows: list[int]) -> Optional[CollisionPolicy]:
        planner = OutputPlanner(settings.output, [self.jobs[r].source for r in rows])
        conflicts = [r for r in rows if planner.desired_path(self.jobs[r].source).exists()]
        if not conflicts:
            return CollisionPolicy.SKIP
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Files already exist")
        names = "\n".join(planner.desired_path(self.jobs[r].source).name for r in conflicts[:8])
        more = f"\n… and {len(conflicts) - 8} more" if len(conflicts) > 8 else ""
        box.setText(f"{len(conflicts)} output file(s) already exist in the destination folder:\n\n{names}{more}")
        overwrite = box.addButton("Overwrite", QMessageBox.ButtonRole.DestructiveRole)
        rename = box.addButton("Keep both (rename)", QMessageBox.ButtonRole.AcceptRole)
        skip = box.addButton("Skip these", QMessageBox.ButtonRole.RejectRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(skip)
        box.exec()
        clicked = box.clickedButton()
        if clicked == overwrite:
            return CollisionPolicy.OVERWRITE
        if clicked == rename:
            return CollisionPolicy.UNIQUE
        if clicked == skip:
            return CollisionPolicy.SKIP
        return None

    def start_conversion(self) -> None:
        if self.busy:
            return
        rows = [i for i, j in enumerate(self.jobs) if j.status != JobStatus.COMPLETED]
        if not rows:
            QMessageBox.information(self, APP_NAME, "Add some .ARW photos first.")
            return
        out_text = self.out_edit.text().strip()
        if not out_text:
            QMessageBox.warning(self, "No output folder", "Please choose an output folder.")
            return
        settings = self._collect_settings()
        try:
            ensure_writable_dir(settings.output.output_dir)
        except OutputError as exc:
            QMessageBox.warning(self, "Output folder problem", f"{settings.output.output_dir}\n\n{exc}")
            return
        try:
            free = free_space_bytes(settings.output.output_dir)
            if free < len(rows) * EST_BYTES_PER_OUTPUT * 0.25:
                if QMessageBox.question(
                        self, "Low disk space",
                        f"Only {human_size(free)} is free on the destination drive. "
                        "The conversion may run out of space. Continue anyway?") != QMessageBox.StandardButton.Yes:
                    return
        except OSError:
            pass

        override = None
        if settings.output.collision == CollisionPolicy.ASK:
            override = self._resolve_ask_policy(settings, rows)
            if override is None:
                return
        self.app_settings.save(settings)

        jobs = []
        for r in rows:
            job = self.jobs[r]
            job.status, job.error, job.output_path = JobStatus.PENDING, None, None
            job.collision_override = override
            self._paint_status(self.items[r], JobStatus.PENDING)
            self.items[r].setText(COL_OUTPUT, "")
            self.items[r].setText(COL_ERROR, "")
            jobs.append(job)
        self.counts = {"done": 0, "failed": 0, "skipped": 0, "cancelled": 0, "total": len(jobs)}
        self.progress.setRange(0, len(jobs))
        self.progress.setValue(0)

        self.thread = QThread(self)
        self.worker = ConversionWorker(jobs, settings, rows)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.job_started.connect(self._on_job_started)
        self.worker.job_finished.connect(self._on_job_finished)
        self.worker.error.connect(lambda msg: QMessageBox.critical(self, "Conversion stopped", msg))
        self.worker.finished.connect(self._on_batch_finished)
        log.info("Batch started: %d files, quality %d, resize %s", len(jobs), settings.jpeg.quality,
                 settings.resize.mode.value)
        self.thread.start()
        self._refresh()

    def cancel_conversion(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.current_label.setText("Cancelling… finishing the current file")

    def _on_job_started(self, row: int, name: str) -> None:
        self.current_label.setText(f"Converting {name}")
        self._paint_status(self.items[row], JobStatus.PROCESSING)
        self.tree.scrollToItem(self.items[row])

    def _on_job_finished(self, row: int, snapshot: ConversionJob) -> None:
        job, item = self.jobs[row], self.items[row]
        job.status, job.error, job.output_path = snapshot.status, snapshot.error, snapshot.output_path
        self._paint_status(item, job.status)
        if job.output_path:
            item.setText(COL_OUTPUT, job.output_path.name)
            item.setToolTip(COL_OUTPUT, str(job.output_path))
        item.setText(COL_ERROR, job.error or "")
        item.setToolTip(COL_ERROR, job.error or "")
        key = {JobStatus.COMPLETED: "done", JobStatus.FAILED: "failed",
               JobStatus.SKIPPED: "skipped", JobStatus.CANCELLED: "cancelled"}.get(job.status)
        if key:
            self.counts[key] += 1
        c = self.counts
        self.progress.setValue(c["done"] + c["failed"] + c["skipped"] + c["cancelled"])
        self._refresh()

    def _on_batch_finished(self, summary) -> None:
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread.deleteLater()
        if self.worker:
            self.worker.deleteLater()
        self.thread = None
        self.worker = None
        msg = (f"Finished: {summary.completed} converted, {summary.failed} failed, "
               f"{summary.skipped} skipped, {summary.cancelled} cancelled.")
        self.current_label.setText(msg)
        log.info(msg)
        self._refresh()
        if summary.failed:
            details = "\n".join(f"• {p.name}: {e}" for p, e in summary.errors[:10])
            QMessageBox.warning(self, "Some files failed", f"{msg}\n\n{details}")

    # ------------------------------------------------------------------ lifecycle
    def closeEvent(self, event) -> None:
        if self.busy:
            if QMessageBox.question(self, "Conversion in progress",
                                    "A conversion is running. Cancel it and quit?") != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.thread.quit()
            self.thread.wait(60000)
        try:
            self.app_settings.save(self._collect_settings())
        except Exception:  # never block closing
            log.exception("Saving settings failed")
        self.thumb_pool.clear()
        self.thumb_pool.waitForDone(3000)
        event.accept()
