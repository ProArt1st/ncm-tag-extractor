"""Worker thread for batch audio conversion with Qt signals."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from core.config import (
    format_config_mtime,
    get_default_config_path,
    load_config,
    save_config,
)
from core.processor import BatchProcessor


class ConvertWorker(QThread):
    """Background worker for processing audio files without blocking the UI."""

    sig_batch_start = Signal(int)  # total count
    sig_item_update = Signal(dict, int, int, str)  # item_info, completed_count, total_count, log_msg
    sig_log = Signal(str, str)  # message, level ("info", "success", "warning", "error")
    sig_batch_finished = Signal(int, int, list)  # success_count, total_count, failed_items

    def __init__(
        self,
        files: list[Path],
        output_dir: Path | None = None,
        enrich_netease: bool = True,
        auto_update_mtime: bool = True,
        is_utc: bool = False,
        config_path: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.files = files
        self.output_dir = output_dir
        self.enrich_netease = enrich_netease
        self.auto_update_mtime = auto_update_mtime
        self.is_utc = is_utc
        self.config_path = config_path or get_default_config_path()
        self._is_cancelled = False

    def cancel(self) -> None:
        """Request worker cancellation."""
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def run(self) -> None:
        total_count = len(self.files)
        self.sig_batch_start.emit(total_count)
        self.sig_log.emit(f"开始批量处理，共 {total_count} 个文件", "info")

        if self.output_dir is not None:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        processor = BatchProcessor()
        processed_albums: dict[tuple[str, str], list[tuple[Path, int]]] = {}
        failed_items: list[dict[str, Any]] = []
        checkpoint_mtime: float | None = None
        completed_count = 0

        for idx, file in enumerate(self.files, start=1):
            if self._is_cancelled:
                self.sig_log.emit("用户已取消任务", "warning")
                break

            target_out_dir = self.output_dir if self.output_dir is not None else file.parent

            item_dict: dict[str, Any] = {
                "idx": idx,
                "name": file.name,
                "source_path": str(file.resolve()),
                "ext": file.suffix.lower().lstrip("."),
                "status": "processing",
                "title": "",
                "artist": "",
                "album_artist": "",
                "publisher": "",
                "track_number": "",
                "track_total": "",
                "disc_number": "",
                "has_lyrics": "",
                "album": "",
                "output_path": "",
                "error": "",
            }

            self.sig_item_update.emit(
                item_dict, completed_count, total_count, f"[{idx}/{total_count}] 处理中: {file.name}"
            )

            try:
                if file.suffix.lower() == ".ncm":
                    result = processor.decode_file(file, target_out_dir, self.enrich_netease)
                else:
                    result = processor.process_audio_file(file, target_out_dir, self.enrich_netease)

                tags = dict(result.netease_tags or {})
                if not tags and result.output.is_file():
                    try:
                        from core.metadata import get_audio_comments
                        file_tags = get_audio_comments(result.output.read_bytes(), result.ext)
                        for k, v in file_tags.items():
                            if k not in tags or not tags[k]:
                                tags[k] = v
                    except Exception:
                        pass

                item_dict["output_path"] = str(result.output.resolve())
                item_dict["title"] = result.title or tags.get("TITLE") or ""
                item_dict["artist"] = result.artist or tags.get("ARTIST") or ""
                item_dict["album_artist"] = tags.get("ALBUMARTIST") or item_dict["artist"] or ""
                item_dict["publisher"] = (
                    tags.get("ORGANIZATION") or tags.get("PUBLISHER") or tags.get("LABEL") or ""
                )
                item_dict["track_number"] = tags.get("TRACKNUMBER") or ""
                item_dict["track_total"] = tags.get("TRACKTOTAL") or ""
                item_dict["disc_number"] = tags.get("DISCNUMBER") or "1"
                has_lrc = bool(tags.get("LYRICS") and str(tags.get("LYRICS")).strip())
                item_dict["has_lyrics"] = "✓ 有" if has_lrc else "无"
                item_dict["album"] = result.album or tags.get("ALBUM") or ""

                if result.netease_attempted and result.netease_missing:
                    missing_str = ", ".join(result.netease_missing)
                    err_msg = f"网易云信息不全: {missing_str}"
                    item_dict["status"] = "failed"
                    item_dict["error"] = err_msg
                    failed_items.append({
                        "path": str(file.resolve()),
                        "name": file.name,
                        "reason": err_msg,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    })
                    log_msg = f"[{idx}/{total_count}] 元数据不全: {file.name} (缺失: {missing_str})"
                    self.sig_item_update.emit(item_dict, completed_count, total_count, log_msg)
                    self.sig_log.emit(log_msg, "warning")
                else:
                    item_dict["status"] = "success"
                    completed_count += 1

                    # Track file mtime for incremental checkpointing
                    file_mtime = file.stat().st_mtime
                    checkpoint_mtime = file_mtime if checkpoint_mtime is None else max(checkpoint_mtime, file_mtime)

                    # Multi-disc tracking
                    album_name = result.album
                    album_artist = (
                        result.netease_tags.get("ALBUMARTIST") if result.netease_tags else result.artist
                    )
                    disc_val = 1
                    if result.netease_tags and "DISCNUMBER" in result.netease_tags:
                        try:
                            disc_val = int(result.netease_tags["DISCNUMBER"])
                        except Exception:
                            pass
                    if album_name and album_artist:
                        album_key = (album_name.strip().upper(), album_artist.strip().upper())
                        if album_key not in processed_albums:
                            processed_albums[album_key] = []
                        processed_albums[album_key].append((result.output, disc_val))

                    log_msg = f"[{idx}/{total_count}] 成功: {file.name} -> {result.output.name}"
                    self.sig_item_update.emit(item_dict, completed_count, total_count, log_msg)
                    self.sig_log.emit(log_msg, "success")

            except Exception as exc:
                err_msg = str(exc)
                item_dict["status"] = "failed"
                item_dict["error"] = err_msg
                failed_items.append({
                    "path": str(file.resolve()),
                    "name": file.name,
                    "reason": err_msg,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
                log_msg = f"[{idx}/{total_count}] 失败: {file.name} ({err_msg})"
                self.sig_item_update.emit(item_dict, completed_count, total_count, log_msg)
                self.sig_log.emit(log_msg, "error")

        # Multi-disc albums post-processing
        if processed_albums:
            self.sig_log.emit("正在校验与修正多碟片专辑 DISCTOTAL...", "info")
            try:
                processor.post_process_albums(processed_albums)
            except Exception as e:
                self.sig_log.emit(f"多碟片专辑修正异常: {e}", "warning")

        # Manage fail.json in application directory
        app_dir = self.config_path.parent
        fail_file = app_dir / "fail.json"
        if failed_items:
            try:
                fail_file.write_text(
                    json.dumps(failed_items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )
                self.sig_log.emit(f"已保存 {len(failed_items)} 个失败项至 {fail_file.name}", "warning")
            except Exception as e:
                self.sig_log.emit(f"保存 {fail_file.name} 失败: {e}", "error")
        elif fail_file.is_file() and not self._is_cancelled:
            try:
                fail_file.unlink()
                self.sig_log.emit("所有文件均处理成功，已自动清除 fail.json", "success")
            except Exception:
                pass

        # Update process_after_mtime in config.json
        if self.auto_update_mtime and checkpoint_mtime is not None:
            try:
                current_cfg = load_config(self.config_path)
                formatted_mtime = format_config_mtime(checkpoint_mtime, is_utc=self.is_utc)
                current_cfg["process_after_mtime"] = formatted_mtime
                save_config(self.config_path, current_cfg)
                self.sig_log.emit(f"已更新时间节点配置: {formatted_mtime}", "info")
            except Exception as e:
                self.sig_log.emit(f"更新时间节点失败: {e}", "warning")

        status_text = "已取消" if self._is_cancelled else "已完成"
        self.sig_log.emit(
            f"任务{status_text}。总计: {total_count}，成功: {completed_count}，失败: {len(failed_items)}",
            "info" if self._is_cancelled else "success",
        )
        self.sig_batch_finished.emit(completed_count, total_count, failed_items)
