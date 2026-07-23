from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from core.processor import BatchProcessor, iter_media_files
from server.schemas import (
    ProgressMessageSchema,
    ScanRequest,
    StartBatchRequest,
    TaskItemSchema,
)
from server.websocket import ws_manager

app = FastAPI(title="NCM Tag Extractor API", version="2.0.0")

# Enable CORS for local React development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global task state
CURRENT_BATCH_CANCELLED = False
IS_PROCESSING = False


def generate_item_id(path: Path) -> str:
    return hashlib.md5(str(path.resolve()).encode("utf-8")).hexdigest()


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "NCM Tag Extractor API"}


@app.post("/api/scan")
async def scan_paths(req: ScanRequest) -> dict[str, Any]:
    """Scan directory or files for NCM/FLAC/MP3 files."""
    script_dir = Path(__file__).resolve().parent.parent
    valid_paths = [p.strip() for p in req.paths if p and p.strip()]
    search_paths = [Path(p).expanduser().resolve() for p in valid_paths] if valid_paths else [script_dir]
    extensions = {".ncm", ".flac", ".mp3"}
    found_files = iter_media_files(search_paths, recursive=req.recursive, extensions=extensions)

    items = []
    for f in found_files:
        items.append(
            TaskItemSchema(
                id=generate_item_id(f),
                filename=f.name,
                source_path=str(f.resolve()),
                ext=f.suffix.lower().lstrip("."),
                status="pending",
            )
        )
    return {"total": len(items), "items": [item.model_dump() for item in items]}


MAIN_LOOP: asyncio.AbstractEventLoop | None = None


@app.on_event("startup")
async def startup_event() -> None:
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()


def safe_broadcast(message: ProgressMessageSchema) -> None:
    """Thread-safe WebSocket broadcasting to main asyncio event loop."""
    if MAIN_LOOP and MAIN_LOOP.is_running():
        asyncio.run_coroutine_threadsafe(ws_manager.broadcast(message), MAIN_LOOP)


def run_batch_task(req: StartBatchRequest) -> None:
    global CURRENT_BATCH_CANCELLED, IS_PROCESSING
    IS_PROCESSING = True
    CURRENT_BATCH_CANCELLED = False

    script_dir = Path(__file__).resolve().parent.parent
    valid_paths = [p.strip() for p in req.paths if p and p.strip()]
    search_paths = [Path(p).expanduser().resolve() for p in valid_paths] if valid_paths else [script_dir]
    output_dir = Path(req.output_dir).expanduser().resolve() if req.output_dir and req.output_dir.strip() else script_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    extensions = {".ncm", ".flac", ".mp3"} if req.enrich_netease else {".ncm"}
    files = iter_media_files(search_paths, recursive=req.recursive, extensions=extensions)
    total_count = len(files)

    processor = BatchProcessor()
    processed_albums: dict[tuple[str, str], list[tuple[Path, int]]] = {}

    safe_broadcast(
        ProgressMessageSchema(event="batch_start", total=total_count, completed=0, message=f"[开始] 开始批处理任务 (共 {total_count} 个文件)")
    )

    completed_count = 0
    for idx, file in enumerate(files, start=1):
        if CURRENT_BATCH_CANCELLED:
            safe_broadcast(
                ProgressMessageSchema(event="log", message="[取消] 转换任务已被用户主动取消")
            )
            break

        item_id = generate_item_id(file)
        item_schema = TaskItemSchema(
            id=item_id,
            filename=file.name,
            source_path=str(file.resolve()),
            ext=file.suffix.lower().lstrip("."),
            status="processing",
            progress=10,
        )

        safe_broadcast(
            ProgressMessageSchema(
                event="item_update",
                total=total_count,
                completed=completed_count,
                item=item_schema,
                message=f"[{idx}/{total_count}] [处理中] {file.name}",
            )
        )

        try:
            if file.suffix.lower() == ".ncm":
                result = processor.decode_file(file, output_dir, req.enrich_netease)
            else:
                result = processor.process_audio_file(file, output_dir, req.enrich_netease)

            item_schema.output_path = str(result.output.resolve())
            item_schema.title = result.title
            item_schema.artists = result.artist.split(";") if result.artist else []
            item_schema.album = result.album
            item_schema.warnings = result.warnings or []

            if result.netease_tags:
                item_schema.cover_url = result.netease_tags.get("COVER_URL")
                item_schema.has_lyrics = "LYRICS" in result.netease_tags

            if result.netease_attempted and result.netease_missing:
                item_schema.status = "failed"
                item_schema.error_msg = f"网易云信息不完整: {', '.join(result.netease_missing)}"
            else:
                item_schema.status = "success"
                item_schema.progress = 100
                completed_count += 1

                # Album tracking for multi-disc post-processing
                album_name = result.album
                album_artist = result.netease_tags.get("ALBUMARTIST") if result.netease_tags else result.artist
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

        except Exception as exc:
            item_schema.status = "failed"
            item_schema.error_msg = str(exc)

        safe_broadcast(
            ProgressMessageSchema(
                event="item_update",
                total=total_count,
                completed=completed_count,
                item=item_schema,
                message=f"[{idx}/{total_count}] [成功] {file.name}" if item_schema.status == "success" else f"[{idx}/{total_count}] [失败] {file.name}",
            )
        )

    # Multi-disc post-processing
    if processed_albums:
        processor.post_process_albums(processed_albums)

    IS_PROCESSING = False
    safe_broadcast(
        ProgressMessageSchema(
            event="batch_complete",
            total=total_count,
            completed=completed_count,
            message=f"[完成] 任务处理完成 (成功: {completed_count}/{total_count})",
        )
    )


@app.post("/api/start")
async def start_batch(req: StartBatchRequest, bg_tasks: BackgroundTasks) -> dict[str, Any]:
    global IS_PROCESSING
    if IS_PROCESSING:
        return JSONResponse(status_code=400, content={"error": "已有转换任务正在运行中"})
    bg_tasks.add_task(run_batch_task, req)
    return {"status": "started", "message": "已成功启动转换任务"}


@app.post("/api/cancel")
async def cancel_batch() -> dict[str, str]:
    global CURRENT_BATCH_CANCELLED
    CURRENT_BATCH_CANCELLED = True
    return {"status": "cancelled", "message": "已向任务发送取消指令"}


@app.websocket("/api/ws/progress")
async def websocket_progress(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# Mount static React bundle if dist exists
dist_dir = Path(__file__).resolve().parent.parent / "web" / "dist"
if dist_dir.is_dir():
    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/")
    async def serve_index() -> FileResponse:
        return FileResponse(str(dist_dir / "index.html"))
