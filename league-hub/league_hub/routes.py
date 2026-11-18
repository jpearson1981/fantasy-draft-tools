from __future__ import annotations

import re
import secrets
from functools import wraps

from flask import (Blueprint, current_app, jsonify, redirect, request, send_from_directory,
                   session)

from . import services
from .db import get_db
from .yahoo.parse import parse_user_leagues

pages = Blueprint("pages", __name__)
auth = Blueprint("auth", __name__, url_prefix="/auth")
api = Blueprint("api", __name__, url_prefix="/api")

LEAGUE_KEY_RE = re.compile(r"^\d+\.l\.\d+$")  # validated before being placed in a Yahoo URL path
EDITABLE_FIELDS = {"draft_mode": {"online", "offline"}, "draft_type": {"snake", "auction"}}


def _client():
    return current_app.extensions["yahoo_client"]


def _cipher():
    return current_app.extensions["cipher"]


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify(error="not_logged_in"), 401
        return fn(*args, **kwargs)

    return wrapper


# ---- pages -----------------------------------------------------------------
@pages.get("/")
def index():
    return send_from_directory(current_app.static_folder, "index.html")


@pages.get("/healthz")
def healthz():
    return jsonify(status="ok")


# ---- auth ------------------------------------------------------------------
@auth.get("/yahoo/login")
def yahoo_login():
    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    return redirect(_client().authorize_url(state))


@auth.get("/yahoo/callback")
def yahoo_callback():
    if request.args.get("error"):
        return redirect("/?error=yahoo_denied")
    expected = session.pop("oauth_state", None)
    if not expected or request.args.get("state") != expected:
        return jsonify(error="bad_state"), 400
    code = request.args.get("code")
    if not code:
        return jsonify(error="missing_code"), 400
    body = _client().exchange_code(code)
    guid = body.get("xoauth_yahoo_guid")
    if not guid:
        return jsonify(error="no_guid_in_token_response"), 502
    db = get_db()
    user_id = services.upsert_user(db, guid)
    services.store_tokens(db, _cipher(), user_id, body)
    session.clear()
    session["user_id"] = user_id
    return redirect("/")


@auth.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


# ---- api -------------------------------------------------------------------
@api.get("/me")
def me():
    uid = session.get("user_id")
    return jsonify(logged_in=bool(uid), user_id=uid)


@api.get("/yahoo/leagues")
@login_required
def yahoo_leagues():
    db = get_db()
    uid = session["user_id"]
    token = services.get_access_token(db, _cipher(), _client(), uid)
    payload = _client().get("users;use_login=1/games;game_codes=nfl/leagues", token)
    leagues = parse_user_leagues(payload)
    saved = {r["external_key"] for r in db.execute(
        "SELECT external_key FROM leagues WHERE user_id = ? AND platform = 'yahoo'", (uid,))}
    for lg in leagues:
        lg["saved"] = lg["league_key"] in saved
    return jsonify(leagues=leagues)


@api.post("/leagues")
@login_required
def save_league():
    data = request.get_json(silent=True) or {}
    league_key = str(data.get("league_key", ""))
    if not LEAGUE_KEY_RE.match(league_key):
        return jsonify(error="invalid_league_key"), 400
    db = get_db()
    uid = session["user_id"]
    token = services.get_access_token(db, _cipher(), _client(), uid)
    league_id = services.import_yahoo_league(db, uid, _client(), token, league_key)
    row = db.execute("SELECT * FROM leagues WHERE id = ?", (league_id,)).fetchone()
    return jsonify(services.league_to_dict(db, row, include_teams=True)), 201


@api.get("/leagues")
@login_required
def list_leagues():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM leagues WHERE user_id = ? ORDER BY season DESC, name", (session["user_id"],)
    ).fetchall()
    return jsonify(leagues=[services.league_to_dict(db, r) for r in rows])


def _own_league(db, league_id: int):
    return db.execute(
        "SELECT * FROM leagues WHERE id = ? AND user_id = ?", (league_id, session["user_id"])
    ).fetchone()


@api.get("/leagues/<int:league_id>")
@login_required
def get_league(league_id: int):
    db = get_db()
    row = _own_league(db, league_id)
    if row is None:
        return jsonify(error="not_found"), 404
    return jsonify(services.league_to_dict(db, row, include_teams=True))


@api.patch("/leagues/<int:league_id>")
@login_required
def update_league(league_id: int):
    db = get_db()
    row = _own_league(db, league_id)
    if row is None:
        return jsonify(error="not_found"), 404
    data = request.get_json(silent=True) or {}
    sets, values = [], []
    for field, allowed in EDITABLE_FIELDS.items():
        if field in data:
            if data[field] not in allowed:
                return jsonify(error=f"invalid_{field}"), 400
            sets.append(f"{field} = ?")
            values.append(data[field])
    if "auction_budget" in data:
        b = data["auction_budget"]
        if b is not None and (not isinstance(b, int) or isinstance(b, bool) or not 1 <= b <= 10000):
            return jsonify(error="invalid_auction_budget"), 400
        sets.append("auction_budget = ?")
        values.append(b)
    if "keeper_enabled" in data:
        if not isinstance(data["keeper_enabled"], bool):
            return jsonify(error="invalid_keeper_enabled"), 400
        sets.append("keeper_enabled = ?")
        values.append(1 if data["keeper_enabled"] else 0)
    if "name" in data:
        name = str(data["name"]).strip()
        if not name or len(name) > 120:
            return jsonify(error="invalid_name"), 400
        sets.append("name = ?")
        values.append(name)
    if sets:
        with db:
            db.execute(f"UPDATE leagues SET {', '.join(sets)} WHERE id = ?", [*values, league_id])
    row = _own_league(db, league_id)
    return jsonify(services.league_to_dict(db, row, include_teams=True))


@api.delete("/leagues/<int:league_id>")
@login_required
def delete_league(league_id: int):
    db = get_db()
    if _own_league(db, league_id) is None:
        return jsonify(error="not_found"), 404
    with db:
        db.execute("DELETE FROM leagues WHERE id = ?", (league_id,))
    return jsonify(ok=True)
