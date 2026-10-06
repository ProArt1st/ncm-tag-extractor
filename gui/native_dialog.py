"""Native OS dialog helper supporting KDE Dolphin, GNOME Nautilus, and QFileDialog."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QWidget


def get_clean_env() -> dict[str, str]:
    """Get clean system environment free of PyInstaller/AppImage LD_LIBRARY_PATH overrides."""
    env = dict(os.environ)
    if "LD_LIBRARY_PATH_ORIG" in env:
        env["LD_LIBRARY_PATH"] = env["LD_LIBRARY_PATH_ORIG"]
    else:
        env.pop("LD_LIBRARY_PATH", None)
    env.pop("QT_PLUGIN_PATH", None)
    env.pop("QML2_IMPORT_PATH", None)
    return env


def is_kde() -> bool:
    """Check if current session is KDE Plasma with kdialog available."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    return "KDE" in desktop and bool(shutil.which("kdialog"))


def is_gnome() -> bool:
    """Check if current session is GNOME/GTK with zenity available."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    return any(name in desktop for name in ("GNOME", "UNITY", "UBUNTU", "CINNAMON")) and bool(shutil.which("zenity"))


def choose_directory(parent: QWidget | None = None, title: str = "选择文件夹", start_dir: str = "") -> str:
    """Open directory picker (KDE Dolphin via kdialog, GNOME Nautilus via zenity, or QFileDialog)."""
    target_start = start_dir or str(Path.home())

    # 1. KDE Dolphin native dialog
    if is_kde():
        try:
            cmd = ["kdialog", "--title", title, "--getexistingdirectory", target_start]
            res = subprocess.run(cmd, env=get_clean_env(), capture_output=True, text=True)
            if res.returncode == 0:
                selected = res.stdout.strip()
                if selected:
                    return str(Path(selected).resolve())
                return ""
            elif res.returncode == 1:
                # User cancelled dialog
                return ""
        except Exception:
            pass

    # 2. GNOME Nautilus native dialog
    if is_gnome():
        try:
            cmd = [
                "zenity",
                "--file-selection",
                "--directory",
                "--title", title,
                f"--filename={target_start}/",
            ]
            res = subprocess.run(cmd, env=get_clean_env(), capture_output=True, text=True)
            if res.returncode == 0:
                selected = res.stdout.strip()
                if selected:
                    return str(Path(selected).resolve())
                return ""
            elif res.returncode == 1:
                # User cancelled dialog
                return ""
        except Exception:
            pass

    # 3. Standard QFileDialog (uses XDG Desktop Portal on Linux, Windows Explorer on Windows)
    try:
        folder = QFileDialog.getExistingDirectory(parent, title, target_start)
        if folder:
            return str(Path(folder).resolve())
    except Exception:
        pass

    # 4. Fallback to Qt built-in dialog if all native options fail
    try:
        folder = QFileDialog.getExistingDirectory(
            parent, title, target_start, QFileDialog.Option.DontUseNativeDialog
        )
        if folder:
            return str(Path(folder).resolve())
    except Exception:
        pass

    return ""


def choose_files(
    parent: QWidget | None = None,
    title: str = "选择音频文件",
    start_dir: str = "",
    file_filter: str = "音频文件 (*.ncm *.flac *.mp3);;所有文件 (*.*)",
) -> list[str]:
    """Open multi-file picker (KDE Dolphin via kdialog, GNOME Nautilus via zenity, or QFileDialog)."""
    target_start = start_dir or str(Path.home())

    # 1. KDE Dolphin native dialog
    if is_kde():
        try:
            cmd = [
                "kdialog",
                "--title", title,
                "--getopenfilename", target_start,
                "*.ncm *.flac *.mp3 | 音频文件 (*.ncm *.flac *.mp3)",
                "--multiple",
                "--separate-output",
            ]
            res = subprocess.run(cmd, env=get_clean_env(), capture_output=True, text=True)
            if res.returncode == 0:
                lines = [str(Path(line.strip()).resolve()) for line in res.stdout.splitlines() if line.strip()]
                return lines
            elif res.returncode == 1:
                return []
        except Exception:
            pass

    # 2. GNOME Nautilus native dialog
    if is_gnome():
        try:
            cmd = [
                "zenity",
                "--file-selection",
                "--multiple",
                "--separator=\n",
                "--title", title,
                f"--filename={target_start}/",
                "--file-filter=音频文件 (*.ncm *.flac *.mp3) | *.ncm *.flac *.mp3",
                "--file-filter=所有文件 (*.*) | *",
            ]
            res = subprocess.run(cmd, env=get_clean_env(), capture_output=True, text=True)
            if res.returncode == 0:
                lines = [str(Path(line.strip()).resolve()) for line in res.stdout.splitlines() if line.strip()]
                return lines
            elif res.returncode == 1:
                return []
        except Exception:
            pass

    # 3. Standard QFileDialog
    try:
        files, _ = QFileDialog.getOpenFileNames(parent, title, target_start, filter=file_filter)
        if files:
            return [str(Path(f).resolve()) for f in files]
    except Exception:
        pass

    # 4. Fallback to Qt built-in dialog
    try:
        files, _ = QFileDialog.getOpenFileNames(
            parent,
            title,
            target_start,
            filter=file_filter,
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if files:
            return [str(Path(f).resolve()) for f in files]
    except Exception:
        pass

    return []
