from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    secret_key: str
    yahoo_client_id: str
    yahoo_client_secret: str
    public_base_url: str  # e.g. https://league-hub.onrender.com (no trailing slash)
    database_path: str
    token_enc_secret: str = ""  # defaults to secret_key when empty
    env: str = "development"

    @property
    def yahoo_redirect_uri(self) -> str:
        return self.public_base_url.rstrip("/") + "/auth/yahoo/callback"

    @property
    def cookie_secure(self) -> bool:
        return self.public_base_url.startswith("https://")

    @classmethod
    def from_env(cls) -> "Config":
        env = os.environ.get("APP_ENV", "development")
        cfg = cls(
            secret_key=os.environ.get("SECRET_KEY", "dev-only-change-me"),
            yahoo_client_id=os.environ.get("YAHOO_CLIENT_ID", ""),
            yahoo_client_secret=os.environ.get("YAHOO_CLIENT_SECRET", ""),
            public_base_url=os.environ.get("PUBLIC_BASE_URL", "http://localhost:5000"),
            database_path=os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PATH", "league_hub.db"),
            token_enc_secret=os.environ.get("TOKEN_ENC_SECRET", ""),
            env=env,
        )
        if env == "production":
            missing = [
                name
                for name, val in [
                    ("SECRET_KEY", cfg.secret_key if cfg.secret_key != "dev-only-change-me" else ""),
                    ("YAHOO_CLIENT_ID", cfg.yahoo_client_id),
                    ("YAHOO_CLIENT_SECRET", cfg.yahoo_client_secret),
                ]
                if not val
            ]
            if missing:
                raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
            if not (os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PATH")):
                raise RuntimeError("Set DATABASE_URL (PostgreSQL) or DATABASE_PATH (SQLite on a persistent disk); "
                                   "a default file would be lost on restart.")
            if not cfg.public_base_url.startswith("https://"):
                raise RuntimeError("PUBLIC_BASE_URL must be https:// in production (Yahoo requires it).")
        return cfg
