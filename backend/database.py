"""
Sherlock Backend — SQLite Database Setup

Uses aiosqlite for async access. Tables are created on startup.
"""
import aiosqlite
import json
from config import DB_PATH


async def get_db() -> aiosqlite.Connection:
    """Get a database connection. Caller must close it."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    """Create tables if they don't exist."""
    db = await get_db()
    try:
        await db.executescript(SCHEMA_SQL)
        await db.commit()
    finally:
        await db.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS interviews (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT 'GOOGLE_MEET',
    expected_candidate_name TEXT,
    expected_candidate_email TEXT,
    status TEXT NOT NULL DEFAULT 'SCHEDULED'
        CHECK (status IN ('SCHEDULED','JOINING','LIVE','ENDED','COMPLETED')),
    meeting_url TEXT,
    ingestion_method TEXT DEFAULT 'EXTENSION',
    started_at TEXT,
    ended_at TEXT,
    identified_participant_id TEXT,
    overall_fraud_score REAL,
    overall_fraud_tier TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS participants (
    id TEXT PRIMARY KEY,
    interview_id TEXT NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    platform_id TEXT,
    current_display_name TEXT,
    display_name_history TEXT NOT NULL DEFAULT '[]',
    first_join_at TEXT,
    last_leave_at TEXT,
    rejoin_count INTEGER NOT NULL DEFAULT 0,
    total_presence_ms INTEGER NOT NULL DEFAULT 0,
    speaking_duration_ms INTEGER NOT NULL DEFAULT 0,
    speaking_ratio REAL NOT NULL DEFAULT 0.0,
    speaking_turn_count INTEGER NOT NULL DEFAULT 0,
    avg_utterance_length_ms REAL NOT NULL DEFAULT 0.0,
    camera_on INTEGER NOT NULL DEFAULT 0,
    camera_on_ratio REAL NOT NULL DEFAULT 0.0,
    candidate_probability REAL NOT NULL DEFAULT 0.0,
    confidence_band TEXT NOT NULL DEFAULT 'UNCERTAIN',
    is_identified_candidate INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_participants_interview
    ON participants(interview_id);

CREATE TABLE IF NOT EXISTS realtime_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interview_id TEXT NOT NULL,
    participant_id TEXT,
    event_type TEXT NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_interview_type
    ON realtime_events(interview_id, event_type, created_at DESC);

CREATE TABLE IF NOT EXISTS confidence_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interview_id TEXT NOT NULL,
    participant_id TEXT NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    candidate_score REAL NOT NULL,
    confidence_band TEXT NOT NULL,
    signal_scores TEXT NOT NULL DEFAULT '{}',
    delta_score REAL NOT NULL DEFAULT 0.0,
    trigger_signal TEXT,
    explanation TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_confidence_interview_participant
    ON confidence_snapshots(interview_id, participant_id, created_at DESC);
"""
