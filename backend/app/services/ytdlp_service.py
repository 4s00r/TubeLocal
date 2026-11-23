from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

import yt_dlp
from yt_dlp.utils import DownloadError

from app.config import settings

# Path-based IDs (query v= is handled via urlparse)
VIDEO_ID_PATTERNS = [
    re.compile(r"(?:youtube\.com|m\.youtube\.com|music\.youtube\.com|youtube-nocookie\.com)/shorts/([\w-]{11})", re.I),
    re.compile(r"(?:youtube\.com|m\.youtube\.com|music\.youtube\.com|youtube-nocookie\.com)/embed/([\w-]{11})", re.I),
    re.compile(r"(?:youtube\.com|m\.youtube\.com|music\.youtube\.com|youtube-nocookie\.com)/live/([\w-]{11})", re.I),
    re.compile(r"(?:youtube\.com|m\.youtube\.com|music\.youtube\.com|youtube-nocookie\.com)/v/([\w-]{11})", re.I),
    re.compile(r"youtu\.be/([\w-]{11})", re.I),
]

DEFAULT_FORMAT = "bestvideo*+bestaudio/best"


class PublicVideoError(Exception):
    """Raised when a video is not publicly downloadable without auth."""


class YoutubeAccessError(Exception):
    """Raised for rate-limits / bot checks — video may still be public."""


class DownloadInterrupted(RuntimeError):
    """Raised when user pauses or cancels an in-flight download."""

    def __init__(self, reason: str) -> None:
        self.reason = reason  # "paused" | "cancelled"
        super().__init__(f"Download {reason} by user")


def extract_video_id(url: str) -> str | None:
    raw = url.strip()
    if not raw:
        return None
    # Ensure parseable host for relative-ish pastes
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw.lstrip("/")

    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    # Query param v= works for watch / mobile / music
    qs = parse_qs(parsed.query)
    if "v" in qs and qs["v"] and re.fullmatch(r"[\w-]{11}", qs["v"][0]):
        if "youtube" in host or host.endswith("youtu.be") or not host:
            return qs["v"][0]

    for pattern in VIDEO_ID_PATTERNS:
        match = pattern.search(raw)
        if match:
            return match.group(1)
    return None


def is_youtube_url(url: str) -> bool:
    raw = url.strip()
    if not raw:
        return False
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw.lstrip("/")
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host in {"youtu.be", "youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com"}:
        return extract_video_id(url) is not None
    return extract_video_id(url) is not None


def normalize_url(url: str) -> str:
    """Canonical public watch URL (strips playlist/index noise for single-video fetch)."""
    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError(
            "Please paste a valid YouTube URL "
            "(youtube.com, m.youtube.com, youtu.be, shorts, embed, etc.)."
        )
    return f"https://www.youtube.com/watch?v={video_id}"


def ensure_ffmpeg() -> str | None:
    """Resolve ffmpeg binary, including WinGet installs not yet on process PATH."""
    found = shutil.which("ffmpeg")
    if found:
        return found

    candidates: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        links = Path(local) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
        candidates.append(links)
        packages = Path(local) / "Microsoft" / "WinGet" / "Packages"
        if packages.exists():
            candidates.extend(packages.glob("Gyan.FFmpeg*/ffmpeg-*/bin/ffmpeg.exe"))

    for path in candidates:
        if path.is_file():
            return str(path.resolve())
    return None


def _node_runtime() -> dict[str, Any]:
    node = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
    cfg: dict[str, Any] = {}
    if node and Path(node).exists():
        cfg["path"] = str(node)
    return {"node": cfg}


def _cookies_path() -> Path:
    return Path(settings.cookies_file)


def _has_cookies_file() -> bool:
    path = _cookies_path()
    try:
        return path.is_file() and path.stat().st_size > 32
    except OSError:
        return False


def _base_opts() -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "ignoreconfig": True,
        "retries": 5,
        "extractor_retries": 3,
        # Enable Node + bundled EJS challenge solvers (required by modern YouTube)
        "js_runtimes": _node_runtime(),
        "remote_components": ["ejs:npm", "ejs:github"],
        "username": None,
        "password": None,
    }


def export_browser_cookies(browser: str | None = None) -> Path:
    """
    One-time export: copy YouTube cookies from a closed browser into data/youtube.cookies.txt.
    After this, Fetch works even while the browser is open.
    """
    browser_name = (browser or settings.cookies_from_browser or "edge").strip().lower()
    out = _cookies_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    opts = {
        **_base_opts(),
        "cookiesfrombrowser": (browser_name,),
        "cookiefile": str(out),
        "skip_download": True,
    }
    try:
        # Touch YouTube once so the jar is populated / written
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info("https://www.youtube.com/watch?v=jNQXAC9IVRw", download=False)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "permission denied" in msg or "could not copy" in msg:
            raise YoutubeAccessError(
                f"Cannot read {browser_name.title()} cookies — the browser is still locking the file. "
                "Run scripts\\export-youtube-cookies.ps1 from the project root "
                "(it force-closes the browser, then exports). "
                f"Or manually End Task for msedge/chrome in Task Manager, then re-run the script."
            ) from exc
        raise _classify_error(exc) from exc
    if not _has_cookies_file():
        raise YoutubeAccessError(
            f"Cookie export from {browser_name} did not create {out}. "
            f"Fully quit {browser_name.title()} (tray too) and run scripts\\export-youtube-cookies.ps1 again."
        )
    return out


def _classify_error(exc: Exception) -> Exception:
    msg = str(exc).lower()
    browser = settings.cookies_from_browser or "edge"
    cookies = _cookies_path()

    cookie_fail = (
        "could not copy cookie",
        "could not copy chrome cookie",
        "failed to decrypt",
        "dpapi",
        "cookies database",
        "could not find firefox cookies",
        "could not find chromium cookies",
    )
    bot_or_rate = (
        "sign in to confirm you’re not a bot",
        "sign in to confirm you're not a bot",
        "confirm you’re not a bot",
        "confirm you're not a bot",
        "http error 429",
        "too many requests",
        "please wait",
        "not a bot",
    )
    if any(m in msg for m in cookie_fail) or any(m in msg for m in bot_or_rate):
        return YoutubeAccessError(
            "YouTube bot check is active (video can still be public). "
            "Export cookies manually (Edge/Chrome auto-read often fails on Windows): "
            "1) Install extension 'Get cookies.txt LOCALLY'. "
            "2) Open youtube.com while logged in → export cookies. "
            f"3) Save as {cookies}. "
            "4) Restart backend and Fetch. Public videos only."
        )

    private_markers = (
        "private video",
        "this video is private",
        "members-only",
        "members only",
        "login required",
        "age-restricted",
        "age restricted",
        "confirm your age",
        "join this channel",
        "premium members",
    )
    if any(m in msg for m in private_markers):
        return PublicVideoError(
            "This video is not publicly available. "
            "Only public YouTube videos can be downloaded."
        )

    unavailable = (
        "video unavailable",
        "has been removed",
        "is not available",
        "does not exist",
    )
    if any(m in msg for m in unavailable):
        return PublicVideoError(
            "This video is unavailable or was removed. "
            "Only public YouTube videos can be downloaded."
        )
    return exc


def _browser_fallbacks(primary: str) -> list[str]:
    order = [primary, "edge", "chrome", "firefox", "brave", "chromium"]
    seen: set[str] = set()
    out: list[str] = []
    for name in order:
        n = (name or "").strip().lower()
        if n and n not in seen and n not in {"none", "off", "false", "0"}:
            seen.add(n)
            out.append(n)
    return out


def _build_extract_attempts(base: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Prefer saved cookies.txt (works with browser open), then bare, then live browser read.
    """
    attempts: list[dict[str, Any]] = []
    cookies = _cookies_path()

    if _has_cookies_file():
        attempts.append({**base, "cookiefile": str(cookies)})

    # No cookies — sometimes works when YouTube is not rate-limiting
    attempts.append({**base})

    browser = (settings.cookies_from_browser or "edge").strip().lower()
    if browser not in {"", "none", "off", "false", "0"}:
        for name in _browser_fallbacks(browser):
            # Also write jar so next fetches use the file without locking the browser DB
            attempts.append(
                {
                    **base,
                    "cookiesfrombrowser": (name,),
                    "cookiefile": str(cookies),
                }
            )
    return attempts


def _extract_with_ydl(url: str, opts: dict[str, Any], *, download: bool) -> Any:
    """Extract/download with cookie-file / bare / browser fallbacks."""
    attempts = _build_extract_attempts(opts)

    last_exc: Exception | None = None
    preferred_exc: Exception | None = None
    for attempt_opts in attempts:
        for retry in range(3):
            try:
                with yt_dlp.YoutubeDL(attempt_opts) as ydl:
                    return ydl.extract_info(url, download=download)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                msg = str(exc).lower()
                if any(
                    x in msg
                    for x in (
                        "not a bot",
                        "429",
                        "too many requests",
                        "could not copy",
                        "failed to decrypt",
                        "dpapi",
                        "cookies database",
                    )
                ):
                    preferred_exc = preferred_exc or exc
                if "429" in msg or "too many requests" in msg:
                    time.sleep(2.5 * (retry + 1))
                    continue
                # Cookie/profile locked or bot wall → try next source
                if any(
                    x in msg
                    for x in (
                        "cookies",
                        "could not copy",
                        "failed to decrypt",
                        "dpapi",
                        "not a bot",
                        "could not find",
                    )
                ):
                    break
                raise
    assert last_exc is not None
    raise preferred_exc or last_exc


def _format_filesize(fmt: dict[str, Any]) -> int | None:
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    if size is None:
        return None
    try:
        return int(size)
    except (TypeError, ValueError):
        return None


def _human_size(num: int | None) -> str | None:
    if num is None:
        return None
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024
    return None


def serialize_format(fmt: dict[str, Any]) -> dict[str, Any]:
    height = fmt.get("height")
    width = fmt.get("width")
    vcodec = fmt.get("vcodec") or "none"
    acodec = fmt.get("acodec") or "none"
    has_video = vcodec != "none"
    has_audio = acodec != "none"
    if has_video and has_audio:
        kind = "combined"
    elif has_video:
        kind = "video"
    elif has_audio:
        kind = "audio"
    else:
        kind = "other"

    resolution = fmt.get("resolution")
    if not resolution and height:
        resolution = f"{width}x{height}" if width else f"{height}p"
    if not resolution and has_audio and not has_video:
        resolution = "audio only"

    filesize = _format_filesize(fmt)
    note_parts = [
        p
        for p in [
            resolution,
            fmt.get("ext"),
            fmt.get("format_note"),
            kind,
        ]
        if p
    ]
    return {
        "format_id": str(fmt.get("format_id")),
        "ext": fmt.get("ext"),
        "resolution": resolution,
        "fps": fmt.get("fps"),
        "vcodec": vcodec,
        "acodec": acodec,
        "abr": fmt.get("abr"),
        "vbr": fmt.get("vbr"),
        "tbr": fmt.get("tbr"),
        "filesize": filesize,
        "filesize_label": _human_size(filesize),
        "kind": kind,
        "format_note": fmt.get("format_note"),
        "label": " · ".join(note_parts),
    }


def extract_info(url: str) -> dict[str, Any]:
    if not is_youtube_url(url):
        raise ValueError(
            "Please paste a valid YouTube URL "
            "(youtube.com, m.youtube.com, youtu.be, shorts, embed, playlist links OK)."
        )
    url = normalize_url(url)

    opts = {
        **_base_opts(),
        "skip_download": True,
    }
    try:
        info = _extract_with_ydl(url, opts, download=False)
    except DownloadError as exc:
        raise _classify_error(exc) from exc
    except Exception as exc:
        raise _classify_error(exc) from exc

    if not info:
        raise PublicVideoError("Could not fetch video details for a public video.")

    formats = [
        serialize_format(f)
        for f in (info.get("formats") or [])
        if f.get("format_id") and (f.get("vcodec") != "none" or f.get("acodec") != "none")
    ]
    # Prefer higher quality first
    formats.sort(
        key=lambda f: (
            0 if f["kind"] == "combined" else 1 if f["kind"] == "video" else 2,
            f.get("filesize") or 0,
            f.get("fps") or 0,
        ),
        reverse=True,
    )

    # Synthetic "best quality" option for merge download
    best_option = {
        "format_id": DEFAULT_FORMAT,
        "ext": "mp4",
        "resolution": "best available",
        "fps": None,
        "vcodec": "best",
        "acodec": "best",
        "abr": None,
        "vbr": None,
        "tbr": None,
        "filesize": None,
        "filesize_label": None,
        "kind": "best",
        "format_note": "Best video + best audio (merged, no quality loss)",
        "label": "Best quality (video+audio merge)",
    }

    video_id = info.get("id") or extract_video_id(url)
    preview = {
        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else url,
        "original_url": url,
        "video_id": video_id,
        "title": info.get("title"),
        "channel": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration"),
        "thumbnail_url": info.get("thumbnail"),
        "description": (info.get("description") or "")[:500],
        "view_count": info.get("view_count"),
        "formats": [best_option] + formats,
        "default_format_id": DEFAULT_FORMAT,
        "ffmpeg_available": bool(ensure_ffmpeg()),
    }
    if not preview["video_id"]:
        raise PublicVideoError("Could not resolve a public video id from this URL.")
    return preview


ProgressCallback = Callable[[dict[str, Any]], None]
InterruptCheck = Callable[[], str | None]  # "paused" | "cancelled" | None


def download_video(
    *,
    url: str,
    format_id: str,
    output_template: str,
    progress_hook: ProgressCallback | None = None,
    interrupt_check: InterruptCheck | None = None,
) -> dict[str, Any]:
    url = normalize_url(url)
    ffmpeg = ensure_ffmpeg()
    if ("+" in format_id or format_id == DEFAULT_FORMAT) and not ffmpeg:
        raise RuntimeError(
            "ffmpeg is required to merge best video+audio without quality loss. "
            "Install ffmpeg and ensure it is on PATH."
        )

    interrupted: dict[str, str | None] = {"reason": None}

    def hook(d: dict[str, Any]) -> None:
        if interrupt_check:
            reason = interrupt_check()
            if reason:
                interrupted["reason"] = reason
                raise DownloadError(f"Download {reason} by user")
        if progress_hook:
            progress_hook(d)

    opts: dict[str, Any] = {
        **_base_opts(),
        "format": format_id or DEFAULT_FORMAT,
        "outtmpl": output_template,
        "continuedl": True,
        "nopart": False,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 4,
        "merge_output_format": "mp4",
        "progress_hooks": [hook],
    }
    if ffmpeg:
        opts["ffmpeg_location"] = os.path.dirname(ffmpeg) if ffmpeg.lower().endswith(".exe") else ffmpeg

    try:
        info = _extract_with_ydl(url, opts, download=True)
        filepath = None
        if info:
            # Best-effort filename; yt-dlp may remux to another ext
            with yt_dlp.YoutubeDL({**opts, "quiet": True}) as ydl:
                filepath = ydl.prepare_filename(info)
            requested = info.get("requested_downloads") or []
            if requested and requested[0].get("filepath"):
                filepath = requested[0]["filepath"]
            elif info.get("filepath"):
                filepath = info["filepath"]
            # Common post-merge extensions
            if filepath and not Path(filepath).exists():
                for ext in (".mp4", ".mkv", ".webm", ".m4a"):
                    candidate = Path(filepath).with_suffix(ext)
                    if candidate.exists():
                        filepath = str(candidate)
                        break
        return {
            "filepath": filepath,
            "filesize": info.get("filesize") or info.get("filesize_approx") if info else None,
            "title": info.get("title") if info else None,
            "ext": info.get("ext") if info else None,
        }
    except DownloadInterrupted:
        raise
    except DownloadError as exc:
        if interrupted["reason"]:
            raise DownloadInterrupted(interrupted["reason"]) from exc
        msg = str(exc).lower()
        if "paused" in msg:
            raise DownloadInterrupted("paused") from exc
        if "cancelled" in msg:
            raise DownloadInterrupted("cancelled") from exc
        raise _classify_error(exc) from exc
    except Exception as exc:
        if interrupted["reason"]:
            raise DownloadInterrupted(interrupted["reason"]) from exc
        raise _classify_error(exc) from exc
