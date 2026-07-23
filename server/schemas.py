from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class TaskItemSchema(BaseModel):
    """Schema for individual audio conversion task status."""

    id: str = Field(description="Unique ID for task item")
    filename: str = Field(description="Original file name")
    source_path: str = Field(description="Absolute path to source file")
    output_path: str | None = Field(default=None, description="Absolute path to output file")
    ext: str = Field(default="mp3", description="Audio extension: flac or mp3")
    status: Literal["pending", "processing", "success", "failed"] = Field(
        default="pending", description="Current status"
    )
    progress: int = Field(default=0, ge=0, le=100, description="Completion percentage")
    title: str | None = Field(default=None, description="Song title")
    artists: list[str] = Field(default_factory=list, description="Artist names list")
    album: str | None = Field(default=None, description="Album name")
    cover_url: str | None = Field(default=None, description="Album cover image URL")
    has_lyrics: bool = Field(default=False, description="Whether lyrics are embedded")
    netease_id: int | str | None = Field(default=None, description="NetEase song ID")
    warnings: list[str] = Field(default_factory=list, description="Warning messages")
    error_msg: str | None = Field(default=None, description="Error message if failed")


class ScanRequest(BaseModel):
    """Request payload for scanning files or directories."""

    paths: list[str] = Field(default_factory=list, description="List of file or directory paths to scan")
    recursive: bool = Field(default=False, description="Recursive directory search")


class StartBatchRequest(BaseModel):
    """Request payload for starting batch conversion."""

    paths: list[str] = Field(default_factory=list, description="Paths to process")
    output_dir: str | None = Field(default=None, description="Output directory")
    enrich_netease: bool = Field(default=True, description="Enrich metadata from NetEase Music API")
    recursive: bool = Field(default=False, description="Recursive search")


class ProgressMessageSchema(BaseModel):
    """WebSocket notification message payload."""

    event: Literal["scan_result", "item_update", "batch_start", "batch_complete", "log"] = Field(
        description="Event type"
    )
    total: int = Field(default=0, description="Total files count")
    completed: int = Field(default=0, description="Completed files count")
    item: TaskItemSchema | None = Field(default=None, description="Item details")
    message: str | None = Field(default=None, description="Text log message")
