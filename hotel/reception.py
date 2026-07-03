"""Gameplay reception: arrivi (check-in) e partenze (check-out) degli ospiti.

Ogni prenotazione ha un orario di arrivo/partenza casuale e deterministico
(per (prenotazione, giorno)) dentro la sua finestra: gli arrivi distribuiti nel
Pomeriggio/Sera, le partenze nella Mattina. Il check-in e per-persona (tutti
spawnano insieme); il check-out e per prenotazione.
"""

import random
from datetime import date, datetime, time, timedelta

from . import budget, clock, guests, names, reservations
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


def _add(reservation_id, kind, first, last, is_child, when, note=""):
    get_conn().execute(
        "INSERT INTO reception (reservation_id, kind, first_name, last_name,"
        " is_child, arrived_at, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (reservation_id, kind, first, last, int(is_child), when.isoformat(),
         note))


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
    sparisce dalla reception, manda un reclamo e finisce in blacklist. Col
    receptionist 'calmo' di turno nessuno perde la pazienza. Ritorna quanti."""
    from . import mail, staff   # import differiti
    if staff.on_duty_bonus("calmo", now):
        return 0
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
        from . import reviews    # import differito
        reviews.leave_angry(res)
    return len(res_ids)


def _bump_complaints(res_id: int, now=None) -> None:
    """Segna un reclamo sul soggiorno: pesera sulla recensione finale.
    Col 'mediatore' di turno l'ospite si lamenta ma non porta rancore."""
    if now is not None:
        from . import staff
        if staff.on_duty_bonus("mediatore", now):
            return
    get_conn().execute(
        "UPDATE reservations SET complaints = complaints + 1 WHERE id = ?",
        (res_id,))


def serve_meals(now) -> int:
    """Ogni ospite che inizia un pasto consuma 1 unita di cibo, un posto in
    sala (24 per operatore di turno) e un tavolo per il suo gruppo. Se manca
    il cibo ('food'), il personale ('service') o un tavolo ('table') l'ospite
    scende in reception a lamentarsi. Ogni pasto si conta una volta per
    (ospite, giorno, pasto). Ritorna quanti reclami nuovi."""
    from . import guest_state, estate, staff, dining  # differiti: no cicli
    meal = guest_state.current_meal(now)
    if meal is None:
        return 0
    conn = get_conn()
    day = now.date().isoformat()
    capacity = staff.dining_capacity(meal, now.date())
    no_table = {res_id for res_id, _m in dining.seating(now)[2]}
    served_ok = conn.execute(
        "SELECT COUNT(*) FROM meals_served WHERE day = ? AND meal = ?"
        " AND ok = 1", (day, meal)).fetchone()[0]
    complaints = 0
    for g in guests.checked_in_guests():
        if not guest_state.is_eating(g["id"], g["board"], meal, now):
            continue
        # dedup: il pasto viene servito una volta sola
        cur = conn.execute(
            "INSERT OR IGNORE INTO meals_served (guest_id, day, meal)"
            " VALUES (?, ?, ?)", (g["id"], day, meal))
        if cur.rowcount == 0:
            continue
        if g["reservation_id"] in no_table:           # nessun tavolo libero
            kind = "table"
        elif served_ok >= capacity:                   # nessuno che lo serva
            kind = "service"
        elif not estate.consume_food(1):              # dispensa vuota
            kind = "food"
        else:
            served_ok += 1
            staff.add_served(meal, now.date())
            continue
        conn.execute(
            "UPDATE meals_served SET ok = 0 WHERE guest_id = ? AND day = ?"
            " AND meal = ?", (g["id"], day, meal))
        _add(g["reservation_id"], kind, g["first_name"], g["last_name"],
             False, now)
        _bump_complaints(g["reservation_id"], now)
        complaints += 1
    conn.commit()
    return complaints


RS_PROB = 0.15      # probabilita giornaliera che un ospite ordini in camera
RS_PRICE = 15.0     # prezzo del servizio in camera (consuma 1 unita di cibo)


def room_service(now) -> int:
    """Richieste speciali: qualche ospite sveglio ordina in camera (orario
    deterministico per ospite/giorno). Consuma 1 unita di cibo e incassa
    RS_PRICE; a dispensa vuota diventa un reclamo 'food'. Col 'venditore' di
    turno gli ordini raddoppiano. Ritorna i reclami."""
    from . import guest_state, estate, staff   # differiti: evitano il ciclo
    conn = get_conn()
    day = now.date()
    prob = RS_PROB * (2 if staff.on_duty_bonus("venditore", now) else 1)
    complaints = 0
    for g in guests.checked_in_guests():
        r = random.Random(f"rs:{g['id']}:{day.isoformat()}")
        wants = r.random() < prob
        hour = r.randint(11, 22)
        if not wants or now.hour != hour:
            continue
        if guest_state._is_asleep(g["id"], now):
            continue
        cur = conn.execute(     # dedup: al massimo un ordine al giorno
            "INSERT OR IGNORE INTO meals_served (guest_id, day, meal)"
            " VALUES (?, ?, 'RoomService')", (g["id"], day.isoformat()))
        if cur.rowcount == 0:
            continue
        if estate.consume_food(1):
            budget.record(budget.INCOME, "Room service", RS_PRICE,
                          f"Camera {g['room_number']}")
        else:
            conn.execute(
                "UPDATE meals_served SET ok = 0 WHERE guest_id = ? AND day = ?"
                " AND meal = 'RoomService'", (g["id"], day.isoformat()))
            _add(g["reservation_id"], "food", g["first_name"], g["last_name"],
                 False, now)
            _bump_complaints(g["reservation_id"], now)
            complaints += 1
    conn.commit()
    return complaints


def bar_tick(now) -> float:
    """Col 'barista' di turno ogni ospite sveglio puo spendere 5-10 euro al
    bar, al massimo una volta al giorno. Nessuna risorsa consumata."""
    from . import guest_state, staff   # differiti
    if not staff.on_duty_bonus("barista", now):
        return 0.0
    conn = get_conn()
    day = now.date()
    total = 0.0
    for g in guests.checked_in_guests():
        r = random.Random(f"bar:{g['id']}:{day.isoformat()}")
        if r.random() >= 0.4 or now.hour != r.randint(8, 22):
            continue
        if guest_state._is_asleep(g["id"], now):
            continue
        cur = conn.execute(     # dedup: una consumazione al giorno
            "INSERT OR IGNORE INTO meals_served (guest_id, day, meal)"
            " VALUES (?, ?, 'Bar')", (g["id"], day.isoformat()))
        if cur.rowcount == 0:
            continue
        amount = round(r.uniform(5, 10), 2)
        budget.record(budget.INCOME, "Bar", amount,
                      f"Camera {g['room_number']}")
        total += amount
    conn.commit()
    return round(total, 2)


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


def has_food_complaint(reservation_id: int, first: str, last: str) -> bool:
    """Quell'ospite e sceso in reception a lamentarsi (cibo/servizio/tavoli/
    problemi in camera)."""
    return get_conn().execute(
        "SELECT 1 FROM reception WHERE reservation_id = ?"
        " AND kind IN ('food', 'service', 'table', 'problem')"
        " AND first_name = ? AND last_name = ? LIMIT 1",
        (reservation_id, first, last)).fetchone() is not None


def auto_desk(now) -> int:
    """Receptionist 'autonomo' di turno: sbriga da solo check-in e check-out
    in coda (i reclami restano al giocatore). Ritorna quante righe evase."""
    from . import staff   # import differito
    autonomous = [e for e in staff.on_duty_receptionists(now)
                  if e["bonus"] == "autonomo"]
    if not autonomous:
        return 0
    handler = autonomous[0]
    done = 0
    for e in pending():
        if e["kind"] == "checkin":
            checkin_entry(e["id"])
            done += 1
        elif e["kind"] == "checkout":
            res = reservations.get(e["reservation_id"])
            if res is not None and res["status"] == "checked_in":
                reservations.do_checkout(res["id"], receptionist=handler)
            remove(e["id"])
            done += 1
    return done


def remove(entry_id: int):
    get_conn().execute("DELETE FROM reception WHERE id = ?", (entry_id,))
    get_conn().commit()


def checkin_entry(entry_id: int):
    """Registra l'ospite della riga e la rimuove dalla reception. Se al banco
    c'e il receptionist '???', il primo check-in accorcia il soggiorno di una
    notte (prezzo pieno)."""
    from . import staff   # import differito
    e = get(entry_id)
    if e is None:
        return
    res = reservations.get(e["reservation_id"])
    if (res is not None and res["status"] == "booked"
            and staff.on_duty_bonus("misterioso", clock.now())):
        reservations.shorten_stay(e["reservation_id"])
    reservations.checkin_guest(e["reservation_id"], {
        "first_name": e["first_name"], "last_name": e["last_name"],
        "is_child": bool(e["is_child"])})
    remove(entry_id)
