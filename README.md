# TubeLocal — Local YouTube Downloader

Local-only web app to preview public YouTube videos, pick a format, and download at original quality (including long Full HD / multi‑GB files). History of pasted links and download status is stored in SQLite for reuse.

**Public videos only.** Private, members-only, and login-gated videos are rejected. Keep downloads for personal use; do not redistribute.

**Repo:** [github.com/4s00r/TubeLocal](https://github.com/4s00r/TubeLocal)

## Stack

- Backend: FastAPI + yt-dlp + SQLite
- Frontend: React (Vite)
- Merge/remux: ffmpeg (required for best video+audio quality)

## Prerequisites

1. **Python 3.11+** and **Node.js 22+** (required JS runtime for YouTube extraction)
2. **ffmpeg** on your PATH (needed to merge separate video/audio streams without re-encoding)
   - Windows: `winget install Gyan.FFmpeg` or download from https://ffmpeg.org/download.html
   - Verify: `ffmpeg -version`
3. yt-dlp + `yt-dlp-ejs` are installed via Python deps
4. A browser logged into YouTube (**Edge/Chrome/Firefox**) so the app can pass bot checks via cookies — still **public videos only**

## Setup

```powershell
git clone https://github.com/4s00r/TubeLocal.git
cd TubeLocal

# Backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt

# Frontend
cd frontend
npm install
cd ..
```

## Run locally

Open two terminals:

**API (127.0.0.1:8000)**

```powershell
.\.venv\Scripts\Activate.ps1
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**UI (127.0.0.1:5173)**

```powershell
cd frontend
npm run dev
```

Or use the helper scripts:

```powershell
.\scripts\start-backend.ps1
.\scripts\start-frontend.ps1
```

Open http://127.0.0.1:5173

## Features

- Paste many YouTube URL shapes → normalized to a single public video
  (`youtube.com/watch`, `youtu.be`, `m.youtube.com`, shorts/embed/live, playlist links with `&list=` / `&index=`)
- Preview title, channel, duration, thumbnail, formats
- Default format: `bestvideo*+bestaudio/best` (merged with ffmpeg, no quality loss)
- **Multi-download list** (IDM-style): add many videos while others run (up to 3 concurrent)
- Pause / resume **each** job (partial files kept; continues with yt-dlp `continuedl`)
- Per-job progress: speed, %, downloaded, total size, remaining, ETA, start/end
- Live progress over SSE; history “Add to list” re-queues a past video
- ETA from remaining bytes ÷ net speed (human: sec / min / hr / days)
- Real-time speed as MBps·Mbps (or KBps when under 1 Mbps)
- No artificial file-size or duration limits; downloads stream to disk
- History of links + latest download status; click to reuse
- Cancel in-flight jobs; disk-space check before download
- Interrupted jobs become **paused** on server restart (can resume)

## Data locations

| Path | Purpose |
|------|---------|
| `downloads/` | Saved video files (gitignored) |
| `data/app.db` | Link + job history (gitignored) |

Both are excluded from the repository. Empty `downloads/` and `data/` folders are kept via `.gitkeep`.

## API (summary)

- `POST /api/preview` — fetch metadata + formats
- `POST /api/downloads` — enqueue download
- `GET /api/downloads/{id}/events` — SSE progress
- `POST /api/downloads/{id}/pause` / `.../resume` / `.../cancel`
- `GET /api/downloads/{id}/file` — stream completed file
- `GET /api/history` — paste/download history
- `POST /api/history/{id}/reuse` — reload preview from history

## Notes

- Bound to `127.0.0.1` by default (not exposed on your LAN)
- Large files are never buffered entirely in memory
- ffmpeg remux uses stream copy when possible (`-c copy`)

### If Fetch says bot check / rate limit

YouTube sometimes returns HTTP 429 or “confirm you’re not a bot” even for **public** videos.  
Auto cookie reading from Edge/Chrome often fails on Windows (DPAPI / app-bound encryption).

**Reliable fix — manual cookies.txt (once):**

1. Install the browser extension **Get cookies.txt LOCALLY** (Edge or Chrome)
2. Open https://www.youtube.com and stay logged in
3. Export cookies and save as:

```text
data/youtube.cookies.txt
```

4. Restart the backend and click Fetch again

Or run `.\scripts\export-youtube-cookies.ps1` for the same instructions (auto-export is optional and may fail).

Cookies only pass the bot wall; the app still rejects private/members-only videos.

## Contributing

Developers are welcome — please join us to help improve TubeLocal.

Ideas that help a lot: better YouTube reliability, UI polish, resume/edge-case fixes, packaging, docs, and tests.

1. Fork [4s00r/TubeLocal](https://github.com/4s00r/TubeLocal)
2. Create a branch: `git checkout -b feature/your-idea`
3. Commit and push your changes
4. Open a Pull Request with a short summary of the improvement

Questions or proposals? Open an [Issue](https://github.com/4s00r/TubeLocal/issues) or start a discussion on the PR.

Thank you for contributing.
