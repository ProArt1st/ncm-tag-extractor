#!/usr/bin/env python3
"""Cross-platform packaging script for NCM Tag Extractor (Windows .exe & Linux AppImage)."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Force UTF-8 on Windows and non-UTF8 console environments
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"
APP_NAME = "NCMTagExtractor"


def clean_previous_builds() -> None:
    print("[CLEAN] 清理旧的构建产物...")
    for p in [BUILD_DIR, DIST_DIR]:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
    for spec in ROOT_DIR.glob("*.spec"):
        try:
            spec.unlink()
        except OSError:
            pass


def build_pyinstaller_binary() -> Path:
    """Build single binary using PyInstaller."""
    print("[BUILD] 正在使用 PyInstaller 打包应用二进制...")

    system = platform.system()
    pyinstaller_bin = shutil.which("pyinstaller") or (
        str(ROOT_DIR / ".venv" / "bin" / "pyinstaller")
        if (ROOT_DIR / ".venv" / "bin" / "pyinstaller").is_file()
        else "pyinstaller"
    )

    cmd = [
        pyinstaller_bin,
        "--name", APP_NAME,
        "--windowed",  # No console window
        "--onefile",   # Single standalone executable
        "--clean",
        "--collect-all", "mutagen",
        "--collect-all", "Crypto",
        "--collect-all", "httpx",
        "--hidden-import", "core.config",
        "--hidden-import", "core",
        "--hidden-import", "gui",
        "--hidden-import", "PySide6.QtSvg",
        "--collect-binaries", "PySide6.QtSvg",
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.QtWebEngineQuick",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.Qt3DRender",
        "--exclude-module", "PySide6.Qt3DAnimation",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.QtQuick3D",
        "--exclude-module", "PySide6.QtQml",
        "--exclude-module", "PySide6.QtPdf",
        "--exclude-module", "PySide6.QtPdfWidgets",
        "--exclude-module", "PySide6.QtMultimedia",
        "--exclude-module", "PySide6.QtMultimediaWidgets",
        "--exclude-module", "PySide6.QtSpatialAudio",
        "--exclude-module", "PySide6.QtSensors",
        "--exclude-module", "PySide6.QtPositioning",
        "--exclude-module", "PySide6.QtLocation",
        "--exclude-module", "PySide6.QtCharts",
        "--exclude-module", "PySide6.QtDataVisualization",
        "--exclude-module", "PySide6.QtBluetooth",
        "--exclude-module", "PySide6.QtNfc",
        "--exclude-module", "PySide6.QtSerialPort",
        "--exclude-module", "PySide6.QtTextToSpeech",
        "--exclude-module", "PySide6.QtRemoteObjects",
        "--add-data", f"gui/check.svg{os.pathsep}gui",
        "main.py",
    ]

    print("[CMD] 执行命令:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=str(ROOT_DIR))
    if res.returncode != 0:
        print("[ERROR] PyInstaller 打包失败！", file=sys.stderr)
        sys.exit(res.returncode)

    exe_suffix = ".exe" if system == "Windows" else ""
    binary_path = DIST_DIR / f"{APP_NAME}{exe_suffix}"
    if not binary_path.is_file():
        print(f"[ERROR] 未找到生成的二进制文件: {binary_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[SUCCESS] 二进制打包成功: {binary_path} ({binary_path.stat().st_size / (1024*1024):.2f} MB)")
    return binary_path


def create_linux_appdir(binary_path: Path) -> Path:
    """Create Linux AppDir structure for AppImage creation."""
    print("[BUILD] 正在构建 Linux AppDir 结构...")
    appdir = ROOT_DIR / "AppDir"
    if appdir.is_dir():
        shutil.rmtree(appdir, ignore_errors=True)

    usr_bin = appdir / "usr" / "bin"
    usr_bin.mkdir(parents=True, exist_ok=True)
    target_bin = usr_bin / APP_NAME
    shutil.copy2(binary_path, target_bin)
    target_bin.chmod(0o755)

    # 1. Desktop entry
    desktop_content = f"""[Desktop Entry]
Type=Application
Name=NCM Tag Extractor
Comment=NCM 音频解密与元数据提取器
Exec={APP_NAME} %F
Icon=ncm-tag-extractor
Categories=AudioVideo;Audio;AudioVideoEditing;
Terminal=false
StartupNotify=true
"""
    (appdir / "ncm-tag-extractor.desktop").write_text(desktop_content, encoding="utf-8")

    # 2. Icon (fallback SVG icon)
    svg_icon = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>"""
    (appdir / "ncm-tag-extractor.svg").write_text(svg_icon, encoding="utf-8")

    # 3. AppRun script
    apprun_content = f"""#!/bin/sh
HERE="$(dirname "$(readlink -f "${{0}}")")"
exec "${{HERE}}/usr/bin/{APP_NAME}" "$@"
"""
    apprun_file = appdir / "AppRun"
    apprun_file.write_text(apprun_content, encoding="utf-8")
    apprun_file.chmod(0o755)

    print(f"[SUCCESS] AppDir 目录结构已生成: {appdir}")
    return appdir


def package_appimage(appdir: Path) -> None:
    """Generate .AppImage if appimagetool is available."""
    tool = shutil.which("appimagetool")
    if not tool:
        print("[INFO] 提示: 系统中未找到 'appimagetool'。")
        print("   如果你想生成单文件 .AppImage，请下载 appimagetool：")
        print("   wget https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage")
        print("   chmod +x appimagetool-x86_64.AppImage")
        print(f"   ./appimagetool-x86_64.AppImage {appdir} dist/{APP_NAME}-x86_64.AppImage")
        return

    output_appimage = DIST_DIR / f"{APP_NAME}-x86_64.AppImage"
    print(f"[BUILD] 正在使用 appimagetool 生成 {output_appimage.name} ...")
    cmd = [tool, str(appdir), str(output_appimage)]
    env = dict(os.environ)
    env["ARCH"] = "x86_64"
    res = subprocess.run(cmd, env=env)
    if res.returncode == 0 and output_appimage.is_file():
        output_appimage.chmod(0o755)
        print(f"[SUCCESS] Linux 免安装 AppImage 生成成功: {output_appimage}")
    else:
        print("[WARN] appimagetool 生成失败。")


def main() -> None:
    clean_previous_builds()
    binary_path = build_pyinstaller_binary()

    system = platform.system()
    if system == "Linux":
        appdir = create_linux_appdir(binary_path)
        package_appimage(appdir)
    elif system == "Windows":
        print(f"[SUCCESS] Windows 单文件免安装绿色版生成成功: {binary_path}")


if __name__ == "__main__":
    main()
