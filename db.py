"""SQLite-backed state. Replaces the Airtable Concepts + Content tables."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from config import CONFIG

# SQLite is thread-safe enough for our usage but we keep a lock anyway because
# launchd may fire two posting jobs at the same minute.
_LOCK = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS concepts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    video_url       TEXT NOT NULL,
    source          TEXT NOT NULL,           -- 'youtube' | 'local'
    title           TEXT,
    status          TEXT NOT NULL DEFAULT 'todo',
                                       -- 'todo' | 'processing' | 'processed' | 'failed'
    error           TEXT,
    created_at      TEXT NOT NULL,
    processed_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_concepts_status ON concepts(status);
CREATE INDEX IF NOT EXISTS idx_concepts_created ON concepts(created_at);

CREATE TABLE IF NOT EXISTS content (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id        INTEGER NOT NULL REFERENCES concepts(id),
    title             TEXT NOT NULL,
    caption           TEXT,
    clip_path         TEXT NOT NULL,
    duration_seconds  REAL,
    start_seconds     REAL,
    end_seconds       REAL,
    status            TEXT NOT NULL DEFAULT 'ready',
                                       -- 'ready' | 'posted' | 'failed'
    platform_state    TEXT,                 -- JSON: {"instagram": {"container_id":...}, "tiktok": {...}}
    error             TEXT,
    created_at        TEXT NOT NULL,
    posted_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_content_status ON content(status);
CREATE INDEX IF NOT EXISTS idx_content_created ON content(created_at);

-- ===== Live mode tables =====
CREATE TABLE IF NOT EXISTS channels (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL,           -- 'twitch' | 'youtube' | 'kick' | 'trovo' | 'other'
    channel         TEXT NOT NULL,           -- channel name or URL slug
    url             TEXT NOT NULL,           -- full URL we pass to streamlink
    display_name    TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    UNIQUE(platform, channel)
);

CREATE TABLE IF NOT EXISTS streams (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id       INTEGER NOT NULL REFERENCES channels(id),
    recording_path  TEXT NOT NULL,           -- /path/to/streams/stream_<id>.mp4
    status          TEXT NOT NULL DEFAULT 'recording',
                                       -- 'recording' | 'transcribing' | 'done' | 'failed'
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    duration_seconds REAL,
    error           TEXT
);

CREATE INDEX IF NOT EXISTS idx_streams_status ON streams(status);
CREATE INDEX IF NOT EXISTS idx_streams_channel ON streams(channel_id);

CREATE TABLE IF NOT EXISTS live_clips (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stream_id       INTEGER NOT NULL REFERENCES streams(id),
    content_id      INTEGER REFERENCES content(id),  -- linked after final render
    start_seconds  REAL NOT NULL,
    end_seconds     REAL NOT NULL,
    title           TEXT,
    caption         TEXT,
    reason          TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
                                       -- 'pending' | 'rendering' | 'posted' | 'failed' | 'duplicate'
    captured_at     TEXT NOT NULL,           -- when during the stream we spotted it
    posted_at       TEXT,
    error           TEXT
);

CREATE INDEX IF NOT EXISTS idx_live_clips_stream ON live_clips(stream_id);
CREATE INDEX IF NOT EXISTS idx_live_clips_status ON live_clips(status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(db_path: Path | None = None):
    """Yield a SQLite connection. Commit on success, rollback on error."""
    path = db_path or CONFIG.db_path
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    """Create tables if missing. Idempotent."""
    with _LOCK, connect(db_path) as conn:
        conn.executescript(_SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO concepts (id, video_url, source, status, created_at) "
            "VALUES (-1, 'live', 'live', 'processed', ?)",
            (_now(),),
        )


# --- Concepts -------------------------------------------------------------

def add_concept(video_url: str, source: str, title: str | None = None) -> int:
    """Insert a new video to be clipped. Returns its id."""
    with _LOCK, connect() as conn:
        cur = conn.execute(
            "INSERT INTO concepts (video_url, source, title, status, created_at) "
            "VALUES (?, ?, ?, 'todo', ?)",
            (video_url, source, title, _now()),
        )
        return cur.lastrowid


def list_concepts(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    sql = "SELECT * FROM concepts"
    args: list[Any] = []
    if status:
        sql += " WHERE status = ?"
        args.append(status)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args)]


def fetch_todo_concepts(limit: int = 2) -> list[dict[str, Any]]:
    """Fetch up to `limit` concepts with status='todo', oldest first."""
    with _LOCK, connect() as conn:
        rows = conn.execute(
            "SELECT * FROM concepts WHERE status = 'todo' "
            "ORDER BY id ASC LIMIT ?",
            (limit,),
        ).fetchall()
        # Atomically flip them to 'processing' so a parallel job can't grab them.
        ids = [r["id"] for r in rows]
        if ids:
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"UPDATE concepts SET status = 'processing' WHERE id IN ({placeholders})",
                ids,
            )
        return [dict(r) for r in rows]


def mark_concept_processed(concept_id: int) -> None:
    with _LOCK, connect() as conn:
        conn.execute(
            "UPDATE concepts SET status = 'processed', processed_at = ? WHERE id = ?",
            (_now(), concept_id),
        )


def mark_concept_failed(concept_id: int, error: str) -> None:
    with _LOCK, connect() as conn:
        conn.execute(
            "UPDATE concepts SET status = 'failed', error = ?, processed_at = ? WHERE id = ?",
            (error[:2000], _now(), concept_id),
        )


def reset_processing_concepts() -> int:
    """Re-queue anything stuck in 'processing' (e.g. after a crash). Returns count."""
    with _LOCK, connect() as conn:
        cur = conn.execute(
            "UPDATE concepts SET status = 'todo' WHERE status = 'processing'"
        )
        return cur.rowcount


# --- Content --------------------------------------------------------------

def add_content(
    concept_id: int,
    title: str,
    clip_path: str,
    caption: str,
    duration_seconds: float,
    start_seconds: float,
    end_seconds: float,
) -> int:
    with _LOCK, connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO concepts (id, video_url, source, status, created_at) "
            "VALUES (?, 'auto', 'live', 'processed', ?)",
            (concept_id, _now()),
        )
        cur = conn.execute(
            "INSERT INTO content "
            "(concept_id, title, caption, clip_path, duration_seconds, "
            " start_seconds, end_seconds, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'ready', ?)",
            # Column order: concept_id, title, caption, clip_path, ...
            (concept_id, title, caption, clip_path, duration_seconds,
             start_seconds, end_seconds, _now()),
        )
        return cur.lastrowid


def fetch_random_ready_clip() -> dict[str, Any] | None:
    """Atomically pick one random Ready-to-Post clip and mark it as the
    in-flight one. We don't flip it to 'posted' yet - we flip after success -
    but we wrap the pick in a transaction so two posting jobs can't both grab
    the same clip."""
    with _LOCK, connect() as conn:
        row = conn.execute(
            "SELECT * FROM content WHERE status = 'ready' "
            "ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return dict(row)


def list_ready_content(limit: int = 100) -> list[dict[str, Any]]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM content WHERE status = 'ready' "
            "ORDER BY id DESC LIMIT ?", (limit,)
        )]


def mark_content_posted(content_id: int, platform_state: dict[str, Any]) -> None:
    with _LOCK, connect() as conn:
        conn.execute(
            "UPDATE content SET status = 'posted', platform_state = ?, "
            "posted_at = ? WHERE id = ?",
            (json.dumps(platform_state), _now(), content_id),
        )


def mark_content_failed(content_id: int, error: str) -> None:
    with _LOCK, connect() as conn:
        conn.execute(
            "UPDATE content SET status = 'failed', error = ? WHERE id = ?",
            (error[:2000], content_id),
        )


def get_content(content_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM content WHERE id = ?", (content_id,)).fetchone()
        return dict(row) if row else None


# --- Channels (live mode) -------------------------------------------------

def add_channel(platform: str, channel: str, url: str, display_name: str | None = None) -> int:
    """Insert a channel to watch. Returns its id. Ignores duplicates."""
    with _LOCK, connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO channels (platform, channel, url, display_name, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (platform, channel, url, display_name, _now()),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            # Already exists; return existing id.
            row = conn.execute(
                "SELECT id FROM channels WHERE platform=? AND channel=?",
                (platform, channel),
            ).fetchone()
            return row["id"]


def list_channels(enabled_only: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM channels"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY platform, channel"
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql)]


def remove_channel(channel_id: int) -> None:
    with _LOCK, connect() as conn:
        conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))


def set_channel_enabled(channel_id: int, enabled: bool) -> None:
    with _LOCK, connect() as conn:
        conn.execute("UPDATE channels SET enabled = ? WHERE id = ?",
                     (1 if enabled else 0, channel_id))


# --- Streams --------------------------------------------------------------

def create_stream(channel_id: int, recording_path: str) -> int:
    with _LOCK, connect() as conn:
        cur = conn.execute(
            "INSERT INTO streams (channel_id, recording_path, status, started_at) "
            "VALUES (?, ?, 'recording', ?)",
            (channel_id, recording_path, _now()),
        )
        # recording_path is supplied by caller; update it after we know the id.
        sid = cur.lastrowid
        # The caller passed a path template; replace with the actual id-based path.
        conn.execute(
            "UPDATE streams SET recording_path = ? WHERE id = ?",
            (recording_path.format(stream_id=sid), sid),
        )
        return sid


def update_stream_path(stream_id: int, recording_path: str) -> None:
    with _LOCK, connect() as conn:
        conn.execute("UPDATE streams SET recording_path = ? WHERE id = ?",
                     (recording_path, stream_id))


def mark_stream_ended(stream_id: int, duration_seconds: float | None = None) -> None:
    with _LOCK, connect() as conn:
        conn.execute(
            "UPDATE streams SET status = 'transcribing', ended_at = ?, duration_seconds = ? "
            "WHERE id = ?",
            (_now(), duration_seconds, stream_id),
        )


def mark_stream_done(stream_id: int) -> None:
    with _LOCK, connect() as conn:
        conn.execute("UPDATE streams SET status = 'done' WHERE id = ?", (stream_id,))


def mark_stream_failed(stream_id: int, error: str) -> None:
    with _LOCK, connect() as conn:
        conn.execute(
            "UPDATE streams SET status = 'failed', error = ? WHERE id = ?",
            (error[:2000], stream_id),
        )


def get_stream(stream_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT s.*, c.platform, c.channel, c.url, c.display_name "
            "FROM streams s JOIN channels c ON s.channel_id = c.id "
            "WHERE s.id = ?",
            (stream_id,),
        ).fetchone()
        return dict(row) if row else None


def list_active_streams() -> list[dict[str, Any]]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT s.*, c.platform, c.channel, c.url, c.display_name "
            "FROM streams s JOIN channels c ON s.channel_id = c.id "
            "WHERE s.status IN ('recording', 'transcribing') ORDER BY s.started_at DESC"
        )]


def list_streams_for_cleanup(before_iso: str) -> list[dict[str, Any]]:
    """Streams that ended before `before_iso` and whose recordings we can delete."""
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM streams WHERE status = 'done' AND ended_at < ?",
            (before_iso,),
        )]


# --- Live clips -----------------------------------------------------------

def add_live_clip(stream_id: int, start: float, end: float,
                  title: str, caption: str, reason: str) -> int:
    with _LOCK, connect() as conn:
        cur = conn.execute(
            "INSERT INTO live_clips "
            "(stream_id, start_seconds, end_seconds, title, caption, reason, "
            " status, captured_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
            (stream_id, start, end, title, caption, reason, _now()),
        )
        return cur.lastrowid


def list_live_clips_for_stream(stream_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM live_clips WHERE stream_id = ? ORDER BY start_seconds",
            (stream_id,),
        )]


def list_pending_live_clips(stream_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM live_clips WHERE stream_id = ? AND status = 'pending' "
            "ORDER BY start_seconds",
            (stream_id,),
        )]


def mark_live_clip_rendering(live_clip_id: int) -> None:
    with _LOCK, connect() as conn:
        conn.execute("UPDATE live_clips SET status = 'rendering' WHERE id = ?", (live_clip_id,))


def mark_live_clip_posted(live_clip_id: int, content_id: int) -> None:
    with _LOCK, connect() as conn:
        conn.execute(
            "UPDATE live_clips SET status = 'posted', content_id = ?, posted_at = ? WHERE id = ?",
            (content_id, _now(), live_clip_id),
        )


def mark_live_clip_failed(live_clip_id: int, error: str) -> None:
    with _LOCK, connect() as conn:
        conn.execute(
            "UPDATE live_clips SET status = 'failed', error = ? WHERE id = ?",
            (error[:2000], live_clip_id),
        )


def mark_live_clip_duplicate(live_clip_id: int) -> None:
    with _LOCK, connect() as conn:
        conn.execute("UPDATE live_clips SET status = 'duplicate' WHERE id = ?", (live_clip_id,))
