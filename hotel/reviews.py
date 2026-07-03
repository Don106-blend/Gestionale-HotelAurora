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


def _insert(guest: str, stars: int, text: str) -> None:
    stars = max(0, min(STARS_MAX, stars))
    conn = get_conn()
    conn.execute("INSERT INTO reviews (day, guest, stars, text)"
                 " VALUES (?, ?, ?, ?)",
                 (clock.today().isoformat(), guest, stars, text))
    conn.commit()


def _add(guest: str, stars: int) -> None:
    """Scrittura diretta (debug/test): testo generico della fascia."""
    stars = max(0, min(STARS_MAX, stars))
    _insert(guest, stars,
            random.Random(f"{guest}:{stars}").choice(TEXTS[_band(stars)]))


# testi legati ai receptionist (memorabile / pappamolle / truffatore)
REC_POSITIVE = ("Il receptionist e stato eccezionale, che accoglienza!",
                "Alla reception ci hanno trattati come re. Torneremo.",
                "Check-out indimenticabile, personale d'oro.")
REC_NEGATIVE = ("Al check-out il conto era gonfiato, mi sento truffato.",
                "Prezzi lievitati al momento di pagare. Vergogna.",
                "Il receptionist ci ha spennati, mai piu.")


def leave_checkout(guest: str, stars: int, force: str | None = None) -> bool:
    """Recensione di fine soggiorno. Le recensioni POSITIVE (4-5 stelle)
    escono solo se c'e qualcosa da lodare: un servizio dell'hotel o un
    receptionist (force='positive'/'negative'). Le negative escono sempre.
    Ritorna True se la recensione e stata lasciata."""
    from . import amenities
    r = random.Random(f"{guest}:{stars}")
    if force == "positive":
        _insert(guest, max(stars, 4), r.choice(REC_POSITIVE))
        return True
    if force == "negative":
        _insert(guest, min(stars, 2), r.choice(REC_NEGATIVE))
        return True
    themed = amenities.random_review_text(r, stars)
    if stars >= 4 and themed is None:
        return False          # niente da lodare: l'ospite non recensisce
    _insert(guest, stars, themed or r.choice(TEXTS[_band(stars)]))
    return True


def leave_angry(res) -> None:
    """Chi annulla arrabbiato per l'attesa al check-in lascia 0 stelle."""
    _add(f"{res['first_name']} {res['last_name']}".strip(), 0)


EMOTION_NEG = "Camera con problemi mai risolti: {emo} per tutto il soggiorno."
EMOTION_POS = "Che soggiorno particolare: mi sono sentito {emo} tutto il tempo!"


def leave_emotion(guest: str, emotion: str, positive: bool) -> None:
    """Recensione legata all'emozione lasciata da un problema in camera."""
    template = EMOTION_POS if positive else EMOTION_NEG
    _insert(guest, 5 if positive else 1,
            template.format(emo=emotion.lower()))


def all_reviews(limit: int = 100):
    return get_conn().execute(
        "SELECT * FROM reviews ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def reputation() -> float:
    """Media stelle delle ultime WINDOW recensioni (3.0 senza recensioni:
    un hotel nuovo parte anonimo, ne osannato ne bocciato)."""
    row = get_conn().execute(
        "SELECT AVG(stars) FROM (SELECT stars FROM reviews"
        " ORDER BY id DESC LIMIT ?)", (WINDOW,)).fetchone()
    return round(row[0], 1) if row[0] is not None else 3.0


def demand_factor() -> float:
    """Moltiplicatore di domanda dalla reputazione: 1.0 a 5 stelle, 0.4 a 0."""
    return round(0.4 + 0.12 * reputation(), 2)
