import pytest

from league_hub.db import connect, init_db, is_postgres_url, schema_statements, to_postgres_sql


def test_url_detection_and_placeholder_translation():
    assert is_postgres_url("postgresql://u:p@h/d") and is_postgres_url("postgres://u:p@h/d")
    assert not is_postgres_url("league_hub.db") and not is_postgres_url("/data/x.db")
    assert to_postgres_sql("SELECT * FROM t WHERE a = ? AND b = ?") == "SELECT * FROM t WHERE a = %s AND b = %s"


def test_schema_uses_dialect_specific_types():
    pg = "\n".join(schema_statements("postgres"))
    lite = "\n".join(schema_statements("sqlite"))
    assert "BIGSERIAL PRIMARY KEY" in pg and "DOUBLE PRECISION" in pg
    assert "INTEGER PRIMARY KEY" in lite and "REAL" in lite
    assert "{" not in pg and "{" not in lite
    assert "?" not in pg and "%" not in pg  # translation and psycopg both treat these specially


def test_transaction_commits_and_rolls_back(tmp_path):
    path = str(tmp_path / "t.db")
    init_db(path)
    db = connect(path)
    with db.transaction():
        db.execute("INSERT INTO users (yahoo_guid) VALUES (?)", ("A",))
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.execute("INSERT INTO users (yahoo_guid) VALUES (?)", ("B",))
            raise RuntimeError("boom")
    guids = [r["yahoo_guid"] for r in db.execute("SELECT yahoo_guid FROM users ORDER BY id")]
    assert guids == ["A"]


def test_nested_transaction_joins_outer(tmp_path):
    path = str(tmp_path / "t.db")
    init_db(path)
    db = connect(path)
    with pytest.raises(RuntimeError):
        with db.transaction():
            with db.transaction():
                db.execute("INSERT INTO users (yahoo_guid) VALUES (?)", ("A",))
            raise RuntimeError("outer fails")
    assert db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0
    with db.transaction():
        db.execute("INSERT INTO users (yahoo_guid) VALUES (?)", ("C",))
    assert db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 1


def test_production_requires_explicit_database(monkeypatch):
    from league_hub.config import Config
    for k, v in {"APP_ENV": "production", "SECRET_KEY": "s", "YAHOO_CLIENT_ID": "c",
                 "YAHOO_CLIENT_SECRET": "x", "PUBLIC_BASE_URL": "https://e.test"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        Config.from_env()
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    assert Config.from_env().database_path == "postgresql://u:p@h/d"
