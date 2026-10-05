"""Linear and Raycast inspired Geek Dark Theme Stylesheet for NCM Tag Extractor."""
from __future__ import annotations

from pathlib import Path

# Resolve path to check.svg icon for crisp checkmarks
CHECK_SVG_PATH = (Path(__file__).resolve().parent / "check.svg").as_posix()

DARK_THEME_QSS = f"""
/* ================= Base Canvas ================= */
QMainWindow, QDialog {{
    background-color: #090a0f;
    color: #e2e4e9;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}}

QWidget {{
    color: #e2e4e9;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
}}

/* ================= Geek Flat Cards ================= */
QFrame#cardFrame {{
    background-color: #111218;
    border: 1px solid #1e202a;
    border-radius: 8px;
    padding: 12px;
}}

QLabel#sectionTitle {{
    color: #8b8ea4;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
    text-transform: uppercase;
}}

/* ================= Buttons ================= */
QPushButton {{
    background-color: #171822;
    color: #d1d5db;
    border: 1px solid #262836;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 500;
    min-height: 20px;
}}

QPushButton:hover {{
    background-color: #212230;
    border-color: #3b3e52;
    color: #ffffff;
}}

QPushButton:pressed {{
    background-color: #12131b;
}}

QPushButton:disabled {{
    background-color: #101116;
    color: #4b5063;
    border-color: #191b24;
}}

/* Linear Accent Primary CTA */
QPushButton#primaryButton {{
    background-color: #5e6ad2;
    color: #ffffff;
    border: 1px solid #6f7be8;
    font-weight: 600;
    font-size: 13px;
    padding: 6px 18px;
    min-height: 22px;
    border-radius: 6px;
}}

QPushButton#primaryButton:hover {{
    background-color: #6b77e2;
    border-color: #8591f5;
}}

QPushButton#primaryButton:pressed {{
    background-color: #4e59ba;
}}

QPushButton#primaryButton:disabled {{
    background-color: #262947;
    color: #5b6294;
    border-color: #323659;
}}

/* Danger / Stop Button */
QPushButton#dangerButton {{
    background-color: #231215;
    color: #f87171;
    border: 1px solid #451b22;
}}

QPushButton#dangerButton:hover {{
    background-color: #35161c;
    border-color: #ef4444;
    color: #fca5a5;
}}

QPushButton#dangerButton:pressed {{
    background-color: #180d10;
}}

/* Warning Pill Button */
QPushButton#warningButton {{
    background-color: #241a10;
    color: #fbbf24;
    border: 1px solid #4d3319;
}}

QPushButton#warningButton:hover {{
    background-color: #362414;
    border-color: #f59e0b;
}}

/* Filter Tag Buttons (Toggle) */
QPushButton#filterPill {{
    background-color: #151620;
    color: #9496a8;
    border: 1px solid #232533;
    border-radius: 12px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 500;
}}

QPushButton#filterPill:hover {{
    background-color: #1d1e2c;
    color: #e2e4e9;
    border-color: #33364a;
}}

QPushButton#filterPill:checked {{
    background-color: #232742;
    color: #a5b4fc;
    border: 1px solid #5e6ad2;
    font-weight: 600;
}}

/* ================= Input Fields & Selectors ================= */
QLineEdit, QDateTimeEdit, QDateEdit, QTimeEdit, QSpinBox, QComboBox {{
    background-color: #0d0e14;
    color: #e2e4e9;
    border: 1px solid #1f212c;
    border-radius: 6px;
    padding: 4px 6px;
    selection-background-color: #5e6ad2;
    selection-color: #ffffff;
    min-height: 18px;
    font-size: 12px;
}}

QLineEdit:focus, QDateTimeEdit:focus, QDateEdit:focus, QTimeEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid #5e6ad2;
    background-color: #101119;
}}


QDateEdit::drop-down, QDateTimeEdit::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #1f212c;
}}

QDateEdit::up-button, QTimeEdit::up-button,
QDateEdit::down-button, QTimeEdit::down-button {{
    subcontrol-origin: border;
    width: 16px;
    background: #151620;
    border-left: 1px solid #1f212c;
}}

QDateEdit::up-button:hover, QTimeEdit::up-button:hover,
QDateEdit::down-button:hover, QTimeEdit::down-button:hover {{
    background: #232536;
}}



QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border-left-width: 0px;
}}

QComboBox QAbstractItemView {{
    background-color: #111218;
    border: 1px solid #262836;
    color: #e2e4e9;
    selection-background-color: #5e6ad2;
    selection-color: #ffffff;
    padding: 4px;
    outline: none;
}}

/* ================= Checkboxes (with Crisp Checkmark) ================= */
QCheckBox {{
    spacing: 8px;
    color: #c9cdd6;
    font-size: 12px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid #333648;
    border-radius: 4px;
    background-color: #0d0e14;
}}

QCheckBox::indicator:hover {{
    border-color: #5e6ad2;
    background-color: #13141f;
}}

QCheckBox::indicator:unchecked {{
    background-color: #0d0e14;
    border: 1px solid #333648;
    image: none;
}}

QCheckBox::indicator:checked {{
    background-color: #5e6ad2;
    border-color: #5e6ad2;
    image: url({CHECK_SVG_PATH});
}}

QCheckBox::indicator:checked:hover {{
    background-color: #6f7be8;
    border-color: #6f7be8;
    image: url({CHECK_SVG_PATH});
}}

/* ================= Progress Bar ================= */
QProgressBar {{
    background-color: #12131b;
    border: 1px solid #1c1e28;
    border-radius: 4px;
    text-align: center;
    color: #ffffff;
    font-weight: 600;
    font-size: 10px;
    min-height: 8px;
    max-height: 8px;
}}

QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5e6ad2, stop:1 #22c55e);
    border-radius: 3px;
}}

/* ================= Tables & Lists ================= */
QTableWidget, QListWidget {{
    background-color: #0d0e14;
    border: 1px solid #1a1c26;
    border-radius: 6px;
    gridline-color: #1a1c28;
    color: #e2e4e9;
    selection-background-color: #1e2238;
    selection-color: #ffffff;
    outline: none;
    font-size: 12px;
}}

QTableWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid #14151e;
}}

QTableWidget::item:selected {{
    background-color: #1c2035;
    color: #ffffff;
}}

QHeaderView::section {{
    background-color: #111218;
    color: #8b8ea4;
    font-weight: 600;
    font-size: 12px;
    padding: 6px 8px;
    border-top: none;
    border-left: none;
    border-right: 1px solid #232536;
    border-bottom: 1px solid #232536;
}}

QHeaderView::section:last {{
    border-right: none;
}}

/* ================= Scrollbars ================= */
QScrollBar:vertical {{
    background: #090a0f;
    width: 6px;
    margin: 0;
    border-radius: 3px;
}}

QScrollBar::handle:vertical {{
    background: #232533;
    min-height: 20px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical:hover {{
    background: #5e6ad2;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    height: 0px;
}}

QScrollBar:horizontal {{
    background: #090a0f;
    height: 6px;
    margin: 0;
    border-radius: 3px;
}}

QScrollBar::handle:horizontal {{
    background: #232533;
    min-width: 20px;
    border-radius: 3px;
}}

QScrollBar::handle:horizontal:hover {{
    background: #5e6ad2;
}}

/* ================= Plain Text / Log Console ================= */
QPlainTextEdit {{
    background-color: #0b0c10;
    color: #c9cdd6;
    border: 1px solid #191b24;
    border-radius: 6px;
    font-family: "Cascadia Code", "Fira Code", Consolas, Monaco, monospace;
    font-size: 11px;
    padding: 6px;
}}

/* ================= Badges & Micro Status Pills ================= */
QLabel#badgeSuccess {{
    background-color: #0d281a;
    color: #4ade80;
    border: 1px solid #165333;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 10px;
    font-weight: 600;
}}

QLabel#badgeFailed {{
    background-color: #2b1115;
    color: #f87171;
    border: 1px solid #541d24;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 10px;
    font-weight: 600;
}}

QLabel#badgePending {{
    background-color: #171822;
    color: #9496a8;
    border: 1px solid #282a3b;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 10px;
    font-weight: 600;
}}

/* Audio Format Pills */
QLabel#pillNcm {{
    background-color: #211938;
    color: #c4b5fd;
    border: 1px solid #372961;
    border-radius: 4px;
    padding: 1px 5px;
    font-size: 10px;
    font-weight: 600;
}}

QLabel#pillFlac {{
    background-color: #132438;
    color: #7dd3fc;
    border: 1px solid #1c3c60;
    border-radius: 4px;
    padding: 1px 5px;
    font-size: 10px;
    font-weight: 600;
}}

QLabel#pillMp3 {{
    background-color: #132b1f;
    color: #6ee7b7;
    border: 1px solid #194a32;
    border-radius: 4px;
    padding: 1px 5px;
    font-size: 10px;
    font-weight: 600;
}}

/* Unified Drop & Path List Frame */
QFrame#pathListCard {{
    background-color: #0d0e14;
    border: 1px dashed #242738;
    border-radius: 6px;
}}

QFrame#pathListCard:hover {{
    border-color: #5e6ad2;
}}
"""
