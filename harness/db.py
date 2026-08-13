"""SQLite storage for the MDMP harness.

Single file database, no ORM, no migrations framework. The schema is created
on first run and additively patched on later runs so an existing plan database
survives an upgrade of the harness.
"""

import json
import os
import sqlite3
import threading
import time

_LOCAL = threading.local()
_DB_PATH = None


def init(path):
    """Point the module at a database file and make sure the schema exists."""
    global _DB_PATH
    _DB_PATH = os.path.abspath(path)
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = connect()
    _create_schema(conn)
    conn.commit()
    return _DB_PATH


def path():
    return _DB_PATH


def connect():
    """One connection per thread; the HTTP server is threaded."""
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        conn = sqlite3.connect(_DB_PATH, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        _LOCAL.conn = conn
    return conn


def now():
    return int(time.time())


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    display_name  TEXT NOT NULL,
    pw_hash       TEXT NOT NULL,
    pw_salt       TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'planner',
    staff_section TEXT NOT NULL DEFAULT 's3',
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    last_seen  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    flow_id     TEXT NOT NULL DEFAULT 'mdmp_opord',
    phase       TEXT NOT NULL DEFAULT 'planning',
    created_by  INTEGER NOT NULL REFERENCES users(id),
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL,
    archived    INTEGER NOT NULL DEFAULT 0,
    meta_json   TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS plan_members (
    plan_id  INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role     TEXT NOT NULL DEFAULT 'planner',
    PRIMARY KEY (plan_id, user_id)
);

-- One row per (plan, field). Superseded rows are kept for the audit trail.
CREATE TABLE IF NOT EXISTS answers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id     INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    step_key    TEXT NOT NULL,
    field_key   TEXT NOT NULL,
    value_json  TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'selected',  -- selected|written|edited|auto
    option_id   TEXT,
    dep_hash    TEXT NOT NULL DEFAULT '',
    author_id   INTEGER REFERENCES users(id),
    created_at  INTEGER NOT NULL,
    current     INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_answers_current
    ON answers(plan_id, field_key, current);

CREATE TABLE IF NOT EXISTS optionsets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id      INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    step_key     TEXT NOT NULL,
    field_key    TEXT NOT NULL,
    dep_hash     TEXT NOT NULL DEFAULT '',
    provider     TEXT NOT NULL DEFAULT 'offline',
    options_json TEXT NOT NULL,
    created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_optionsets_field
    ON optionsets(plan_id, field_key, created_at);

-- OPORD paragraphs and annexes during the staff production phase.
CREATE TABLE IF NOT EXISTS sections (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id    INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    key        TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'paragraph',  -- paragraph|annex
    title      TEXT NOT NULL,
    body       TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'not_started',
    owner_id   INTEGER REFERENCES users(id),
    owner_hint TEXT NOT NULL DEFAULT '',
    updated_by INTEGER REFERENCES users(id),
    updated_at INTEGER NOT NULL,
    UNIQUE (plan_id, key)
);

CREATE TABLE IF NOT EXISTS activity (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id   INTEGER REFERENCES plans(id) ON DELETE CASCADE,
    user_id   INTEGER REFERENCES users(id),
    ts        INTEGER NOT NULL,
    kind      TEXT NOT NULL,
    detail    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_activity_plan ON activity(plan_id, id);

CREATE TABLE IF NOT EXISTS docs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    path       TEXT UNIQUE NOT NULL,
    title      TEXT NOT NULL,
    sha        TEXT NOT NULL,
    n_chunks   INTEGER NOT NULL DEFAULT 0,
    added_at   INTEGER NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
    body,
    doc_id UNINDEXED,
    ord UNINDEXED,
    title,
    tokenize = 'porter unicode61'
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _create_schema(conn):
    conn.executescript(SCHEMA)


# ---------------------------------------------------------------- helpers --

def q(sql, args=()):
    """Query returning a list of dict rows."""
    cur = connect().execute(sql, args)
    return [dict(r) for r in cur.fetchall()]


def q1(sql, args=()):
    rows = q(sql, args)
    return rows[0] if rows else None


def ex(sql, args=()):
    conn = connect()
    cur = conn.execute(sql, args)
    conn.commit()
    return cur.lastrowid


def setting(key, default=None):
    row = q1("SELECT value FROM settings WHERE key=?", (key,))
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except (ValueError, TypeError):
        return row["value"]


def set_setting(key, value):
    ex("INSERT INTO settings(key,value) VALUES(?,?) "
       "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
       (key, json.dumps(value)))


def log(plan_id, user_id, kind, detail=""):
    ex("INSERT INTO activity(plan_id,user_id,ts,kind,detail) VALUES(?,?,?,?,?)",
       (plan_id, user_id, now(), kind, detail))
