from __future__ import annotations

import json
import re
from datetime import date, datetime, time as date_time, timezone
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_NAME = "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "input_dirs": [],
    "output_dir": "",
    "recursive": True,
    "enrich_netease": True,
    "sort_by": "name",
    "enable_mtime_filter": False,
    "process_after_mtime": "",
    "mtime_tz": "local",
    "auto_update_mtime": True,
    "only_process_failed": False,
}


def get_app_dir() -> Path:
    """Get application base directory (supports frozen binary like PyInstaller/AppImage)."""
    import os
    import sys

    # 1. Linux AppImage: use the directory where the .AppImage file resides
    appimage_path = os.environ.get("APPIMAGE")
    if appimage_path:
        return Path(appimage_path).resolve().parent

    # 2. Frozen binary (Windows .exe or standalone Linux binary)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    # 3. Source code development mode
    return Path(__file__).resolve().parent.parent


def get_default_config_path() -> Path:
    """Get default config.json path in the application directory."""
    return get_app_dir() / DEFAULT_CONFIG_NAME


def get_or_create_config(config_path: Path | None = None) -> tuple[dict[str, Any], Path]:
    """Load config.json, or create it with defaults if it does not exist."""
    path = config_path or get_default_config_path()
    if not path.is_file():
        cfg = dict(DEFAULT_CONFIG)
        save_config(path, cfg)
        return cfg, path

    loaded = load_config(path)
    dirty = False
    merged = dict(DEFAULT_CONFIG)
    for k, v in loaded.items():
        merged[k] = v

    # Check if any default key was missing
    for k in DEFAULT_CONFIG:
        if k not in loaded:
            dirty = True

    if dirty:
        save_config(path, merged)

    return merged, path


def load_config(config_path: Path) -> dict[str, Any]:
    """Load JSON configuration file."""
    if not config_path.is_file():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_config(config_path: Path, data: dict[str, Any]) -> None:
    """Save dictionary configuration back to JSON file."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    config_path.write_text(content, encoding="utf-8")


def coerce_path_list(value: object) -> list[str]:
    """Coerce string or list of strings to list of path strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        paths: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("input_dirs / input_paths 只能包含字符串路径")
            paths.append(item)
        return paths
    raise ValueError("input_dirs / input_paths 必须是字符串或字符串数组")


def resolve_config_path(path_text: str, base_dir: Path) -> Path:
    """Resolve absolute path from config path text."""
    path = Path(path_text).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def config_bool(value: object, default: bool = False, name: str = "配置项") -> bool:
    """Coerce boolean value from config."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    raise ValueError(f"{name} 必须是 true/false")


def parse_config_mtime(value: object, is_utc: bool = False) -> float | None:
    """Parse modification timestamp from config."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("process_after_mtime 不能是 true/false")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        if is_utc and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    if isinstance(value, date):
        tz = timezone.utc if is_utc else None
        return datetime.combine(value, date_time.min, tzinfo=tz).timestamp()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
            if is_utc and dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError as exc:
            raise ValueError("process_after_mtime 必须为空，或形如 2026-04-29 18:30:00") from exc
    raise ValueError("process_after_mtime 必须为空、数字时间戳或日期时间字符串")


def format_config_mtime(timestamp: float, is_utc: bool = False) -> str:
    """Format float timestamp to clean YYYY-MM-DD HH:mm:ss string."""
    if is_utc:
        return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def update_config_mtime_checkpoint(config_path: Path, timestamp: float) -> None:
    """Update process_after_mtime timestamp in config TOML file."""
    if not config_path.is_file():
        return
    line = f'process_after_mtime = "{format_config_mtime(timestamp)}"'
    text = config_path.read_text(encoding="utf-8")
    if re.search(r"(?m)^process_after_mtime\s*=", text):
        text = re.sub(r"(?m)^process_after_mtime\s*=.*$", line, text, count=1)
    else:
        text = text.rstrip() + "\n\n" + line + "\n"
    config_path.write_text(text, encoding="utf-8")
