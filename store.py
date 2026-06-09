"""Tiny SQLite-backed state shared by the streamer and the webhook server.

Two things are persisted:
  * session_id -> Slack thread timestamp (the parent message of the thread)
  * the set of event ids already posted, so we never double-post when both
    the live streamer and the webhook backfill see the same session.

SQLite is used (rather than an in-memory dict) precisely because two
processes may touch the same session: the long-running streamer and the
webhook receiver. WAL mode keeps concurrent reads/writes safe. When hosting,
put the DB file on a mounted volume (LOGGER_STATE_DB=/data/state.db) so it
survives redeploys.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager

from config import STATE_DB

_local = threading.local()


def _conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(STATE_DB, timeout=30, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        _local.conn = conn
        _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS threads (
            session_id TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL,
            thread_ts  TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS posted_events (
            session_id TEXT NOT NULL,
            event_id   TEXT NOT NULL,
            PRIMARY KEY (session_id, event_id)
        );
        """
    )
    conn.commit()


@contextmanager
def _locked():
    # Serialize writes within a process; SQLite busy_timeout handles cross-process.
    lock = getattr(_local, "lock", None)
    if lock is None:
        lock = _local.lock = threading.Lock()
    with lock:
        yield


def get_thread(session_id: str) -> tuple[str, str] | None:
    """Return (channel_id, thread_ts) for a session, or None if not yet logged."""
    row = _conn().execute(
        "SELECT channel_id, thread_ts FROM threads WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    return (row[0], row[1]) if row else None


def save_thread(session_id: str, channel_id: str, thread_ts: str) -> None:
    with _locked():
        _conn().execute(
            "INSERT OR REPLACE INTO threads(session_id, channel_id, thread_ts) "
            "VALUES (?, ?, ?)",
            (session_id, channel_id, thread_ts),
        )
        _conn().commit()


def mark_posted(session_id: str, event_id: str) -> bool:
    """Record that an event was posted. Returns True if newly recorded,
    False if it was already posted (caller should skip)."""
    with _locked():
        cur = _conn().execute(
            "INSERT OR IGNORE INTO posted_events(session_id, event_id) VALUES (?, ?)",
            (session_id, event_id),
        )
        _conn().commit()
        return cur.rowcount > 0


def already_posted(session_id: str, event_id: str) -> bool:
    row = _conn().execute(
        "SELECT 1 FROM posted_events WHERE session_id = ? AND event_id = ?",
        (session_id, event_id),
    ).fetchone()
    return row is not None
