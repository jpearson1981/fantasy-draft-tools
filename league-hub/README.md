# League Hub (work in progress)

One app, many leagues. Step 1 covers **Yahoo**: log in with Yahoo (OAuth, no passwords stored),
list your NFL leagues across seasons, and save a league's name, roster slots, scoring, draft
type/mode, teams and owners. The existing standalone draft tools on `main` are untouched.

## What you need before it can talk to Yahoo
1. Create a Yahoo app at https://developer.yahoo.com/apps/ (Web Application).
   - API Permissions: **Fantasy Sports -> Read**.
   - Redirect/callback URI: `<PUBLIC_BASE_URL>/auth/yahoo/callback` (must be https).
2. Copy the Client ID and Client Secret into the environment (never into git).
3. Choose where it runs (see "Deploy" below).

## Run locally
```
pip install -r requirements-dev.txt
cp .env.example .env     # fill in values, then export them (or use your shell's dotenv)
python -m pytest         # tests use mocked Yahoo responses
flask --app wsgi run
```
Yahoo only redirects to https URLs, so for local testing expose the dev server through an https
tunnel (e.g. ngrok or cloudflared) and use that URL as `PUBLIC_BASE_URL` and in the Yahoo app.

## Deploy (Render example)
`render.yaml` defines a Docker web service with a 1 GB persistent disk for the SQLite database.
Set `PUBLIC_BASE_URL`, `YAHOO_CLIENT_ID`, `YAHOO_CLIENT_SECRET` in the Render dashboard.
A persistent disk requires a paid Render instance; free instances lose the database on restart.

## Important: not yet verified against live Yahoo
The parsers and tests use sample payloads written from Yahoo's documented structure, not captured
from a real account. After the first real login, check an imported league against the Yahoo site
(roster slots, scoring, draft type/mode, team and owner names). Each import stores the full raw
Yahoo response in `leagues.settings_raw`, so any mismatch can be fixed without re-importing.

## Layout
- `league_hub/yahoo/client.py` OAuth2 + API calls; `yahoo/parse.py` JSON -> neutral model
- `league_hub/services.py` token refresh, league import, upserts
- `league_hub/routes.py` pages, auth and JSON API; `static/index.html` minimal UI
- `tests/` pytest suite with mocked Yahoo

## Roadmap
2. Draft history import and storage (picks, costs, keeper flags), owner history
3. Keeper / franchise rules engine
4. Projections (CSV first; platform APIs later)
5. Live draft tracking (read-only polling)
6. Port Lone Rangers / Dynasty draft boards onto imported league settings
7. ESPN and other platforms as additional adapters
