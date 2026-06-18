"""Strumento di debug: genera prenotazioni casuali per popolare il DB.

La logica e separata dalla GUI cosi da poter essere testata in autonomia.
"""

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import clock, constants, names, reservations, rooms
from .database import get_conn

# Prezzo di default per ogni soluzione (personalizzabile dal tool).
DEFAULT_BOARD_PRICES = {
    "BB": 85.0,
    "RO": 70.0,
    "HB": 110.0,
    "FB": 135.0,
    "RES": 95.0,
}

# Palette sobria usata quando si assegnano colori casuali.
COLOR_PALETTE = (
    "#cfe2f3", "#d9ead3", "#fce5cd", "#f4cccc",
    "#d9d2e9", "#fff2cc", "#d0e0e3", "#ead1dc",
)

COMMENTS = (
    "", "Arrivo in tarda serata", "Richiesta culla", "Cliente abituale",
    "Camera silenziosa", "Allergia alimentare segnalata",
    "Parcheggio richiesto", "Letto aggiuntivo",
)

PLACEMENT_ATTEMPTS = 12  # date alternative provate prima di rinunciare


@dataclass
class SeedConfig:
    count: int
    start: date
    end: date
    min_nights: int
    max_nights: int
    board_prices: dict = field(default_factory=lambda: dict(DEFAULT_BOARD_PRICES))
    random_colors: bool = True
    auto_checkin: bool = True


@dataclass
class SeedResult:
    created: int = 0
    failed: int = 0
    checked_in: int = 0


def _make_guests(first: str, last: str, adults: int, children: int,
                 rng: random.Random) -> list[dict]:
    """Ospiti per il check-in: il primo e l'intestatario, gli altri casuali."""
    people = []
    for i in range(adults):
        people.append(_guest(first if i == 0 else names.random_first_name(rng),
                             last, False, rng))
    for _ in range(children):
        people.append(_guest(names.random_first_name(rng), last, True, rng))
    return people


def _guest(first: str, last: str, child: bool, rng: random.Random) -> dict:
    return {
        "first_name": first,
        "last_name": last,
        "birth_date": names.random_birth_date(rng, child=child),
        "birth_place": names.random_city(rng),
        "document_type": rng.choice(constants.DOCUMENT_TYPES),
        "document_number": names.random_document_number(rng),
        "is_child": child,
    }


def _place_one(cfg: SeedConfig, rng: random.Random):
    """Sceglie data e camera libere e crea una prenotazione completa.

    Ritorna l'id creato, oppure None se non trova spazio.
    """
    span = max((cfg.end - cfg.start).days, 0)
    for _ in range(PLACEMENT_ATTEMPTS):
        nights = rng.randint(cfg.min_nights, cfg.max_nights)
        checkin = cfg.start + timedelta(days=rng.randint(0, span))
        checkout = checkin + timedelta(days=nights)
        free = reservations.available_rooms(checkin, checkout)
        if not free:
            continue

        room = rng.choice(free)
        first = names.random_first_name(rng)
        last = names.random_last_name(rng)
        board = rng.choice(list(cfg.board_prices))
        res_id = reservations.create_reservation(
            first_name=first, last_name=last, room_number=room["number"],
            checkin=checkin, checkout=checkout,
            adults=rng.randint(1, room["max_adults"]),
            children=rng.randint(0, room["max_children"]),
            price_per_night=cfg.board_prices[board], board=board,
            discount=rng.choice([None, None, 5.0, 10.0, 15.0, 20.0]),
            phone=names.random_phone(rng),
            email=names.make_email(first, last, rng),
            color=rng.choice(COLOR_PALETTE) if cfg.random_colors else "",
            comments=rng.choice(COMMENTS))
        return res_id
    return None


def seed_reservations(cfg: SeedConfig, rng: random.Random | None = None) -> SeedResult:
    """Crea fino a `cfg.count` prenotazioni casuali.

    Ogni prenotazione ha durata casuale tra min e max notti, check-in entro
    l'intervallo richiesto e prezzo dato dalla soluzione. Con auto_checkin le
    prenotazioni gia attive oggi vengono anche messe in check-in.
    """
    rng = rng or random.Random()
    result = SeedResult()
    today = clock.today()

    for _ in range(cfg.count):
        res_id = _place_one(cfg, rng)
        if res_id is None:
            result.failed += 1
            continue
        result.created += 1

        if cfg.auto_checkin:
            res = reservations.get(res_id)
            checkin = date.fromisoformat(res["checkin_date"])
            checkout = date.fromisoformat(res["checkout_date"])
            if checkin <= today <= checkout:
                guests = _make_guests(res["first_name"], res["last_name"],
                                      res["adults"], res["children"], rng)
                reservations.do_checkin(res_id, guests)
                result.checked_in += 1
    return result


def clear_all() -> None:
    """Svuota prenotazioni e ospiti e azzera lo stato delle camere.

    Utile per ripartire da un DB pulito durante i test.
    """
    conn = get_conn()
    conn.execute("DELETE FROM reservation_guests")
    conn.execute("DELETE FROM reservations")
    conn.execute("DELETE FROM guests")
    conn.execute("DELETE FROM ledger")
    conn.execute("DELETE FROM mails")
    conn.execute("DELETE FROM reception")
    conn.execute("DELETE FROM blacklist")
    conn.execute("DELETE FROM meals_served")
    conn.execute("UPDATE rooms SET dirty = 0, blocked = 0")
    conn.commit()
