"""Dark charcoal theme with a restrained blue accent."""

ACCENT = "#3d8bfd"

STYLESHEET = f"""
* {{ font-family: "Segoe UI", "Inter", sans-serif; font-size: 10pt; color: #e6e6e6; }}
QMainWindow, QWidget#root {{ background: #1e1f22; }}
QWidget#sidePanel {{ background: #26272b; border-right: 1px solid #34363b; }}
QWidget#topBar, QWidget#bottomBar {{ background: #232428; }}
QWidget#topBar {{ border-bottom: 1px solid #34363b; }}
QWidget#bottomBar {{ border-top: 1px solid #34363b; }}
QLabel#title {{ font-size: 14pt; font-weight: 600; }}
QLabel#version, QLabel#muted, QLabel#hint {{ color: #9aa0a6; }}
QLabel#hint {{ font-size: 9pt; }}
QLabel#sectionTitle {{ color: #9aa0a6; font-size: 8.5pt; font-weight: 600; letter-spacing: 1px; margin-top: 8px; }}
QPushButton {{ background: #34363b; border: 1px solid #45474d; border-radius: 6px; padding: 7px 14px; }}
QPushButton:hover {{ background: #3c3e44; border-color: #55585f; }}
QPushButton:pressed {{ background: #2c2e32; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #6b6e74; background: #2a2b2f; border-color: #34363b; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: white; font-weight: 600; padding: 9px 22px; }}
QPushButton#primary:hover {{ background: #5a9dfd; }}
QPushButton#primary:disabled {{ background: #2f4a73; border-color: #2f4a73; color: #a9b8cc; }}
QPushButton#danger:enabled {{ border-color: #a8473f; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: #1b1c1f; border: 1px solid #3a3c41; border-radius: 5px; padding: 5px 7px; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: #26272b; selection-background-color: {ACCENT}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid #5a5d63; border-radius: 3px; background: #1b1c1f; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox::indicator:focus {{ border-color: {ACCENT}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #45474d; border-radius: 4px; min-height: 30px; margin: 2px; }}
QScrollBar::handle:vertical:hover {{ background: #5a5d63; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: #45474d; border-radius: 4px; min-width: 30px; margin: 2px; }}
QSlider::groove:horizontal {{ height: 4px; background: #3a3c41; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #f0f0f0; width: 14px; margin: -6px 0; border-radius: 7px; }}
QSlider::handle:horizontal:focus {{ background: {ACCENT}; }}
QTreeWidget {{ background: #1b1c1f; border: 1px solid #34363b; border-radius: 6px;
    alternate-background-color: #202125; }}
QTreeWidget::item {{ padding: 4px; }}
QTreeWidget::item:selected {{ background: #2d4a73; }}
QHeaderView::section {{ background: #26272b; border: none; border-right: 1px solid #34363b;
    padding: 6px; color: #b5b9be; }}
QProgressBar {{ background: #1b1c1f; border: 1px solid #34363b; border-radius: 5px; height: 14px;
    text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QScrollArea {{ border: none; background: transparent; }}
QGroupBox {{ border: 1px solid #34363b; border-radius: 6px; margin-top: 14px; padding: 10px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #b5b9be; }}
QFrame#dropZone {{ border: 2px dashed #45474d; border-radius: 12px; background: #202125; }}
QFrame#dropZone[active="true"] {{ border-color: {ACCENT}; background: #1f2a3a; }}
QToolTip {{ background: #2c2e32; color: #e6e6e6; border: 1px solid #45474d; }}
"""

STATUS_COLORS = {
    "Pending": "#9aa0a6",
    "Processing": ACCENT,
    "Completed": "#4caf7a",
    "Failed": "#e5534b",
    "Skipped": "#d4a72c",
    "Cancelled": "#9aa0a6",
}
