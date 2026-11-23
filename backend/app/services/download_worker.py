from __future__ import annotations

import asyncio
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.db.models import utc_now
from app.services import history_service
from app.services.formatters import compute_eta_seconds, format_duration_human, format_speed
from app.services.ytdlp_service import DownloadInterrupted, PublicVideoError, download_video


def _remaining_bytes(downloaded: Any, total: Any) -> int | None:
    if total is None:
        return None
    try:
        return max(0, int(total) - int(downloaded or 0))
    except (TypeError, ValueError):
        return None


def _parse_iso(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


class DownloadWorker:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._cancel_flags: dict[int, threading.Event] = {}
        self._pause_flags: dict[int, threading.Event] = {}
        self._subscribers: dict[int, list[asyncio.Queue[dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()
        self._tasks: list[asyncio.Task] = []
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        history_service.mark_stale_jobs_paused()
        for job in history_service.list_jobs_by_status(["queued"]):
            await self._queue.put(job["id"])
        for _ in range(settings.max_concurrent_downloads):
            self._tasks.append(asyncio.create_task(self._worker_loop()))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        self._started = False

    def _ensure_flags(self, job_id: int) -> tuple[threading.Event, threading.Event]:
        cancel = self._cancel_flags.setdefault(job_id, threading.Event())
        pause = self._pause_flags.setdefault(job_id, threading.Event())
        return cancel, pause

    async def enqueue(self, job_id: int) -> None:
        cancel, pause = self._ensure_flags(job_id)
        cancel.clear()
        pause.clear()
        await self._queue.put(job_id)
        job = history_service.get_job(job_id) or {}
        await self._publish(job_id, self._event_from_job({**job, "status": "queued", "phase": "queued"}))

    def request_cancel(self, job_id: int) -> bool:
        job = history_service.get_job(job_id)
        if not job:
            return False
        if job["status"] in ("completed", "failed", "cancelled"):
            return False
        cancel, pause = self._ensure_flags(job_id)
        pause.clear()
        cancel.set()
        if job["status"] in ("queued", "paused"):
            history_service.update_job(
                job_id,
                status="cancelled",
                phase="cancelled",
                error="Cancelled by user",
                speed=None,
                speed_bps=None,
                eta=None,
                eta_seconds=None,
                ended_at=utc_now(),
                completed_at=utc_now(),
            )
            self._schedule_publish(
                job_id,
                {
                    "job_id": job_id,
                    "status": "cancelled",
                    "phase": "cancelled",
                    "progress": job.get("progress") or 0,
                    "error": "Cancelled by user",
                    "ended_at": utc_now(),
                },
            )
        return True

    def request_pause(self, job_id: int) -> bool:
        job = history_service.get_job(job_id)
        if not job:
            return False
        if job["status"] not in ("queued", "fetching", "downloading", "merging"):
            return False
        cancel, pause = self._ensure_flags(job_id)
        if cancel.is_set():
            return False
        pause.set()
        now = utc_now()
        if job["status"] == "queued":
            history_service.update_job(
                job_id,
                status="paused",
                phase="paused",
                speed=None,
                speed_bps=None,
                eta=None,
                eta_seconds=None,
                ended_at=now,
            )
            self._schedule_publish(
                job_id,
                {
                    "job_id": job_id,
                    "status": "paused",
                    "phase": "paused",
                    "progress": job.get("progress") or 0,
                    "speed": None,
                    "eta": None,
                    "ended_at": now,
                },
            )
        else:
            # In-flight: mark pausing until yt-dlp honors the interrupt
            history_service.update_job(
                job_id,
                status="pausing",
                phase="pausing",
                speed=None,
                speed_bps=None,
                eta=None,
                eta_seconds=None,
            )
            self._schedule_publish(
                job_id,
                {
                    "job_id": job_id,
                    "status": "pausing",
                    "phase": "pausing",
                    "progress": job.get("progress") or 0,
                    "speed": None,
                    "eta": None,
                },
            )
        return True

    async def request_resume(self, job_id: int) -> bool:
        job = history_service.get_job(job_id)
        if not job or job["status"] != "paused":
            return False
        history_service.update_job(
            job_id,
            status="queued",
            phase="queued",
            error=None,
            speed=None,
            speed_bps=None,
            eta=None,
            eta_seconds=None,
            ended_at=None,
        )
        await self.enqueue(job_id)
        return True

    def _schedule_publish(self, job_id: int, event: dict[str, Any]) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._publish(job_id, event))
        except RuntimeError:
            pass

    def _event_from_job(self, job: dict[str, Any]) -> dict[str, Any]:
        downloaded = job.get("downloaded_bytes")
        total = job.get("total_bytes") or job.get("filesize")
        return {
            "job_id": job.get("id") or job.get("job_id"),
            "status": job.get("status"),
            "phase": job.get("phase") or job.get("status"),
            "progress": job.get("progress") or 0,
            "speed": job.get("speed"),
            "eta": job.get("eta"),
            "speed_bps": job.get("speed_bps"),
            "eta_seconds": job.get("eta_seconds"),
            "downloaded_bytes": downloaded,
            "total_bytes": total,
            "remaining_bytes": _remaining_bytes(downloaded, total),
            "started_at": job.get("started_at"),
            "ended_at": job.get("ended_at"),
            "error": job.get("error"),
            "filepath": job.get("filepath"),
            "filesize": job.get("filesize"),
            "title": job.get("title"),
            "channel": job.get("channel"),
            "thumbnail_url": job.get("thumbnail_url"),
            "video_id": job.get("video_id"),
            "url": job.get("url"),
        }

    async def subscribe(self, job_id: int) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        async with self._lock:
            self._subscribers.setdefault(job_id, []).append(q)
        job = history_service.get_job_enriched(job_id) or history_service.get_job(job_id)
        if job:
            await q.put(self._event_from_job(job))
        return q

    async def unsubscribe(self, job_id: int, q: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            subs = self._subscribers.get(job_id) or []
            if q in subs:
                subs.remove(q)
            if not subs and job_id in self._subscribers:
                del self._subscribers[job_id]

    async def _publish(self, job_id: int, event: dict[str, Any]) -> None:
        async with self._lock:
            subs = list(self._subscribers.get(job_id, []))
        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    _ = q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    async def _worker_loop(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                await self._process_job(job_id)
            except Exception as exc:  # noqa: BLE001
                history_service.update_job(
                    job_id,
                    status="failed",
                    phase="failed",
                    error=str(exc),
                    ended_at=utc_now(),
                    completed_at=utc_now(),
                )
                await self._publish(
                    job_id,
                    {
                        "job_id": job_id,
                        "status": "failed",
                        "phase": "failed",
                        "progress": 0,
                        "error": str(exc),
                        "ended_at": utc_now(),
                    },
                )
            finally:
                self._queue.task_done()

    def _disk_ok(self) -> tuple[bool, str | None]:
        usage = shutil.disk_usage(settings.download_dir)
        if usage.free < settings.min_free_disk_bytes:
            return False, (
                f"Not enough free disk space "
                f"({usage.free // (1024 * 1024)} MB free). "
                f"Free some space and try again."
            )
        return True, None

    async def _process_job(self, job_id: int) -> None:
        job = history_service.get_job(job_id)
        if not job:
            return
        if job["status"] in ("cancelled", "paused", "completed", "failed"):
            return

        cancel_flag, pause_flag = self._ensure_flags(job_id)
        if cancel_flag.is_set():
            history_service.update_job(
                job_id,
                status="cancelled",
                phase="cancelled",
                error="Cancelled by user",
                ended_at=utc_now(),
                completed_at=utc_now(),
            )
            await self._publish(
                job_id,
                {
                    "job_id": job_id,
                    "status": "cancelled",
                    "phase": "cancelled",
                    "progress": job.get("progress") or 0,
                    "ended_at": utc_now(),
                },
            )
            return
        if pause_flag.is_set():
            history_service.update_job(
                job_id,
                status="paused",
                phase="paused",
                speed=None,
                speed_bps=None,
                eta=None,
                eta_seconds=None,
                ended_at=utc_now(),
            )
            await self._publish(
                job_id,
                {
                    "job_id": job_id,
                    "status": "paused",
                    "phase": "paused",
                    "progress": job.get("progress") or 0,
                    "ended_at": utc_now(),
                },
            )
            return

        ok, err = self._disk_ok()
        if not ok:
            history_service.update_job(
                job_id,
                status="failed",
                phase="failed",
                error=err,
                ended_at=utc_now(),
                completed_at=utc_now(),
            )
            await self._publish(
                job_id,
                {
                    "job_id": job_id,
                    "status": "failed",
                    "phase": "failed",
                    "error": err,
                    "progress": job.get("progress") or 0,
                    "ended_at": utc_now(),
                },
            )
            return

        link = history_service.get_link(job["link_id"])
        if not link:
            history_service.update_job(
                job_id,
                status="failed",
                phase="failed",
                error="Link not found",
                ended_at=utc_now(),
                completed_at=utc_now(),
            )
            return

        started_at = job.get("started_at") or utc_now()
        history_service.update_job(
            job_id,
            status="fetching",
            phase="fetching",
            error=None,
            started_at=started_at,
            ended_at=None,
        )
        await self._publish(
            job_id,
            {
                "job_id": job_id,
                "status": "fetching",
                "phase": "fetching",
                "progress": job.get("progress") or 0,
                "started_at": started_at,
            },
        )

        loop = asyncio.get_running_loop()
        last_db_write = {"t": 0.0}
        started_epoch = _parse_iso(started_at) or time.time()

        def interrupt_check() -> str | None:
            if cancel_flag.is_set():
                return "cancelled"
            if pause_flag.is_set():
                return "paused"
            return None

        def progress_hook(d: dict[str, Any]) -> None:
            status = d.get("status")
            phase = "downloading"
            progress = float(job.get("progress") or 0)
            speed_bps = None
            speed = None
            eta_seconds = None
            eta = None
            downloaded = d.get("downloaded_bytes")
            total = d.get("total_bytes") or d.get("total_bytes_estimate")

            if status == "downloading":
                if total and downloaded is not None:
                    progress = max(0.0, min(100.0, float(downloaded) * 100.0 / float(total)))
                speed_val = d.get("speed")
                if speed_val:
                    speed_bps = float(speed_val)
                    speed = format_speed(speed_bps)
                eta_seconds = compute_eta_seconds(
                    downloaded=downloaded,
                    total=total,
                    speed_bps=speed_bps,
                    started_at_epoch=started_epoch,
                    now_epoch=time.time(),
                )
                # Prefer yt-dlp ETA when our estimate is missing
                if eta_seconds is None and d.get("eta") is not None:
                    try:
                        eta_seconds = float(d["eta"])
                    except (TypeError, ValueError):
                        eta_seconds = None
                eta = format_duration_human(eta_seconds)
            elif status == "finished":
                phase = "merging"
                progress = max(progress, 99.0)
                speed = None
                speed_bps = None
                eta = None
                eta_seconds = None
            elif status == "error":
                phase = "failed"

            now = time.time()
            if now - last_db_write["t"] > 0.35 or phase in ("merging", "failed"):
                last_db_write["t"] = now
                status_name = "merging" if phase == "merging" else "downloading"
                history_service.update_job(
                    job_id,
                    status=status_name,
                    phase=phase,
                    progress=progress,
                    speed=speed,
                    speed_bps=speed_bps,
                    eta=eta,
                    eta_seconds=eta_seconds,
                    downloaded_bytes=int(downloaded) if downloaded is not None else None,
                    total_bytes=int(total) if total is not None else None,
                )
                dl_i = int(downloaded) if downloaded is not None else None
                tot_i = int(total) if total is not None else None
                asyncio.run_coroutine_threadsafe(
                    self._publish(
                        job_id,
                        {
                            "job_id": job_id,
                            "status": status_name,
                            "phase": phase,
                            "progress": progress,
                            "speed": speed,
                            "speed_bps": speed_bps,
                            "eta": eta,
                            "eta_seconds": eta_seconds,
                            "downloaded_bytes": dl_i,
                            "total_bytes": tot_i,
                            "remaining_bytes": _remaining_bytes(dl_i, tot_i),
                            "started_at": started_at,
                            "title": link.get("title"),
                            "channel": link.get("channel"),
                            "thumbnail_url": link.get("thumbnail_url"),
                            "video_id": link.get("video_id"),
                            "url": link.get("url"),
                        },
                    ),
                    loop,
                )

        outtmpl = job.get("output_template")
        if not outtmpl:
            safe_title = "".join(
                c if c.isalnum() or c in (" ", "-", "_") else "_"
                for c in (link.get("title") or link["video_id"])
            ).strip()[:80]
            outtmpl = str(
                settings.download_dir
                / f"{link['video_id']}_{job_id}_{safe_title}.%(ext)s"
            )
            history_service.update_job(job_id, output_template=outtmpl)

        def run_download() -> dict[str, Any]:
            return download_video(
                url=link["url"],
                format_id=job["format_id"],
                output_template=outtmpl,
                progress_hook=progress_hook,
                interrupt_check=interrupt_check,
            )

        try:
            result = await loop.run_in_executor(None, run_download)
        except DownloadInterrupted as exc:
            now = utc_now()
            if exc.reason == "paused":
                history_service.update_job(
                    job_id,
                    status="paused",
                    phase="paused",
                    error=None,
                    speed=None,
                    speed_bps=None,
                    eta=None,
                    eta_seconds=None,
                    ended_at=now,
                )
                await self._publish(
                    job_id,
                    {
                        "job_id": job_id,
                        "status": "paused",
                        "phase": "paused",
                        "progress": (history_service.get_job(job_id) or {}).get("progress") or 0,
                        "speed": None,
                        "eta": None,
                        "ended_at": now,
                        "started_at": started_at,
                    },
                )
            else:
                history_service.update_job(
                    job_id,
                    status="cancelled",
                    phase="cancelled",
                    error="Cancelled by user",
                    speed=None,
                    speed_bps=None,
                    eta=None,
                    eta_seconds=None,
                    ended_at=now,
                    completed_at=now,
                )
                await self._publish(
                    job_id,
                    {
                        "job_id": job_id,
                        "status": "cancelled",
                        "phase": "cancelled",
                        "progress": (history_service.get_job(job_id) or {}).get("progress") or 0,
                        "error": "Cancelled by user",
                        "ended_at": now,
                        "started_at": started_at,
                    },
                )
            return
        except PublicVideoError as exc:
            now = utc_now()
            history_service.update_job(
                job_id,
                status="failed",
                phase="failed",
                error=str(exc),
                ended_at=now,
                completed_at=now,
            )
            await self._publish(
                job_id,
                {
                    "job_id": job_id,
                    "status": "failed",
                    "phase": "failed",
                    "error": str(exc),
                    "progress": 0,
                    "ended_at": now,
                },
            )
            return
        except Exception as exc:  # noqa: BLE001
            now = utc_now()
            history_service.update_job(
                job_id,
                status="failed",
                phase="failed",
                error=str(exc),
                ended_at=now,
                completed_at=now,
            )
            await self._publish(
                job_id,
                {
                    "job_id": job_id,
                    "status": "failed",
                    "phase": "failed",
                    "error": str(exc),
                    "progress": 0,
                    "ended_at": now,
                },
            )
            return

        filepath = result.get("filepath")
        filesize = result.get("filesize")
        if filepath and Path(filepath).exists():
            filesize = Path(filepath).stat().st_size
        elif filepath:
            for ext in (".mp4", ".mkv", ".webm", ".m4a"):
                candidate = Path(filepath).with_suffix(ext)
                if candidate.exists():
                    filepath = str(candidate)
                    filesize = candidate.stat().st_size
                    break

        now = utc_now()
        history_service.update_job(
            job_id,
            status="completed",
            phase="done",
            progress=100,
            speed=None,
            speed_bps=None,
            eta=None,
            eta_seconds=0,
            filepath=filepath,
            filesize=filesize,
            downloaded_bytes=filesize,
            total_bytes=filesize,
            error=None,
            ended_at=now,
            completed_at=now,
        )
        await self._publish(
            job_id,
            {
                "job_id": job_id,
                "status": "completed",
                "phase": "done",
                "progress": 100,
                "filepath": filepath,
                "filesize": filesize,
                "started_at": started_at,
                "ended_at": now,
                "eta": format_duration_human(0),
                "eta_seconds": 0,
            },
        )


worker = DownloadWorker()
