from __future__ import annotations

import json
from typing import Any

from app.db.database import get_db
from app.db.models import row_to_dict, utc_now


def upsert_link(
    *,
    url: str,
    video_id: str,
    title: str | None,
    channel: str | None,
    duration: int | None,
    thumbnail_url: str | None,
    preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = utc_now()
    preview_json = json.dumps(preview) if preview is not None else None
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM links WHERE video_id = ?", (video_id,)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE links
                SET url = ?, title = ?, channel = ?, duration = ?,
                    thumbnail_url = ?, last_preview_json = COALESCE(?, last_preview_json),
                    last_preview_at = ?
                WHERE video_id = ?
                """,
                (
                    url,
                    title,
                    channel,
                    duration,
                    thumbnail_url,
                    preview_json,
                    now,
                    video_id,
                ),
            )
            link_id = existing["id"]
        else:
            cur = conn.execute(
                """
                INSERT INTO links (
                    url, video_id, title, channel, duration,
                    thumbnail_url, last_preview_json, last_preview_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    url,
                    video_id,
                    title,
                    channel,
                    duration,
                    thumbnail_url,
                    preview_json,
                    now,
                    now,
                ),
            )
            link_id = cur.lastrowid
        row = conn.execute("SELECT * FROM links WHERE id = ?", (link_id,)).fetchone()
        return row_to_dict(row)


def get_link(link_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM links WHERE id = ?", (link_id,)).fetchone()
        return row_to_dict(row) if row else None


def get_link_by_video_id(video_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM links WHERE video_id = ?", (video_id,)
        ).fetchone()
        return row_to_dict(row) if row else None


def list_history(search: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    with get_db() as conn:
        if search:
            like = f"%{search}%"
            rows = conn.execute(
                """
                SELECT
                    l.*,
                    j.id AS latest_job_id,
                    j.status AS latest_status,
                    j.progress AS latest_progress,
                    j.filepath AS latest_filepath,
                    j.format_note AS latest_format_note,
                    j.error AS latest_error,
                    j.updated_at AS latest_job_updated_at
                FROM links l
                LEFT JOIN download_jobs j ON j.id = (
                    SELECT id FROM download_jobs
                    WHERE link_id = l.id
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                )
                WHERE l.title LIKE ? OR l.url LIKE ? OR l.channel LIKE ? OR l.video_id LIKE ?
                ORDER BY COALESCE(l.last_preview_at, l.created_at) DESC
                LIMIT ?
                """,
                (like, like, like, like, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT
                    l.*,
                    j.id AS latest_job_id,
                    j.status AS latest_status,
                    j.progress AS latest_progress,
                    j.filepath AS latest_filepath,
                    j.format_note AS latest_format_note,
                    j.error AS latest_error,
                    j.updated_at AS latest_job_updated_at
                FROM links l
                LEFT JOIN download_jobs j ON j.id = (
                    SELECT id FROM download_jobs
                    WHERE link_id = l.id
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                )
                ORDER BY COALESCE(l.last_preview_at, l.created_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [row_to_dict(r) for r in rows]


def create_job(
    *,
    link_id: int,
    format_id: str,
    format_note: str | None = None,
) -> dict[str, Any]:
    now = utc_now()
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO download_jobs (
                link_id, format_id, format_note, status, progress,
                speed, eta, speed_bps, eta_seconds, downloaded_bytes, total_bytes,
                phase, filepath, output_template, filesize, error,
                started_at, ended_at, created_at, updated_at, completed_at
            ) VALUES (
                ?, ?, ?, 'queued', 0,
                NULL, NULL, NULL, NULL, NULL, NULL,
                'queued', NULL, NULL, NULL, NULL,
                NULL, NULL, ?, ?, NULL
            )
            """,
            (link_id, format_id, format_note, now, now),
        )
        job_id = cur.lastrowid
        row = conn.execute(
            "SELECT * FROM download_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return row_to_dict(row)


def get_job(job_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM download_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return row_to_dict(row) if row else None


def update_job(job_id: int, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return get_job(job_id)
    fields["updated_at"] = utc_now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]
    with get_db() as conn:
        conn.execute(f"UPDATE download_jobs SET {cols} WHERE id = ?", values)
        row = conn.execute(
            "SELECT * FROM download_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return row_to_dict(row) if row else None


_JOB_SELECT = """
    SELECT
        j.*,
        l.url AS url,
        l.title AS title,
        l.channel AS channel,
        l.thumbnail_url AS thumbnail_url,
        l.video_id AS video_id,
        l.duration AS duration
    FROM download_jobs j
    JOIN links l ON l.id = j.link_id
"""

_STATUS_RANK = """
    CASE j.status
        WHEN 'downloading' THEN 0
        WHEN 'merging' THEN 1
        WHEN 'fetching' THEN 2
        WHEN 'pausing' THEN 3
        WHEN 'queued' THEN 4
        WHEN 'paused' THEN 5
        WHEN 'completed' THEN 6
        WHEN 'failed' THEN 7
        WHEN 'cancelled' THEN 8
        ELSE 9
    END
"""


def list_jobs_by_status(statuses: list[str]) -> list[dict[str, Any]]:
    if not statuses:
        return []
    placeholders = ",".join("?" for _ in statuses)
    with get_db() as conn:
        rows = conn.execute(
            f"""
            {_JOB_SELECT}
            WHERE j.status IN ({placeholders})
            ORDER BY {_STATUS_RANK}, j.updated_at DESC, j.id DESC
            """,
            statuses,
        ).fetchall()
        return [row_to_dict(r) for r in rows]


def list_jobs(
    *,
    statuses: list[str] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500))
    with get_db() as conn:
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            rows = conn.execute(
                f"""
                {_JOB_SELECT}
                WHERE j.status IN ({placeholders})
                ORDER BY {_STATUS_RANK}, j.updated_at DESC, j.id DESC
                LIMIT ?
                """,
                [*statuses, limit],
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                {_JOB_SELECT}
                ORDER BY {_STATUS_RANK}, j.updated_at DESC, j.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [row_to_dict(r) for r in rows]


def get_job_enriched(job_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            f"{_JOB_SELECT} WHERE j.id = ?",
            (job_id,),
        ).fetchone()
        return row_to_dict(row) if row else None


def mark_stale_jobs_paused() -> int:
    """Mark interrupted in-flight jobs as paused so they can be resumed."""
    now = utc_now()
    with get_db() as conn:
        cur = conn.execute(
            """
            UPDATE download_jobs
            SET status = 'paused',
                phase = 'paused',
                error = NULL,
                speed = NULL,
                speed_bps = NULL,
                eta = NULL,
                eta_seconds = NULL,
                ended_at = COALESCE(ended_at, ?),
                updated_at = ?
            WHERE status IN ('downloading', 'merging', 'fetching', 'pausing')
            """,
            (now, now),
        )
        return cur.rowcount


def get_active_jobs() -> list[dict[str, Any]]:
    return list_jobs_by_status(
        ["queued", "fetching", "downloading", "merging", "pausing", "paused"]
    )


def delete_job(job_id: int) -> bool:
    """Remove a job from the download list (does not delete files on disk)."""
    with get_db() as conn:
        cur = conn.execute("DELETE FROM download_jobs WHERE id = ?", (job_id,))
        return cur.rowcount > 0


def clear_jobs(statuses: list[str] | None = None) -> int:
    """
    Remove jobs from the download list.
    If statuses is None, clears finished jobs: completed / failed / cancelled.
    """
    target = statuses or ["completed", "failed", "cancelled"]
    if not target:
        return 0
    placeholders = ",".join("?" for _ in target)
    with get_db() as conn:
        cur = conn.execute(
            f"DELETE FROM download_jobs WHERE status IN ({placeholders})",
            target,
        )
        return cur.rowcount
