"""Recensioni e reputazione dell'hotel.

A ogni check-out l'ospite lascia una recensione: 5 stelle meno 2 per ogni
reclamo subito nel soggiorno (-1 se non ha pagato). Chi se ne va arrabbiato
dal check-in lascia 0 stelle. La reputazione e la media delle ultime 20
recensioni e muove la domanda di nuove prenotazioni.
"""

import random

from . import clock
from .database import get_conn

STARS_MAX = 5
WINDOW = 20            # recensioni considerate per la reputazione

# template per fascia di stelle; {name} = ospite
TEXTS = {
    5: ("Soggiorno perfetto, torneremo di sicuro!",
        "Personale gentile e tutto impeccabile. Consigliato.",
        "Esperienza ottima, camera pulita e servizio puntuale."),
    3: ("Soggiorno nella media, qualche intoppo qua e la.",
        "Carino, ma c'e margine per migliorare.",
        "Non male, pero ci aspettavamo qualcosa in piu."),
    1: ("Diversi problemi durante il soggiorno, deluso.",
        "Servizio scadente, difficile tornare.",
        "Troppi disagi per il prezzo pagato."),
    0: ("Esperienza pessima, mai piu in questo hotel.",
        "Da evitare: un disastro dall'inizio alla fine.",
        "Zero stelle se si potesse. Inaccettabile."),
}


def _band(stars: int) -> int:
    if stars >= 5:
        return 5
    if stars >= 3:
        return 3
    if stars >= 1:
        return 1
    return 0


def _add(guest: str, stars: int) -> None:
    stars = max(0, min(STARS_MAX, stars))
    text = random.Random(f"{guest}:{stars}").choice(TEXTS[_band(stars)])
    conn = get_conn()
    conn.execute("INSERT INTO reviews (day, guest, stars, text)"
                 " VALUES (?, ?, ?, ?)",
                 (clock.today().isoformat(), guest, stars, text))
    conn.commit()


def leave_review(res, paid: bool = True) -> None:
    """Recensione a fine soggiorno: parte da 5, -2 a reclamo, -1 se non paga."""
    stars = STARS_MAX - 2 * res["complaints"] - (0 if paid else 1)
    _add(f"{res['first_name']} {res['last_name']}".strip(), stars)


def leave_angry(res) -> None:
    """Chi annulla arrabbiato per l'attesa al check-in lascia 0 stelle."""
    _add(f"{res['first_name']} {res['last_name']}".strip(), 0)


def all_reviews(limit: int = 100):
    return get_conn().execute(
        "SELECT * FROM reviews ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def reputation() -> float:
    """Media stelle delle ultime WINDOW recensioni (5.0 senza recensioni)."""
    row = get_conn().execute(
        "SELECT AVG(stars) FROM (SELECT stars FROM reviews"
        " ORDER BY id DESC LIMIT ?)", (WINDOW,)).fetchone()
    return round(row[0], 1) if row[0] is not None else 5.0


def demand_factor() -> float:
    """Moltiplicatore di domanda dalla reputazione: 1.0 a 5 stelle, 0.4 a 0."""
    return round(0.4 + 0.12 * reputation(), 2)
