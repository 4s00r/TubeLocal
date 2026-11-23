from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PreviewRequest(BaseModel):
    url: str = Field(..., min_length=8)


class DownloadRequest(BaseModel):
    url: str = Field(..., min_length=8)
    format_id: str = Field(default="bestvideo*+bestaudio/best")
    format_note: str | None = None


class QueueFromHistoryRequest(BaseModel):
    format_id: str = Field(default="bestvideo*+bestaudio/best")
    format_note: str | None = None


class PreviewResponse(BaseModel):
    link_id: int
    url: str
    video_id: str
    title: str | None = None
    channel: str | None = None
    duration: int | None = None
    thumbnail_url: str | None = None
    description: str | None = None
    view_count: int | None = None
    formats: list[dict[str, Any]]
    default_format_id: str
    ffmpeg_available: bool


class JobResponse(BaseModel):
    id: int
    link_id: int
    format_id: str
    format_note: str | None = None
    status: str
    progress: float = 0
    speed: str | None = None
    eta: str | None = None
    speed_bps: float | None = None
    eta_seconds: float | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    remaining_bytes: int | None = None
    phase: str | None = None
    filepath: str | None = None
    filesize: int | None = None
    error: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None
    # Video metadata for multi-download list
    title: str | None = None
    channel: str | None = None
    thumbnail_url: str | None = None
    video_id: str | None = None
    url: str | None = None
    duration: int | None = None


class HistoryItem(BaseModel):
    id: int
    url: str
    video_id: str
    title: str | None = None
    channel: str | None = None
    duration: int | None = None
    thumbnail_url: str | None = None
    last_preview_at: str | None = None
    created_at: str
    latest_job_id: int | None = None
    latest_status: str | None = None
    latest_progress: float | None = None
    latest_filepath: str | None = None
    latest_format_note: str | None = None
    latest_error: str | None = None
    latest_job_updated_at: str | None = None


class MessageResponse(BaseModel):
    ok: bool
    message: str
    removed: int | None = None


class ClearJobsRequest(BaseModel):
    """Statuses to remove from the download list. Default = finished jobs only."""

    statuses: list[str] | None = None
