"""Web app Flask di HotelAurora: stessa logica hotel/, GUI sostituita dal browser."""

import os

from flask import Flask

from . import session_state, views


def create_app() -> Flask:
    app = Flask(__name__)
    # ponytail: chiave fissa per lo sviluppo locale; in produzione va letta
    # da variabile d'ambiente (le sessioni firmate con una chiave nuova ad
    # ogni riavvio perderebbero il cookie, non i dati: la partita resta sul
    # suo file .db e si ricollega con un nuovo cookie).
    app.secret_key = os.environ.get("HOTEL_SECRET_KEY", "hotelaurora-dev-secret")
    app.register_blueprint(views.bp)
    session_state.start_background_loop()
    return app
