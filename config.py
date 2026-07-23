from __future__ import annotations

import json
import re
from datetime import date, datetime, time as date_time
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_NAME = "config.json"


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


def parse_config_mtime(value: object) -> float | None:
    """Parse modification timestamp from config."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("process_after_mtime 不能是 true/false")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, date):
        return datetime.combine(value, date_time.min).timestamp()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text).timestamp()
        except ValueError as exc:
            raise ValueError("process_after_mtime 必须为空，或形如 2026-04-29 18:30:00") from exc
    raise ValueError("process_after_mtime 必须为空、数字时间戳或日期时间字符串")


def format_config_mtime(timestamp: float) -> str:
    """Format float timestamp to clean YYYY-MM-DD HH:mm:ss string."""
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
