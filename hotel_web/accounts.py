"""Account utenti: login/registrazione.

Le credenziali vivono in un DB dedicato (accounts.db), separato dalle
partite (sessions_data/<user_id>.db): un attaccante che leggesse un
salvataggio di gioco non troverebbe comunque nessuna password. Le password
non sono mai salvate in chiaro, solo l'hash salato (werkzeug.security, gia
una dipendenza di Flask: nessun pacchetto nuovo da installare).

L'id utente (uuid, generato una volta alla registrazione) e anche il nome
del file di salvataggio della partita: e stabile, quindi lo stesso account
ritrova sempre lo stesso hotel da qualunque browser faccia login.
"""

import sqlite3
import uuid
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = Path(__file__).resolve().parent.parent / "accounts.db"

MIN_USERNAME = 3
MIN_PASSWORD = 6


class AccountError(Exception):
    """Registrazione o login non possibile."""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        " id TEXT PRIMARY KEY,"
        " username TEXT NOT NULL UNIQUE COLLATE NOCASE,"
        " password_hash TEXT NOT NULL,"
        " created_at TEXT NOT NULL DEFAULT (datetime('now')))")
    return conn


def register(username: str, password: str):
    """Crea un nuovo account e ritorna la riga utente.

    Solleva AccountError se il nome utente non e valido o e gia in uso.
    """
    username = username.strip()
    if len(username) < MIN_USERNAME:
        raise AccountError(f"Il nome utente deve avere almeno {MIN_USERNAME} caratteri.")
    if len(password) < MIN_PASSWORD:
        raise AccountError(f"La password deve avere almeno {MIN_PASSWORD} caratteri.")
    conn = _conn()
    if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        raise AccountError("Nome utente gia in uso.")
    user_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
        (user_id, username, generate_password_hash(password)))
    conn.commit()
    return get(user_id)


def verify(username: str, password: str):
    """Ritorna la riga utente se le credenziali sono corrette, altrimenti None."""
    row = _conn().execute(
        "SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        return None
    return row


def get(user_id: str):
    return _conn().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
