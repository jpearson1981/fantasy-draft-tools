from __future__ import annotations

from flask import Flask, jsonify

from .config import Config
from .crypto import TokenCipher
from .db import close_db, init_db
from .yahoo.client import YahooApiError, YahooAuthError, YahooClient


def create_app(config: Config | None = None, yahoo_client: YahooClient | None = None) -> Flask:
    config = config or Config.from_env()
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config.update(
        SECRET_KEY=config.secret_key,
        DATABASE_PATH=config.database_path,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=config.cookie_secure,
    )
    app.extensions["cipher"] = TokenCipher(config.token_enc_secret or config.secret_key)
    app.extensions["yahoo_client"] = yahoo_client or YahooClient(
        config.yahoo_client_id, config.yahoo_client_secret, config.yahoo_redirect_uri
    )

    init_db(config.database_path)
    app.teardown_appcontext(close_db)

    from .routes import api, auth, pages

    app.register_blueprint(pages)
    app.register_blueprint(auth)
    app.register_blueprint(api)

    @app.errorhandler(YahooAuthError)
    def _reauth(_e):
        return jsonify(error="yahoo_reauth_required", message="Please log in with Yahoo again."), 401

    @app.errorhandler(YahooApiError)
    def _yahoo_down(e):
        return jsonify(error="yahoo_api_error", message=str(e)), 502

    return app
