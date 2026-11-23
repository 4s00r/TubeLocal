from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings
from app.db.database import init_db
from app.services.download_worker import worker


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    await worker.start()
    yield
    await worker.stop()


app = FastAPI(
    title="Local YouTube Downloader",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root() -> dict:
    return {
        "name": "Local YouTube Downloader",
        "docs": "/docs",
        "health": "/api/health",
    }
