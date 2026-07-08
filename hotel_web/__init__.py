"""Web app Flask di HotelAurora: stessa logica hotel/, GUI sostituita dal browser."""

import os
import secrets
from pathlib import Path

from flask import Flask

from . import session_state, views

# il cookie di sessione porta l'id dell'account loggato: se la chiave con cui
# e' firmato fosse nota (es. hardcoded nel sorgente), chiunque potrebbe
# forgiare un cookie con l'user_id di un altro ed entrare nel suo account
# senza password. Generata una volta e salvata in un file gitignored, cosi
# resta segreta e stabile tra i riavvii (niente logout ad ogni restart).
_SECRET_FILE = Path(__file__).resolve().parent.parent / "secret_key.txt"


def _load_or_create_secret() -> str:
    env = os.environ.get("HOTEL_SECRET_KEY")
    if env:
        return env
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    _SECRET_FILE.write_text(key, encoding="utf-8")
    return key


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = _load_or_create_secret()
    app.register_blueprint(views.bp)
    session_state.start_background_loop()
    return app
