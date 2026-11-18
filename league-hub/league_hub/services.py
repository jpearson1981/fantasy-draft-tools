from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from .yahoo.client import YahooAuthError
from .yahoo.parse import parse_league_settings, parse_teams


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upsert_user(db, guid: str) -> int:
    with db.transaction():
        row = db.execute(
            "INSERT INTO users (yahoo_guid, created_at) VALUES (?, ?) "
            "ON CONFLICT(yahoo_guid) DO UPDATE SET yahoo_guid = excluded.yahoo_guid RETURNING id",
            (guid, _now()),
        ).fetchone()
    return row["id"]


def store_tokens(db, cipher, user_id: int, token_body: dict) -> None:
    expires_at = time.time() + float(token_body.get("expires_in", 3600))
    fields = ["access_token_enc = ?", "access_expires_at = ?"]
    values: list = [cipher.encrypt(token_body["access_token"]), expires_at]
    if token_body.get("refresh_token"):
        fields.append("refresh_token_enc = ?")
        values.append(cipher.encrypt(token_body["refresh_token"]))
    values.append(user_id)
    with db.transaction():
        db.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)


def get_access_token(db, cipher, client, user_id: int) -> str:
    row = db.execute(
        "SELECT access_token_enc, access_expires_at, refresh_token_enc FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        raise YahooAuthError("unknown user")
    if row["access_token_enc"] and (row["access_expires_at"] or 0) > time.time() + 60:
        token = cipher.decrypt(row["access_token_enc"])
        if token:
            return token
    refresh = cipher.decrypt(row["refresh_token_enc"]) if row["refresh_token_enc"] else None
    if not refresh:
        raise YahooAuthError("no refresh token on file")
    body = client.refresh(refresh)
    store_tokens(db, cipher, user_id, body)
    return body["access_token"]


def import_yahoo_league(db, user_id: int, client, access_token: str, league_key: str) -> int:
    settings_payload = client.get(f"league/{league_key}/settings", access_token)
    teams_payload = client.get(f"league/{league_key}/teams", access_token)
    norm = parse_league_settings(settings_payload)
    teams = parse_teams(teams_payload)

    with db.transaction():
        league_id = db.execute(
            """
            INSERT INTO leagues (user_id, platform, external_key, external_league_id, season, name,
                num_teams, scoring_type, draft_type, draft_mode, draft_status, roster_json,
                scoring_json, auction_budget, renew_key, settings_raw, imported_at)
            VALUES (?, 'yahoo', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, platform, external_key) DO UPDATE SET
                external_league_id = excluded.external_league_id,
                season = excluded.season, name = excluded.name, num_teams = excluded.num_teams,
                scoring_type = excluded.scoring_type, draft_type = excluded.draft_type,
                draft_mode = excluded.draft_mode, draft_status = excluded.draft_status,
                roster_json = excluded.roster_json, scoring_json = excluded.scoring_json,
                auction_budget = COALESCE(excluded.auction_budget, leagues.auction_budget),
                renew_key = excluded.renew_key, settings_raw = excluded.settings_raw,
                imported_at = excluded.imported_at
            RETURNING id
            """,
            (
                user_id, league_key, norm["league_id"], norm["season"], norm["name"],
                norm["num_teams"], norm["scoring_type"], norm["draft_type"], norm["draft_mode"],
                norm["draft_status"], json.dumps({**norm["roster"], "_spots": norm["roster_spots"],
                                                 "_starters": norm["starters"]}),
                json.dumps(norm["scoring"]), norm["auction_budget"], norm["renew_key"],
                json.dumps({"settings": settings_payload, "teams": teams_payload}), _now(),
            ),
        ).fetchone()["id"]

        for t in teams:
            owner_row_id = None
            if t["owner_external_id"]:
                owner_row_id = db.execute(
                    """
                    INSERT INTO owners (user_id, platform, external_id, display_name)
                    VALUES (?, 'yahoo', ?, ?)
                    ON CONFLICT(user_id, platform, external_id) DO UPDATE SET
                        display_name = COALESCE(excluded.display_name, owners.display_name)
                    RETURNING id
                    """,
                    (user_id, t["owner_external_id"], t["owner_name"]),
                ).fetchone()["id"]
            db.execute(
                """
                INSERT INTO teams (league_id, external_key, name, owner_id, is_mine)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(league_id, external_key) DO UPDATE SET
                    name = excluded.name, owner_id = excluded.owner_id, is_mine = excluded.is_mine
                """,
                (league_id, t["team_key"], t["name"], owner_row_id, 1 if t["is_mine"] else 0),
            )
    return league_id


def league_to_dict(db, row, include_teams: bool = False) -> dict:
    roster = json.loads(row["roster_json"] or "{}")
    spots = roster.pop("_spots", None)
    starters = roster.pop("_starters", None)
    out = {
        "id": row["id"],
        "platform": row["platform"],
        "external_key": row["external_key"],
        "season": row["season"],
        "name": row["name"],
        "num_teams": row["num_teams"],
        "scoring_type": row["scoring_type"],
        "draft_type": row["draft_type"],
        "draft_mode": row["draft_mode"],
        "draft_status": row["draft_status"],
        "roster": roster,
        "roster_spots": spots,
        "starters": starters,
        "auction_budget": row["auction_budget"],
        "keeper_enabled": bool(row["keeper_enabled"]),
        "keeper_rules": json.loads(row["keeper_rules_json"]) if row["keeper_rules_json"] else None,
        "renew_key": row["renew_key"],
        "imported_at": row["imported_at"],
    }
    if include_teams:
        out["scoring"] = json.loads(row["scoring_json"] or "[]")
        out["teams"] = [
            {
                "id": t["id"],
                "external_key": t["external_key"],
                "name": t["name"],
                "owner": t["owner_name"],
                "is_mine": bool(t["is_mine"]),
            }
            for t in db.execute(
                "SELECT t.*, o.display_name AS owner_name FROM teams t "
                "LEFT JOIN owners o ON o.id = t.owner_id WHERE t.league_id = ? ORDER BY t.id",
                (row["id"],),
            )
        ]
    return out
