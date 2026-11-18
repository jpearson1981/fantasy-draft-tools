from __future__ import annotations

import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    yahoo_guid TEXT UNIQUE,
    display_name TEXT,
    refresh_token_enc TEXT,
    access_token_enc TEXT,
    access_expires_at REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- A real-world person who manages one or more fantasy teams. Kept per saving user so the
-- same owner can be followed across seasons/leagues (history features come in a later step).
CREATE TABLE IF NOT EXISTS owners (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    external_id TEXT NOT NULL,
    display_name TEXT,
    UNIQUE (user_id, platform, external_id)
);

CREATE TABLE IF NOT EXISTS leagues (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    external_key TEXT NOT NULL,
    external_league_id TEXT,
    season INTEGER,
    name TEXT NOT NULL,
    num_teams INTEGER,
    scoring_type TEXT,
    draft_type TEXT,            -- 'snake' | 'auction'
    draft_mode TEXT,            -- 'online' | 'offline'
    draft_status TEXT,          -- platform status: predraft / draft / postdraft
    roster_json TEXT,           -- {"QB":1,"RB":2,...,"BN":6}
    scoring_json TEXT,          -- list of {stat_id,name,value,...}
    auction_budget INTEGER,
    renew_key TEXT,             -- previous season's league key on the platform (history chain)
    keeper_enabled INTEGER NOT NULL DEFAULT 0,
    keeper_rules_json TEXT,
    settings_raw TEXT,          -- full platform payload, kept so nothing is lost
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, platform, external_key)
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY,
    league_id INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    external_key TEXT NOT NULL,
    name TEXT,
    owner_id INTEGER REFERENCES owners(id) ON DELETE SET NULL,
    is_mine INTEGER NOT NULL DEFAULT 0,
    UNIQUE (league_id, external_key)
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: str) -> None:
    conn = connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()
