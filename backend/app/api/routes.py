from __future__ import annotations

import json
import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from app.schemas import (
    ClearJobsRequest,
    DownloadRequest,
    HistoryItem,
    JobResponse,
    MessageResponse,
    PreviewRequest,
    PreviewResponse,
    QueueFromHistoryRequest,
)
from app.services import history_service
from app.services.download_worker import worker
from app.services.ytdlp_service import (
    DEFAULT_FORMAT,
    PublicVideoError,
    YoutubeAccessError,
    extract_info,
)

router = APIRouter(prefix="/api")


def _remaining_bytes(job: dict) -> int | None:
    total = job.get("total_bytes") or job.get("filesize")
    downloaded = job.get("downloaded_bytes") or 0
    if total is None:
        return None
    try:
        return max(0, int(total) - int(downloaded))
    except (TypeError, ValueError):
        return None


def _job_response(job: dict) -> JobResponse:
    return JobResponse(
        id=job["id"],
        link_id=job["link_id"],
        format_id=job["format_id"],
        format_note=job.get("format_note"),
        status=job["status"],
        progress=job.get("progress") or 0,
        speed=job.get("speed"),
        eta=job.get("eta"),
        speed_bps=job.get("speed_bps"),
        eta_seconds=job.get("eta_seconds"),
        downloaded_bytes=job.get("downloaded_bytes"),
        total_bytes=job.get("total_bytes"),
        remaining_bytes=_remaining_bytes(job),
        phase=job.get("phase"),
        filepath=job.get("filepath"),
        filesize=job.get("filesize"),
        error=job.get("error"),
        started_at=job.get("started_at"),
        ended_at=job.get("ended_at"),
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        completed_at=job.get("completed_at"),
        title=job.get("title"),
        channel=job.get("channel"),
        thumbnail_url=job.get("thumbnail_url"),
        video_id=job.get("video_id"),
        url=job.get("url"),
        duration=job.get("duration"),
    )


@router.get("/health")
def health() -> dict:
    return {"ok": True}


@router.post("/preview", response_model=PreviewResponse)
def preview(body: PreviewRequest) -> PreviewResponse:
    try:
        info = extract_info(body.url)
    except PublicVideoError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except YoutubeAccessError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    link = history_service.upsert_link(
        url=info["url"],
        video_id=info["video_id"],
        title=info.get("title"),
        channel=info.get("channel"),
        duration=info.get("duration"),
        thumbnail_url=info.get("thumbnail_url"),
        preview=info,
    )
    return PreviewResponse(
        link_id=link["id"],
        url=info["url"],
        video_id=info["video_id"],
        title=info.get("title"),
        channel=info.get("channel"),
        duration=info.get("duration"),
        thumbnail_url=info.get("thumbnail_url"),
        description=info.get("description"),
        view_count=info.get("view_count"),
        formats=info["formats"],
        default_format_id=info["default_format_id"],
        ffmpeg_available=info["ffmpeg_available"],
    )


@router.post("/downloads", response_model=JobResponse)
async def start_download(body: DownloadRequest) -> JobResponse:
    try:
        info = extract_info(body.url)
    except PublicVideoError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except YoutubeAccessError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    link = history_service.upsert_link(
        url=info["url"],
        video_id=info["video_id"],
        title=info.get("title"),
        channel=info.get("channel"),
        duration=info.get("duration"),
        thumbnail_url=info.get("thumbnail_url"),
        preview=info,
    )
    format_note = body.format_note
    if not format_note:
        for fmt in info["formats"]:
            if fmt["format_id"] == body.format_id:
                format_note = fmt.get("label") or fmt.get("format_note")
                break

    job = history_service.create_job(
        link_id=link["id"],
        format_id=body.format_id,
        format_note=format_note,
    )
    await worker.enqueue(job["id"])
    enriched = history_service.get_job_enriched(job["id"]) or job
    return _job_response(enriched)


@router.get("/downloads/{job_id}", response_model=JobResponse)
def get_download(job_id: int) -> JobResponse:
    job = history_service.get_job_enriched(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_response(job)


@router.get("/downloads/{job_id}/events")
async def download_events(job_id: int) -> StreamingResponse:
    job = history_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_stream():
        q = await worker.subscribe(job_id)
        try:
            while True:
                event = await q.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("status") in ("completed", "failed", "cancelled", "paused"):
                    break
        finally:
            await worker.unsubscribe(job_id, q)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/downloads/{job_id}/cancel", response_model=MessageResponse)
def cancel_download(job_id: int) -> MessageResponse:
    job = history_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    ok = worker.request_cancel(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled")
    return MessageResponse(ok=True, message="Cancel requested")


@router.delete("/downloads/{job_id}", response_model=MessageResponse)
def remove_download(job_id: int) -> MessageResponse:
    """Remove a job from the download list (files on disk are kept)."""
    job = history_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # Stop in-flight work first so the worker does not resurrect progress
    if job["status"] not in ("completed", "failed", "cancelled"):
        worker.request_cancel(job_id)
    ok = history_service.delete_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")
    return MessageResponse(ok=True, message="Removed from download list", removed=1)


@router.post("/jobs/clear", response_model=MessageResponse)
def clear_download_list(body: ClearJobsRequest = ClearJobsRequest()) -> MessageResponse:
    """Clear finished jobs from the list, or specific statuses."""
    allowed = {
        "completed",
        "failed",
        "cancelled",
        "paused",
        "queued",
    }
    statuses = body.statuses
    if statuses is not None:
        bad = [s for s in statuses if s not in allowed]
        if bad:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot clear active statuses or unknown: {', '.join(bad)}. "
                "Cancel/remove those jobs individually.",
            )
    removed = history_service.clear_jobs(statuses)
    return MessageResponse(
        ok=True,
        message=f"Removed {removed} job(s) from download list",
        removed=removed,
    )


@router.post("/downloads/{job_id}/pause", response_model=MessageResponse)
def pause_download(job_id: int) -> MessageResponse:
    job = history_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    ok = worker.request_pause(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Job cannot be paused")
    return MessageResponse(ok=True, message="Pause requested")


@router.post("/downloads/{job_id}/resume", response_model=JobResponse)
async def resume_download(job_id: int) -> JobResponse:
    job = history_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    ok = await worker.request_resume(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Job cannot be resumed")
    updated = history_service.get_job_enriched(job_id)
    assert updated is not None
    return _job_response(updated)


@router.get("/downloads/{job_id}/file")
def download_file(job_id: int) -> FileResponse:
    job = history_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed" or not job.get("filepath"):
        raise HTTPException(status_code=400, detail="File not ready")
    path = Path(job["filepath"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    media_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        filename=path.name,
        # Stream from disk; do not buffer whole file
    )


@router.get("/history", response_model=list[HistoryItem])
def history(search: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=500)) -> list[HistoryItem]:
    rows = history_service.list_history(search=search, limit=limit)
    return [HistoryItem(**{k: r.get(k) for k in HistoryItem.model_fields}) for r in rows]


@router.post("/history/{link_id}/reuse", response_model=PreviewResponse)
def reuse_history(link_id: int, refresh: bool = Query(default=True)) -> PreviewResponse:
    link = history_service.get_link(link_id)
    if not link:
        raise HTTPException(status_code=404, detail="History item not found")

    if not refresh and link.get("last_preview_json"):
        try:
            info = json.loads(link["last_preview_json"])
            return PreviewResponse(
                link_id=link["id"],
                url=info.get("url") or link["url"],
                video_id=info.get("video_id") or link["video_id"],
                title=info.get("title") or link.get("title"),
                channel=info.get("channel") or link.get("channel"),
                duration=info.get("duration") or link.get("duration"),
                thumbnail_url=info.get("thumbnail_url") or link.get("thumbnail_url"),
                description=info.get("description"),
                view_count=info.get("view_count"),
                formats=info.get("formats") or [],
                default_format_id=info.get("default_format_id") or "bestvideo*+bestaudio/best",
                ffmpeg_available=bool(info.get("ffmpeg_available")),
            )
        except json.JSONDecodeError:
            pass

    try:
        info = extract_info(link["url"])
    except PublicVideoError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except YoutubeAccessError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    updated = history_service.upsert_link(
        url=info["url"],
        video_id=info["video_id"],
        title=info.get("title"),
        channel=info.get("channel"),
        duration=info.get("duration"),
        thumbnail_url=info.get("thumbnail_url"),
        preview=info,
    )
    return PreviewResponse(
        link_id=updated["id"],
        url=info["url"],
        video_id=info["video_id"],
        title=info.get("title"),
        channel=info.get("channel"),
        duration=info.get("duration"),
        thumbnail_url=info.get("thumbnail_url"),
        description=info.get("description"),
        view_count=info.get("view_count"),
        formats=info["formats"],
        default_format_id=info["default_format_id"],
        ffmpeg_available=info["ffmpeg_available"],
    )


@router.get("/jobs/active", response_model=list[JobResponse])
def active_jobs() -> list[JobResponse]:
    return [_job_response(j) for j in history_service.get_active_jobs()]


@router.get("/jobs", response_model=list[JobResponse])
def list_jobs(
    status: str | None = Query(
        default=None,
        description="Comma-separated statuses, or omit for recent jobs of all statuses",
    ),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[JobResponse]:
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    return [_job_response(j) for j in history_service.list_jobs(statuses=statuses, limit=limit)]


@router.post("/history/{link_id}/queue", response_model=JobResponse)
async def queue_from_history(
    link_id: int,
    body: QueueFromHistoryRequest = QueueFromHistoryRequest(),
) -> JobResponse:
    """Add a history video to the multi-download queue (IDM-style)."""
    link = history_service.get_link(link_id)
    if not link:
        raise HTTPException(status_code=404, detail="History item not found")

    format_id = body.format_id or DEFAULT_FORMAT
    format_note = body.format_note

    # Prefer cached preview formats for note; still validate URL is fetchable lightly via link
    if not format_note and link.get("last_preview_json"):
        try:
            cached = json.loads(link["last_preview_json"])
            for fmt in cached.get("formats") or []:
                if fmt.get("format_id") == format_id:
                    format_note = fmt.get("label") or fmt.get("format_note")
                    break
        except json.JSONDecodeError:
            pass
    if not format_note:
        format_note = "Best quality (video+audio merge)" if format_id == DEFAULT_FORMAT else format_id

    job = history_service.create_job(
        link_id=link["id"],
        format_id=format_id,
        format_note=format_note,
    )
    await worker.enqueue(job["id"])
    enriched = history_service.get_job_enriched(job["id"]) or job
    return _job_response(enriched)
