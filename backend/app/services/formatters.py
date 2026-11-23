from __future__ import annotations


def format_duration_human(seconds: float | int | None) -> str | None:
    """Format duration: sec only if < 1 min; else min / hour / days."""
    if seconds is None:
        return None
    try:
        total = max(0, int(round(float(seconds))))
    except (TypeError, ValueError):
        return None

    if total < 60:
        return f"{total} sec"

    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hr")
    if minutes or not parts:
        parts.append(f"{minutes} min")
    return " ".join(parts)


def format_speed(bytes_per_sec: float | int | None) -> str | None:
    """
    Real-time speed:
    - MBps + Mbps when >= 1 Mbps
    - KBps (+ Kbps) when below 1 Mbps
    """
    if bytes_per_sec is None:
        return None
    try:
        bps = float(bytes_per_sec)
    except (TypeError, ValueError):
        return None
    if bps <= 0:
        return None

    bits = bps * 8
    if bits >= 1_000_000:
        return f"{bps / (1024 * 1024):.2f} MBps · {bits / 1_000_000:.2f} Mbps"
    if bps >= 1024:
        return f"{bps / 1024:.1f} KBps · {bits / 1000:.1f} Kbps"
    return f"{bps:.0f} B/s · {bits:.0f} bps"


def compute_eta_seconds(
    *,
    downloaded: int | float | None,
    total: int | float | None,
    speed_bps: float | None,
    started_at_epoch: float | None = None,
    now_epoch: float | None = None,
) -> float | None:
    """ETA from remaining bytes / current speed, with average-speed fallback."""
    if not total or not downloaded:
        return None
    try:
        total_f = float(total)
        downloaded_f = float(downloaded)
    except (TypeError, ValueError):
        return None
    if total_f <= 0 or downloaded_f < 0:
        return None
    remaining = max(0.0, total_f - downloaded_f)
    if remaining <= 0:
        return 0.0

    speed = float(speed_bps) if speed_bps and speed_bps > 0 else None
    if speed is None and started_at_epoch and now_epoch:
        elapsed = max(0.0, now_epoch - started_at_epoch)
        if elapsed > 0 and downloaded_f > 0:
            speed = downloaded_f / elapsed
    if not speed or speed <= 0:
        return None
    return remaining / speed
