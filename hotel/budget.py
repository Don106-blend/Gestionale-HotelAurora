"""Bilancio dell'hotel: registro di introiti e perdite.

Ogni movimento e una riga (kind, category, amount). Il saldo e la somma
degli introiti meno le perdite. Aggiungere bollette, stipendi, ecc. =
chiamare record() con una nuova categoria, nessuna modifica allo schema.
"""

from datetime import date

from . import clock
from .database import get_conn

INCOME = "income"
LOSS = "loss"


def record(kind: str, category: str, amount: float, note: str = "",
           day: date | None = None) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO ledger (day, kind, category, amount, note)"
        " VALUES (?, ?, ?, ?, ?)",
        ((day or clock.today()).isoformat(), kind, category,
         round(amount, 2), note))
    conn.commit()


def entries():
    return get_conn().execute(
        "SELECT * FROM ledger ORDER BY day, id").fetchall()


def totals() -> dict:
    rows = get_conn().execute(
        "SELECT kind, COALESCE(SUM(amount), 0) AS tot FROM ledger"
        " GROUP BY kind").fetchall()
    by = {r["kind"]: r["tot"] for r in rows}
    income = by.get(INCOME, 0.0)
    loss = by.get(LOSS, 0.0)
    return {"income": income, "loss": loss, "balance": round(income - loss, 2)}


def rooms_sold() -> int:
    """Stanze vendute finora: un check-out incassato ciascuna (categoria
    'Soggiorno' a bilancio), anche quelli a importo 0 (usciti d'ufficio)."""
    return get_conn().execute(
        "SELECT COUNT(*) FROM ledger WHERE category = 'Soggiorno'").fetchone()[0]
