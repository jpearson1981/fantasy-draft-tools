from __future__ import annotations

from urllib.parse import urlencode

import requests

AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"
SCOPE = "fspt-r"  # Fantasy Sports, read-only


class YahooAuthError(Exception):
    """Token missing/expired/revoked; the user must log in with Yahoo again."""


class YahooApiError(Exception):
    def __init__(self, status: int, message: str = ""):
        super().__init__(f"Yahoo API error {status}: {message}")
        self.status = status


class YahooClient:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, session=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.http = session or requests.Session()

    def authorize_url(self, state: str) -> str:
        return AUTH_URL + "?" + urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": SCOPE,
                "state": state,
            }
        )

    def _token_request(self, data: dict) -> dict:
        resp = self.http.post(
            TOKEN_URL,
            data=data,
            auth=(self.client_id, self.client_secret),
            headers={"Accept": "application/json"},
            timeout=20,
        )
        if resp.status_code != 200:
            raise YahooAuthError(f"token endpoint returned {resp.status_code}")
        body = resp.json()
        if "access_token" not in body:
            raise YahooAuthError("token endpoint response had no access_token")
        return body

    def exchange_code(self, code: str) -> dict:
        return self._token_request(
            {"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri}
        )

    def refresh(self, refresh_token: str) -> dict:
        return self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token, "redirect_uri": self.redirect_uri}
        )

    def get(self, path: str, access_token: str) -> dict:
        """GET a Fantasy API resource as JSON. `path` is relative, e.g. 'league/461.l.12345/settings'."""
        resp = self.http.get(
            f"{API_BASE}/{path.lstrip('/')}",
            params={"format": "json"},
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            timeout=30,
        )
        if resp.status_code == 401:
            raise YahooAuthError("Yahoo rejected the access token")
        if resp.status_code != 200:
            raise YahooApiError(resp.status_code, resp.text[:200])
        return resp.json()
