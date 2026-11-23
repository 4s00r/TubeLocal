CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    video_id TEXT NOT NULL UNIQUE,
    title TEXT,
    channel TEXT,
    duration INTEGER,
    thumbnail_url TEXT,
    last_preview_json TEXT,
    last_preview_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_links_url ON links(url);
CREATE INDEX IF NOT EXISTS idx_links_video_id ON links(video_id);

CREATE TABLE IF NOT EXISTS download_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id INTEGER NOT NULL,
    format_id TEXT NOT NULL,
    format_note TEXT,
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    speed TEXT,
    eta TEXT,
    speed_bps REAL,
    eta_seconds REAL,
    downloaded_bytes INTEGER,
    total_bytes INTEGER,
    phase TEXT,
    filepath TEXT,
    output_template TEXT,
    filesize INTEGER,
    error TEXT,
    started_at TEXT,
    ended_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (link_id) REFERENCES links(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_jobs_link_id ON download_jobs(link_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON download_jobs(status);
