#!/usr/bin/env python3
"""Desktop application entry point for NCM Tag Extractor."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.config import get_default_config_path
from gui.main_window import MainWindow


def main() -> int:
    # Enable modern Linux desktop portal (native KDE Dolphin / GNOME Nautilus)
    if sys.platform.startswith("linux"):
        import os
        os.environ.setdefault("QT_USE_PORTAL", "1")

    # High DPI & rendering attributes
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("NCMTagExtractor")
    app.setApplicationDisplayName("NCM Tag Extractor")

    config_path = get_default_config_path()
    window = MainWindow(config_path=config_path)

    # If file or folder arguments are passed via command-line, add them
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            p = Path(arg).resolve()
            if p.exists():
                str_p = str(p)
                existing = [window.input_list.item(i).text() for i in range(window.input_list.count())]
                if str_p not in existing:
                    window.input_list.addItem(str_p)
        window._save_ui_to_config()

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
