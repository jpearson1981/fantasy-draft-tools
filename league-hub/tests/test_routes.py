import time

import pytest

from league_hub import create_app
from league_hub.config import Config
from league_hub.crypto import TokenCipher
from league_hub.yahoo.client import YahooAuthError, YahooClient

from .fixtures import USER_LEAGUES, settings_payload, teams_payload


class FakeYahoo(YahooClient):
    def __init__(self):
        super().__init__("cid", "secret", "https://example.test/auth/yahoo/callback")
        self.guid = "GUID_ME"
        self.refresh_calls = 0
        self.fail_refresh = False
        self.paths = []

    def exchange_code(self, code):
        assert code == "good-code"
        return {"access_token": "AT1", "refresh_token": "RT1", "expires_in": 3600,
                "xoauth_yahoo_guid": self.guid}

    def refresh(self, refresh_token):
        self.refresh_calls += 1
        if self.fail_refresh:
            raise YahooAuthError("revoked")
        return {"access_token": "AT2", "refresh_token": "RT2", "expires_in": 3600}

    def get(self, path, access_token):
        self.paths.append(path)
        if path.startswith("users;use_login=1"):
            return USER_LEAGUES
        if path.endswith("/settings"):
            return settings_payload(league_key=path.split("/")[1])
        if path.endswith("/teams"):
            return teams_payload()
        raise AssertionError(path)


@pytest.fixture
def fake():
    return FakeYahoo()


@pytest.fixture
def app(tmp_path, fake):
    cfg = Config(secret_key="test-secret", yahoo_client_id="cid", yahoo_client_secret="secret",
                 public_base_url="https://example.test", database_path=str(tmp_path / "t.db"))
    return create_app(cfg, yahoo_client=fake)


def login(client, fake=None):
    r = client.get("/auth/yahoo/login")
    assert r.status_code == 302 and "api.login.yahoo.com" in r.headers["Location"]
    with client.session_transaction() as s:
        state = s["oauth_state"]
    r = client.get(f"/auth/yahoo/callback?code=good-code&state={state}")
    assert r.status_code == 302


def test_requires_login(app):
    c = app.test_client()
    assert c.get("/api/leagues").status_code == 401
    assert c.get("/api/yahoo/leagues").status_code == 401
    assert c.post("/api/leagues", json={"league_key": "461.l.111"}).status_code == 401
    assert c.get("/api/me").get_json()["logged_in"] is False


def test_callback_rejects_bad_state_and_denial(app):
    c = app.test_client()
    c.get("/auth/yahoo/login")
    assert c.get("/auth/yahoo/callback?code=good-code&state=WRONG").status_code == 400
    assert c.get("/auth/yahoo/callback?code=good-code&state=x").status_code == 400  # state was consumed
    assert "yahoo_denied" in c.get("/auth/yahoo/callback?error=access_denied").headers["Location"]


def test_login_flow_and_tokens_are_encrypted_at_rest(app):
    c = app.test_client()
    login(c)
    assert c.get("/api/me").get_json()["logged_in"] is True
    import sqlite3
    row = sqlite3.connect(app.config["DATABASE_PATH"]).execute(
        "SELECT access_token_enc, refresh_token_enc FROM users").fetchone()
    assert "AT1" not in row[0] and "RT1" not in row[1]
    assert TokenCipher("test-secret").decrypt(row[1]) == "RT1"


def test_list_yahoo_leagues_marks_saved(app):
    c = app.test_client()
    login(c)
    leagues = c.get("/api/yahoo/leagues").get_json()["leagues"]
    assert len(leagues) == 3 and not any(l["saved"] for l in leagues)
    assert c.post("/api/leagues", json={"league_key": "461.l.111"}).status_code == 201
    leagues = c.get("/api/yahoo/leagues").get_json()["leagues"]
    assert {l["league_key"]: l["saved"] for l in leagues}["461.l.111"] is True


def test_import_saves_league_teams_owners_and_is_idempotent(app):
    c = app.test_client()
    login(c)
    r = c.post("/api/leagues", json={"league_key": "461.l.111"})
    body = r.get_json()
    assert body["name"] == "Lone Rangers" and body["num_teams"] == 10
    assert body["roster_spots"] == 15 and body["roster"]["FLEX"] == 1
    assert body["draft_mode"] == "online" and body["draft_type"] == "snake"
    assert body["renew_key"] == "449.l.333"
    assert len(body["teams"]) == 4
    mine = [t for t in body["teams"] if t["is_mine"]]
    assert len(mine) == 1 and mine[0]["name"] == "Gridiron Gurus" and mine[0]["owner"] == "Jeff"

    # Re-import: user edits survive, no duplicates
    lid = body["id"]
    assert c.patch(f"/api/leagues/{lid}", json={"keeper_enabled": True, "auction_budget": 200}).status_code == 200
    c.post("/api/leagues", json={"league_key": "461.l.111"})
    leagues = c.get("/api/leagues").get_json()["leagues"]
    assert len(leagues) == 1
    assert leagues[0]["keeper_enabled"] is True and leagues[0]["auction_budget"] == 200
    assert len(c.get(f"/api/leagues/{lid}").get_json()["teams"]) == 4


def test_invalid_league_key_never_reaches_yahoo(app, fake):
    c = app.test_client()
    login(c)
    for bad in ["../../users", "461.l.111/settings", "abc", "", "461.l.", "461.l.1;x=1"]:
        assert c.post("/api/leagues", json={"league_key": bad}).status_code == 400
    assert fake.paths == []


def test_users_cannot_see_or_change_each_others_leagues(app, fake):
    a = app.test_client()
    login(a)
    lid = a.post("/api/leagues", json={"league_key": "461.l.111"}).get_json()["id"]

    fake.guid = "GUID_OTHER"
    b = app.test_client()
    login(b)
    assert b.get("/api/leagues").get_json()["leagues"] == []
    assert b.get(f"/api/leagues/{lid}").status_code == 404
    assert b.patch(f"/api/leagues/{lid}", json={"name": "hacked"}).status_code == 404
    assert b.delete(f"/api/leagues/{lid}").status_code == 404
    assert a.get(f"/api/leagues/{lid}").get_json()["name"] == "Lone Rangers"


def test_patch_validation_and_delete(app):
    c = app.test_client()
    login(c)
    lid = c.post("/api/leagues", json={"league_key": "461.l.111"}).get_json()["id"]
    assert c.patch(f"/api/leagues/{lid}", json={"draft_mode": "nope"}).status_code == 400
    assert c.patch(f"/api/leagues/{lid}", json={"auction_budget": -5}).status_code == 400
    assert c.patch(f"/api/leagues/{lid}", json={"auction_budget": True}).status_code == 400
    assert c.patch(f"/api/leagues/{lid}", json={"keeper_enabled": "yes"}).status_code == 400
    assert c.patch(f"/api/leagues/{lid}", json={"name": "  "}).status_code == 400
    ok = c.patch(f"/api/leagues/{lid}", json={"draft_mode": "offline", "draft_type": "auction",
                                              "name": "Dynasty"}).get_json()
    assert ok["draft_mode"] == "offline" and ok["draft_type"] == "auction" and ok["name"] == "Dynasty"
    assert c.delete(f"/api/leagues/{lid}").status_code == 200
    assert c.get("/api/leagues").get_json()["leagues"] == []


def test_expired_access_token_is_refreshed_and_revoked_token_asks_for_login(app, fake):
    c = app.test_client()
    login(c)
    import sqlite3
    conn = sqlite3.connect(app.config["DATABASE_PATH"])
    conn.execute("UPDATE users SET access_expires_at = ?", (time.time() - 10,))
    conn.commit()
    assert c.get("/api/yahoo/leagues").status_code == 200
    assert fake.refresh_calls == 1
    conn.execute("UPDATE users SET access_expires_at = ?", (time.time() - 10,))
    conn.commit()
    fake.fail_refresh = True
    r = c.get("/api/yahoo/leagues")
    assert r.status_code == 401 and r.get_json()["error"] == "yahoo_reauth_required"


def test_logout_clears_session(app):
    c = app.test_client()
    login(c)
    c.post("/auth/logout")
    assert c.get("/api/leagues").status_code == 401


def test_index_and_health(app):
    c = app.test_client()
    assert c.get("/healthz").get_json() == {"status": "ok"}
    assert c.get("/").status_code == 200
