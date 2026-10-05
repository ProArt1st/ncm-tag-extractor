"""Native OS dialog helper supporting KDE Dolphin (kdialog) and QFileDialog."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QWidget


def is_kde_desktop() -> bool:
    """Check if current session is KDE Plasma with kdialog available."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    return "KDE" in desktop.upper() and bool(shutil.which("kdialog"))


def choose_directory(parent: QWidget | None = None, title: str = "选择文件夹", start_dir: str = "") -> str:
    """Open native directory picker (KDE Dolphin via kdialog, or native QFileDialog)."""
    target_start = start_dir or str(Path.home())

    if is_kde_desktop():
        try:
            cmd = ["kdialog", "--title", title, "--getexistingdirectory", target_start]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                selected = res.stdout.strip()
                if selected:
                    return str(Path(selected).resolve())
            return ""
        except Exception:
            pass

    # Fallback to standard native Qt dialog
    folder = QFileDialog.getExistingDirectory(parent, title, target_start)
    return str(Path(folder).resolve()) if folder else ""


def choose_files(
    parent: QWidget | None = None,
    title: str = "选择音频文件",
    start_dir: str = "",
    file_filter: str = "音频文件 (*.ncm *.flac *.mp3);;所有文件 (*.*)",
) -> list[str]:
    """Open native multi-file picker (KDE Dolphin via kdialog, or native QFileDialog)."""
    target_start = start_dir or str(Path.home())

    if is_kde_desktop():
        try:
            cmd = [
                "kdialog",
                "--title",
                title,
                "--getopenfilename",
                target_start,
                "*.ncm *.flac *.mp3 | 音频文件 (*.ncm *.flac *.mp3)",
                "--multiple",
                "--separate-output",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                lines = [str(Path(line.strip()).resolve()) for line in res.stdout.splitlines() if line.strip()]
                return lines
            return []
        except Exception:
            pass

    # Fallback to standard native Qt dialog
    files, _ = QFileDialog.getOpenFileNames(parent, title, target_start, filter=file_filter)
    return [str(Path(f).resolve()) for f in files] if files else []
