"""Gameplay reception: arrivi (check-in) e partenze (check-out) degli ospiti.

Gli ospiti compaiono in reception a orari casuali (come le mail, sul time tick):
gli arrivi solo di Pomeriggio/Sera, le partenze solo di Mattina, uno per tick.
Il check-in e per-persona (tutti spawnano insieme); il check-out e per prenotazione.
"""

import random
from datetime import date, datetime

from . import clock, names, reservations
from .database import get_conn

rng = random.Random()
SPAWN_PROBABILITY = 0.15   # per tick (~1s) quando il turno e valido


def _due_arrivals(today: date):
    return get_conn().execute(
        "SELECT * FROM reservations r WHERE r.status = 'booked'"
        " AND r.checkin_date <= ? AND NOT EXISTS ("
        "  SELECT 1 FROM reception rc WHERE rc.reservation_id = r.id"
        "  AND rc.kind = 'checkin')",
        (today.isoformat(),)).fetchall()


def _due_departures(today: date):
    return get_conn().execute(
        "SELECT * FROM reservations r WHERE r.status = 'checked_in'"
        " AND r.checkout_date = ? AND NOT EXISTS ("
        "  SELECT 1 FROM reception rc WHERE rc.reservation_id = r.id"
        "  AND rc.kind = 'checkout')",
        (today.isoformat(),)).fetchall()


def _add(reservation_id, kind, first, last, is_child, when):
    get_conn().execute(
        "INSERT INTO reception (reservation_id, kind, first_name, last_name,"
        " is_child, arrived_at) VALUES (?, ?, ?, ?, ?, ?)",
        (reservation_id, kind, first, last, int(is_child), when.isoformat()))


def _spawn_checkin(res, when: datetime):
    last = res["last_name"] or names.random_last_name(rng)
    for i in range(res["adults"]):
        first = res["first_name"] if i == 0 else names.random_first_name(rng)
        _add(res["id"], "checkin", first, last, False, when)
    for _ in range(res["children"]):
        _add(res["id"], "checkin", names.random_first_name(rng), last, True, when)
    get_conn().commit()


def _spawn_checkout(res, when: datetime):
    _add(res["id"], "checkout", res["first_name"], res["last_name"], False, when)
    get_conn().commit()


def maybe_spawn():
    """Genera arrivi/partenze in base al turno e a una probabilita casuale."""
    now = clock.now()
    shift = clock.shift(now)[0]
    prob = SPAWN_PROBABILITY * clock.freq_factor()   # segue la velocita di gioco
    if prob <= 0:
        return
    # al massimo un ospite per tick (trickle): mai tutti insieme
    if shift in ("Pomeriggio", "Sera"):
        due = _due_arrivals(now.date())
        if due and rng.random() < prob:
            _spawn_checkin(rng.choice(due), now)
    elif shift == "Mattina":
        due = _due_departures(now.date())
        if due and rng.random() < prob:
            _spawn_checkout(rng.choice(due), now)


def pending():
    return get_conn().execute(
        "SELECT rc.*, r.room_number FROM reception rc"
        " JOIN reservations r ON r.id = rc.reservation_id"
        " ORDER BY rc.arrived_at, rc.id").fetchall()


def get(entry_id: int):
    return get_conn().execute(
        "SELECT * FROM reception WHERE id = ?", (entry_id,)).fetchone()


def remove(entry_id: int):
    get_conn().execute("DELETE FROM reception WHERE id = ?", (entry_id,))
    get_conn().commit()


def checkin_entry(entry_id: int):
    """Registra l'ospite della riga e la rimuove dalla reception."""
    e = get(entry_id)
    if e is None:
        return
    reservations.checkin_guest(e["reservation_id"], {
        "first_name": e["first_name"], "last_name": e["last_name"],
        "is_child": bool(e["is_child"])})
    remove(entry_id)
