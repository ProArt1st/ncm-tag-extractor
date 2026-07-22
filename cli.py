#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import (
    DEFAULT_CONFIG_NAME,
    coerce_path_list,
    config_bool,
    format_config_mtime,
    load_config,
    parse_config_mtime,
    resolve_config_path,
    update_config_mtime_checkpoint,
)
from core.processor import BatchProcessor, iter_media_files


def prompt_run_mode() -> str:
    """Prompt user to select run mode."""
    print("请选择模式：")
    print("1. 仅转换 NCM")
    print("2. 转换 NCM 并从网易云音乐补充元数据信息")
    while True:
        try:
            choice = input("请输入 1 或 2：").strip()
        except EOFError:
            return "1"
        if choice in {"1", "2"}:
            return choice
        print("请输入 1 或 2。")


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="将 NCM 文件解码为原始音频文件。")
    parser.add_argument("paths", nargs="*", default=None, help="NCM 文件或目录，默认为脚本所在目录。")
    parser.add_argument("--config", default=str(script_dir / DEFAULT_CONFIG_NAME), help="TOML 配置文件路径。")
    parser.add_argument("--no-config", action="store_true", help="忽略 TOML 配置文件。")
    parser.add_argument("-o", "--output-dir", default=None, help="输出目录，默认为脚本所在目录。")
    parser.add_argument("-r", "--recursive", action="store_true", help="递归搜索目录。")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    config = {} if args.no_config else load_config(config_path)
    config_dir = config_path.parent

    config_output_dir = config.get("output_dir")
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser().resolve()
    elif isinstance(config_output_dir, str) and config_output_dir.strip():
        output_dir = resolve_config_path(config_output_dir, config_dir)
    else:
        output_dir = script_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    run_mode = prompt_run_mode()
    enrich_netease = run_mode == "2"
    extensions = {".ncm", ".flac", ".mp3"} if enrich_netease else {".ncm"}

    sort_by = str(config.get("sort_by") or "name").strip().casefold()
    only_process_failed = not args.no_config and config_bool(
        config.get("only_process_failed"), default=False, name="only_process_failed"
    )
    failed_list_path = script_dir / "failed_list.txt"
    files: list[Path] = []

    if only_process_failed and failed_list_path.is_file():
        try:
            lines = failed_list_path.read_text(encoding="utf-8").splitlines()
            for line in lines:
                line = line.strip()
                if line:
                    p = Path(line).resolve()
                    if p.is_file():
                        files.append(p)
            print(f"已启用只处理失败文件选项，从 {failed_list_path.name} 加载了 {len(files)} 个待重试文件。")
        except Exception as e:
            print(f"读取失败文件列表出错: {e}", file=sys.stderr)

    if not files:
        if args.paths:
            search_paths = [Path(p).expanduser().resolve() for p in args.paths]
        else:
            config_inputs = coerce_path_list(config.get("input_dirs")) + coerce_path_list(config.get("input_paths"))
            search_paths = [resolve_config_path(path_text, config_dir) for path_text in config_inputs] or [script_dir]
        recursive = args.recursive or config_bool(config.get("recursive"), default=False, name="recursive")
        files = iter_media_files(search_paths, recursive=recursive, extensions=extensions, sort_by=sort_by)
        process_after_mtime = None if args.no_config else parse_config_mtime(config.get("process_after_mtime"))
        if process_after_mtime is not None:
            files = [file for file in files if file.stat().st_mtime > process_after_mtime]

    if not files:
        wanted = "、".join(sorted(extensions))
        print(f"未找到可处理文件（{wanted}）。", file=sys.stderr)
        try:
            input("按回车退出程序...")
        except EOFError:
            pass
        return 1

    processor = BatchProcessor()
    failures = 0
    successes = 0
    failed_names: list[str] = []
    failed_paths: list[Path] = []
    auto_update_mtime = (
        not args.no_config
        and sort_by == "mtime"
        and config_bool(
            config.get("auto_update_process_after_mtime"),
            default=False,
            name="auto_update_process_after_mtime",
        )
    )
    checkpoint_mtime: float | None = None
    checkpoint_blocked = False
    processed_albums: dict[tuple[str, str], list[tuple[Path, int]]] = {}

    for file in files:
        try:
            if file.suffix.lower() == ".ncm":
                result = processor.decode_file(file, output_dir, enrich_netease=enrich_netease)
            else:
                result = processor.process_audio_file(file, output_dir, enrich_netease=enrich_netease)

            if result.netease_attempted and result.netease_missing:
                failures += 1
                checkpoint_blocked = True
                failed_names.append(file.name)
                failed_paths.append(file.resolve())
                print(f"{file.name}：失败（网易云信息不完整：{', '.join(result.netease_missing)}）", file=sys.stderr)
                continue

            successes += 1
            album_name = result.album
            album_artist = None
            if result.netease_tags:
                album_artist = result.netease_tags.get("ALBUMARTIST")
            if not album_artist:
                album_artist = result.artist

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

            if auto_update_mtime and not checkpoint_blocked:
                file_mtime = file.stat().st_mtime
                checkpoint_mtime = file_mtime if checkpoint_mtime is None else max(checkpoint_mtime, file_mtime)

            if enrich_netease and result.netease_attempted:
                print(f"{file.name}：成功（已补充网易云元数据）")
            elif enrich_netease:
                print(f"{file.name}：成功（无需补充）")
            else:
                print(f"{file.name}：成功")

            if result.warnings:
                print(f"  [警告] 缺失信息：{', '.join(result.warnings)}")

        except Exception as exc:
            failures += 1
            checkpoint_blocked = True
            failed_names.append(file.name)
            failed_paths.append(file.resolve())
            print(f"{file.name}：失败 - {exc}", file=sys.stderr)

    # Post-process multi-disc albums for DISCTOTAL correction
    if processed_albums:
        processor.post_process_albums(processed_albums)

    print("")
    print(f"成功：{successes}")
    print(f"失败：{failures}")
    if failed_names:
        print("失败的文件：")
        for name in failed_names:
            print(f"- {name}")

    if auto_update_mtime and checkpoint_mtime is not None:
        update_config_mtime_checkpoint(config_path, checkpoint_mtime)
        print(f"已更新处理起点时间：{format_config_mtime(checkpoint_mtime)}")

    if failed_paths:
        try:
            failed_list_path.write_text("\n".join(str(p) for p in failed_paths) + "\n", encoding="utf-8")
            print(f"已更新失败文件列表：{failed_list_path}")
        except Exception as e:
            print(f"写入失败文件列表出错: {e}", file=sys.stderr)
    else:
        if failed_list_path.is_file():
            try:
                failed_list_path.unlink()
                print("所有文件处理成功，已清除失败文件列表。")
            except Exception as e:
                try:
                    failed_list_path.write_text("", encoding="utf-8")
                except Exception:
                    pass

    try:
        input("按回车退出程序...")
    except EOFError:
        pass

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
