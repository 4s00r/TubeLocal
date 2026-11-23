from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8000
    download_dir: Path = ROOT_DIR / "downloads"
    db_path: Path = ROOT_DIR / "data" / "app.db"
    max_concurrent_downloads: int = 3
    # No artificial filesize / duration limits
    min_free_disk_bytes: int = 100 * 1024 * 1024  # warn/block if < 100MB free

    # Auto browser cookie read (often fails on Windows Edge/Chrome DPAPI). Prefer cookies_file.
    # Examples: none, edge, chrome, firefox, brave
    cookies_from_browser: str = "none"
    # Netscape cookies.txt from browser extension export (recommended)
    cookies_file: Path = ROOT_DIR / "data" / "youtube.cookies.txt"


settings = Settings()
settings.download_dir.mkdir(parents=True, exist_ok=True)
settings.db_path.parent.mkdir(parents=True, exist_ok=True)
settings.cookies_file.parent.mkdir(parents=True, exist_ok=True)
