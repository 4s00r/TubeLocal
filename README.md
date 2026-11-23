# TubeLocal

Local-only engineering side project: a small web app for **video metadata preview**, **format selection**, and **SQLite-backed history / job status tracking**. The focus is long-running local jobs, pause/resume, live progress (SSE), and a clean FastAPI + React architecture — bound to `127.0.0.1`.

**Repo:** [github.com/4s00r/TubeLocal](https://github.com/4s00r/TubeLocal)

## Intended use & disclaimer

Use this only with content you own or have permission to use (for example your own uploads, or Creative Commons / explicitly licensed media).

Respect [YouTube’s Terms of Service](https://www.youtube.com/t/terms) and applicable copyright law. This project is for learning and personal tooling experiments. The maintainers do not encourage bypassing platform restrictions or redistributing others’ content.

Private, members-only, and login-gated videos are rejected by the app.

## Stack

- Backend: FastAPI + yt-dlp + SQLite
- Frontend: React (Vite)
- Optional remux: ffmpeg (when merging separate streams)

## Prerequisites

1. **Python 3.11+** and **Node.js 22+**
2. **ffmpeg** on your PATH (optional but useful for stream merge)
   - Windows: `winget install Gyan.FFmpeg` or https://ffmpeg.org/download.html
   - Verify: `ffmpeg -version`
3. Python deps from `backend/requirements.txt` (includes yt-dlp)
4. For some public metadata fetches, browser cookies may be needed to pass bot checks — still **not** for private/gated content

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

Or:

```powershell
.\scripts\start-backend.ps1
.\scripts\start-frontend.ps1
```

Open http://127.0.0.1:5173

## What it demonstrates

- URL normalization for common YouTube link shapes
- Metadata preview (title, channel, duration, thumbnail, available formats)
- Multi-job queue with concurrent workers
- Pause / resume / cancel per job (partial progress kept where possible)
- Live progress over SSE (speed, %, ETA, sizes)
- SQLite history of past links and job status; reuse from history
- Disk-space check before enqueue; interrupted jobs marked paused on restart
- Local-only binding (`127.0.0.1`); streaming to disk without buffering entire files in memory

## Data locations

| Path | Purpose |
|------|---------|
| `downloads/` | Local output files (gitignored) |
| `data/app.db` | Link + job history (gitignored) |

Both are excluded from the repository. Empty folders are kept via `.gitkeep`.

## API (summary)

- `POST /api/preview` — metadata + formats
- `POST /api/downloads` — enqueue a job
- `GET /api/downloads/{id}/events` — SSE progress
- `POST /api/downloads/{id}/pause` / `.../resume` / `.../cancel`
- `GET /api/downloads/{id}/file` — stream a completed local file
- `GET /api/history` — history list
- `POST /api/history/{id}/reuse` — reload preview from history

## Notes

- Default host is localhost only (not exposed on your LAN)
- ffmpeg remux uses stream copy when possible (`-c copy`)

### Bot check / rate limit on Fetch

YouTube may return HTTP 429 or a bot wall even for public pages. Auto cookie reading from Edge/Chrome often fails on Windows.

**Manual cookies.txt (optional):**

1. Install **Get cookies.txt LOCALLY** (Edge or Chrome)
2. Open https://www.youtube.com while logged in
3. Export cookies to:

```text
data/youtube.cookies.txt
```

4. Restart the backend and try Fetch again

Or see `.\scripts\export-youtube-cookies.ps1`. Cookies only help with bot checks; private/members-only content remains rejected.

## Contributing

Developers are welcome — join us to improve the architecture, UX, job reliability, packaging, docs, and tests.

1. Fork [4s00r/TubeLocal](https://github.com/4s00r/TubeLocal)
2. Branch: `git checkout -b feature/your-idea`
3. Open a Pull Request with a short summary

Questions? Open an [Issue](https://github.com/4s00r/TubeLocal/issues).

Thank you for contributing.
