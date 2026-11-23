import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.config import settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

JOB_COLUMNS = {
    "speed_bps": "REAL",
    "eta_seconds": "REAL",
    "downloaded_bytes": "INTEGER",
    "total_bytes": "INTEGER",
    "output_template": "TEXT",
    "started_at": "TEXT",
    "ended_at": "TEXT",
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(download_jobs)").fetchall()
    }
    for col, col_type in JOB_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE download_jobs ADD COLUMN {col} {col_type}")


def init_db() -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with _connect() as conn:
        conn.executescript(schema)
        _migrate(conn)
        conn.commit()


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
