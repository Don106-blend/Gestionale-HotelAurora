"""Salva/ripristina lo stato di gioco in memoria (orologio + config email).

Prenotazioni, budget e mail sono gia su sqlite; qui restano solo i pochi
valori volatili. Tabella KV `settings`: aggiungere un valore = una riga.
"""

import json
from datetime import datetime

from . import clock, mail
from .database import get_conn


def _set(key: str, value) -> None:
    get_conn().execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, json.dumps(value)))


def _get(key: str, default=None):
    row = get_conn().execute(
        "SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def save() -> None:
    _set("clock_sim", clock._sim.isoformat() if clock._sim else None)
    _set("clock_scale", clock.scale)
    _set("clock_running", clock.running)
    _set("mail", vars(mail.config))
    get_conn().commit()


def load() -> None:
    sim = _get("clock_sim")
    clock.set_now(datetime.fromisoformat(sim) if sim else None)
    clock.scale = _get("clock_scale", clock.scale)
    clock.running = _get("clock_running", clock.running)
    for key, value in (_get("mail") or {}).items():
        setattr(mail.config, key, value)
