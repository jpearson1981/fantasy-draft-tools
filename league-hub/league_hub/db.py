"""Database access that works on SQLite (local/dev, or a hosted disk) and PostgreSQL (hosted).

Pick the backend with the DATABASE_URL environment variable:
  * postgresql://user:pass@host/dbname  -> PostgreSQL (psycopg 3)
  * anything else (a file path)         -> SQLite

SQL is written once with `?` placeholders and translated for PostgreSQL. Do not put a literal
`?` or `%` inside SQL text; pass such values as parameters.

Both backends run in autocommit mode. Group multi-statement writes with `db.transaction()`.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from flask import current_app, g

# Schema is a list of statements with two dialect tokens: {pk} and {dbl}.
_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id {pk},
        yahoo_guid TEXT UNIQUE,
        display_name TEXT,
        refresh_token_enc TEXT,
        access_token_enc TEXT,
        access_expires_at {dbl},
        created_at TEXT
    )""",
    # A real person who manages teams. Kept per saving user so one owner can be followed across
    # seasons and leagues (history features come in a later step).
    """CREATE TABLE IF NOT EXISTS owners (
        id {pk},
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        platform TEXT NOT NULL,
        external_id TEXT NOT NULL,
        display_name TEXT,
        UNIQUE (user_id, platform, external_id)
    )""",
    # draft_type: snake|auction. draft_mode: online|offline. roster_json: slot counts.
    # renew_key: the previous season's league key on the platform (history chain).
    # settings_raw: the full platform payload, kept so nothing is lost.
    """CREATE TABLE IF NOT EXISTS leagues (
        id {pk},
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        platform TEXT NOT NULL,
        external_key TEXT NOT NULL,
        external_league_id TEXT,
        season INTEGER,
        name TEXT NOT NULL,
        num_teams INTEGER,
        scoring_type TEXT,
        draft_type TEXT,
        draft_mode TEXT,
        draft_status TEXT,
        roster_json TEXT,
        scoring_json TEXT,
        auction_budget INTEGER,
        renew_key TEXT,
        keeper_enabled INTEGER NOT NULL DEFAULT 0,
        keeper_rules_json TEXT,
        settings_raw TEXT,
        imported_at TEXT,
        UNIQUE (user_id, platform, external_key)
    )""",
    """CREATE TABLE IF NOT EXISTS teams (
        id {pk},
        league_id BIGINT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
        external_key TEXT NOT NULL,
        name TEXT,
        owner_id BIGINT REFERENCES owners(id) ON DELETE SET NULL,
        is_mine INTEGER NOT NULL DEFAULT 0,
        UNIQUE (league_id, external_key)
    )""",
]
_DIALECT_TOKENS = {
    "sqlite": {"pk": "INTEGER PRIMARY KEY", "dbl": "REAL"},
    # DOUBLE PRECISION, not REAL: PostgreSQL's REAL is 4 bytes and would corrupt epoch seconds.
    "postgres": {"pk": "BIGSERIAL PRIMARY KEY", "dbl": "DOUBLE PRECISION"},
}


def is_postgres_url(target: str) -> bool:
    return target.startswith(("postgres://", "postgresql://"))


def schema_statements(dialect: str) -> list[str]:
    return [s.format(**_DIALECT_TOKENS[dialect]) for s in _SCHEMA]


def to_postgres_sql(sql: str) -> str:
    return sql.replace("?", "%s")


class Database:
    def __init__(self, conn, dialect: str):
        self.conn = conn
        self.dialect = dialect
        self._depth = 0

    def execute(self, sql: str, params=()):
        if self.dialect == "postgres":
            sql = to_postgres_sql(sql)
        return self.conn.execute(sql, tuple(params))

    @contextmanager
    def transaction(self):
        """Commit on success, roll back on any exception. Nested use joins the outer one."""
        if self._depth:
            self._depth += 1
            try:
                yield self
            finally:
                self._depth -= 1
            return
        self._depth = 1
        try:
            if self.dialect == "postgres":
                with self.conn.transaction():
                    yield self
            else:
                self.conn.execute("BEGIN")
                try:
                    yield self
                except BaseException:
                    self.conn.execute("ROLLBACK")
                    raise
                else:
                    self.conn.execute("COMMIT")
        finally:
            self._depth = 0

    def close(self) -> None:
        self.conn.close()


def connect(target: str) -> Database:
    if is_postgres_url(target):
        import psycopg  # imported lazily so SQLite-only setups do not need it
        from psycopg.rows import dict_row

        url = "postgresql://" + target.split("://", 1)[1]  # accept the postgres:// alias
        # prepare_threshold=None keeps this working behind pgbouncer-style poolers (e.g. Neon's pooled URL).
        conn = psycopg.connect(url, autocommit=True, row_factory=dict_row, prepare_threshold=None)
        return Database(conn, "postgres")
    conn = sqlite3.connect(target, isolation_level=None)  # autocommit; transactions are explicit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return Database(conn, "sqlite")


def init_db(target: str) -> None:
    db = connect(target)
    try:
        if db.dialect == "sqlite":
            db.execute("PRAGMA journal_mode=WAL")
        with db.transaction():
            for stmt in schema_statements(db.dialect):
                db.execute(stmt)
    finally:
        db.close()


def get_db() -> Database:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()
