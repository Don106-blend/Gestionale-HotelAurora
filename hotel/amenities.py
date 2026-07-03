"""Servizi dell'hotel e categoria (tier) da 1 a 5 stelle.

Il tier NON sono le recensioni: e la categoria (luxury, ecc.) e dipende da
quante camere hai e da quali zone/servizi hai sbloccato. Ogni servizio compare
anche nelle recensioni degli ospiti. Casino e luci rosse generano entrate
passive; gli upgrade delle camere alzano prezzi (e costi) di tutto l'hotel.
"""

import random

from . import budget, clock, estate, guests
from .database import get_conn, kv_get, kv_set


class AmenityError(estate.EstateError):
    """Acquisto servizio non possibile."""


AMENITIES = {
    "wifi":     {"label": "Wi-Fi", "cost": 1500.0},
    "lobby":    {"label": "Reception decorata", "cost": 2000.0},
    "snackbar": {"label": "Zona ristoro", "cost": 2500.0},
    "meeting":  {"label": "Sala riunioni", "cost": 3000.0},  # funzioni future
    "pool":     {"label": "Piscina", "cost": 8000.0},
    "redlight": {"label": "Zona a luci rosse", "cost": 12000.0},
    "casino":   {"label": "Casino", "cost": 15000.0},
}

# recensioni a tema per ogni servizio: (positiva, negativa)
REVIEW_TEXTS = {
    "wifi": ("Wi-Fi veloce in tutto l'hotel, comodissimo.",
             "Il Wi-Fi va e viene di continuo, frustrante."),
    "lobby": ("La reception decorata fa subito colpo, che eleganza.",
              "Reception tutta lustrini ma servizio cosi cosi."),
    "snackbar": ("Zona ristoro fornitissima, spuntini a ogni ora.",
                 "Zona ristoro mezza vuota, che delusione."),
    "meeting": ("Sala riunioni perfetta per lavorare in trasferta.",
                "Sala riunioni sempre occupata quando serve."),
    "pool": ("La piscina e stupenda, giornate bellissime.",
             "Piscina affollata e rumorosa a tutte le ore."),
    "redlight": ("Di notte l'hotel offre... intrattenimenti particolari.",
                 "Certe zone di notte sono poco raccomandabili."),
    "casino": ("Serata al casino indimenticabile, ci torno!",
               "Al casino ho lasciato meta della vacanza..."),
}

# upgrade delle camere: livello 0 standard, 1 migliorate, 2 luxury.
# Prezzo per notte e costo delle nuove camere x moltiplicatore; il costo
# dell'upgrade scala col numero di camere possedute.
ROOM_LEVELS = {1: {"label": "Camere migliorate", "mult": 1.5,
                   "cost_per_room": 350.0},
               2: {"label": "Camere luxury", "mult": 2.5,
                   "cost_per_room": 700.0}}

# entrate passive per ospite presente, all'ora
CASINO_RATE = 2.0
REDLIGHT_RATE = 4.0     # solo nel turno Notte

AMENITY_REVIEW_PROB = 0.35   # quota di recensioni che citano un servizio


# --- servizi -------------------------------------------------------------------

def owned() -> set:
    return set(kv_get("amenities", []))


def buy(key: str) -> None:
    if key not in AMENITIES:
        raise AmenityError("Servizio sconosciuto.")
    if key in owned():
        raise AmenityError("Servizio gia acquistato.")
    estate._spend(AMENITIES[key]["cost"], AMENITIES[key]["label"])
    kv_set("amenities", sorted(owned() | {key}))


# --- upgrade camere --------------------------------------------------------------

def room_level() -> int:
    return kv_get("room_level", 0)


def price_mult() -> float:
    """Moltiplicatore di prezzo/costo camere dal livello di upgrade."""
    return ROOM_LEVELS.get(room_level(), {"mult": 1.0})["mult"]


def room_upgrade_cost(level: int) -> float:
    n_rooms = get_conn().execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    return round(ROOM_LEVELS[level]["cost_per_room"] * n_rooms, 2)


def buy_room_upgrade(level: int) -> None:
    if level not in ROOM_LEVELS:
        raise AmenityError("Upgrade sconosciuto.")
    if level != room_level() + 1:
        raise AmenityError("Gli upgrade vanno comprati in ordine.")
    estate._spend(room_upgrade_cost(level), ROOM_LEVELS[level]["label"])
    kv_set("room_level", level)


# --- tier (categoria 1-5 stelle) ---------------------------------------------------

TIER_REQS = {
    2: {"rooms": 12, "amenities": {"wifi"}, "level": 0},
    3: {"rooms": 16, "amenities": {"wifi", "snackbar", "lobby"}, "level": 0},
    4: {"rooms": 22, "amenities": {"wifi", "snackbar", "lobby", "pool",
                                   "meeting"}, "level": 1},
    5: {"rooms": 30, "amenities": {"wifi", "snackbar", "lobby", "pool",
                                   "meeting", "casino"}, "level": 2},
}


def _room_count() -> int:
    return get_conn().execute("SELECT COUNT(*) FROM rooms").fetchone()[0]


def _satisfies(req: dict) -> bool:
    return (_room_count() >= req["rooms"] and req["amenities"] <= owned()
            and room_level() >= req["level"])


def tier() -> int:
    t = 1
    for k in (2, 3, 4, 5):
        if _satisfies(TIER_REQS[k]):
            t = k
        else:
            break
    return t


def tier_factor() -> float:
    """Piu stelle di categoria = piu domanda (0.85 a 1 stella, 1.45 a 5)."""
    return round(0.7 + 0.15 * tier(), 2)


def missing_for_next() -> list:
    """Cosa manca per la prossima stella di categoria (vuota a 5 stelle)."""
    t = tier()
    if t >= 5:
        return []
    req = TIER_REQS[t + 1]
    out = []
    if _room_count() < req["rooms"]:
        out.append(f"{req['rooms']} camere (hai {_room_count()})")
    for a in sorted(req["amenities"] - owned()):
        out.append(AMENITIES[a]["label"])
    if room_level() < req["level"]:
        out.append(ROOM_LEVELS[req["level"]]["label"])
    return out


# --- entrate passive ----------------------------------------------------------------

def accrue_passive(now) -> float:
    """Casino sempre, luci rosse solo di Notte: entrate orarie per ospite
    presente. Una sola volta per ora di gioco (ponytail: le ore saltate con
    i time-jump del debug non maturano)."""
    own = owned()
    if not (own & {"casino", "redlight"}):
        return 0.0
    stamp = now.strftime("%Y-%m-%dT%H")
    if kv_get("passive_last") == stamp:
        return 0.0
    kv_set("passive_last", stamp)
    n = len(guests.checked_in_guests())
    if n == 0:
        return 0.0
    total = 0.0
    if "casino" in own:
        from . import staff   # 'fortunato' di turno: il casino rende doppio
        lucky = 2 if staff.on_duty_bonus("fortunato", now) else 1
        amount = round(CASINO_RATE * n * lucky, 2)
        budget.record(budget.INCOME, "Casino", amount, f"{n} ospiti")
        total += amount
    if "redlight" in own and clock.shift(now)[0] == "Notte":
        amount = round(REDLIGHT_RATE * n, 2)
        budget.record(budget.INCOME, "Luci rosse", amount, f"{n} ospiti")
        total += amount
    return round(total, 2)


def random_review_text(rng: random.Random, stars: int):
    """Testo di recensione legato a un servizio posseduto, oppure None."""
    own = sorted(owned())
    if not own or rng.random() >= AMENITY_REVIEW_PROB:
        return None
    good, bad = REVIEW_TEXTS[rng.choice(own)]
    return good if stars >= 3 else bad
