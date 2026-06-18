"""Gameplay reception: arrivi (check-in) e partenze (check-out) degli ospiti.

Ogni prenotazione ha un orario di arrivo/partenza casuale e deterministico
(per (prenotazione, giorno)) dentro la sua finestra: gli arrivi distribuiti nel
Pomeriggio/Sera, le partenze nella Mattina. Il check-in e per-persona (tutti
spawnano insieme); il check-out e per prenotazione.
"""

import random
from datetime import date, datetime, time, timedelta

from . import clock, guests, names, reservations
from .database import get_conn

rng = random.Random()
ARRIVAL_WINDOW = (15, 23)    # Pomeriggio + Sera
DEPARTURE_WINDOW = (7, 12)   # Mattina
ANGER_HOURS = 1.5            # attesa al check-in oltre cui l'ospite si arrabbia


def _scheduled_time(kind: str, reservation_id: int, day, window):
    """Orario casuale ma stabile (per prenotazione/giorno) dentro la finestra."""
    start, end = window
    r = random.Random(f"{kind}:{reservation_id}:{day.isoformat()}")
    minutes = r.randint(0, (end - start) * 60 - 1)
    return datetime.combine(day, time(start)) + timedelta(minutes=minutes)


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
    """Fa comparire arrivi/partenze quando si raggiunge il loro orario schedulato."""
    if clock.freq_factor() <= 0:   # in pausa: niente
        return
    now = clock.now()
    shift = clock.shift(now)[0]
    today = now.date()
    if shift in ("Pomeriggio", "Sera"):
        for res in _due_arrivals(today):
            if now >= _scheduled_time("arr", res["id"], today, ARRIVAL_WINDOW):
                _spawn_checkin(res, now)
    elif shift == "Mattina":
        from . import guest_state   # import differito: evita il ciclo
        for res in _due_departures(today):
            # niente check-out mentre un ospite della prenotazione e a un pasto
            if (now >= _scheduled_time("dep", res["id"], today, DEPARTURE_WINDOW)
                    and not guest_state.reservation_at_meal(res["id"], now)):
                _spawn_checkout(res, now)


def handle_anger(now) -> int:
    """Chi aspetta il check-in oltre 1,5h si arrabbia: annulla la prenotazione,
    sparisce dalla reception, manda un reclamo e finisce in blacklist. Ritorna
    quanti ospiti si sono arrabbiati."""
    from . import mail   # import differito
    cutoff = (now - timedelta(hours=ANGER_HOURS)).isoformat()
    res_ids = [r["reservation_id"] for r in get_conn().execute(
        "SELECT DISTINCT rc.reservation_id FROM reception rc"
        " JOIN reservations r ON r.id = rc.reservation_id"
        " WHERE rc.kind = 'checkin' AND r.status = 'booked'"
        " AND rc.arrived_at <= ?", (cutoff,)).fetchall()]
    for rid in res_ids:
        res = reservations.get(rid)
        if res is None:
            continue
        mail.spawn_complaint(res)
        conn = get_conn()
        conn.execute("DELETE FROM reception WHERE reservation_id = ?", (rid,))
        conn.execute("UPDATE reservations SET status = 'cancelled' WHERE id = ?",
                     (rid,))
        conn.commit()
        guests.add_to_blacklist(res["first_name"], res["last_name"])
    return len(res_ids)


def pending():
    return get_conn().execute(
        "SELECT rc.*, r.room_number FROM reception rc"
        " JOIN reservations r ON r.id = rc.reservation_id"
        " ORDER BY rc.arrived_at, rc.id").fetchall()


def get(entry_id: int):
    return get_conn().execute(
        "SELECT * FROM reception WHERE id = ?", (entry_id,)).fetchone()


def has_checkout(reservation_id: int) -> bool:
    """La prenotazione e in reception per il check-out (ospiti 'scesi')."""
    return get_conn().execute(
        "SELECT 1 FROM reception WHERE reservation_id = ? AND kind = 'checkout'"
        " LIMIT 1", (reservation_id,)).fetchone() is not None


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
