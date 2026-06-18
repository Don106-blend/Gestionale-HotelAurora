"""Prenotazioni: creazione, disponibilita, check-in e check-out."""

from datetime import date

from . import billing, budget, clock, constants, guests, rooms
from .database import get_conn


class ValidationError(Exception):
    """Errore bloccante nei dati di una prenotazione."""


def make_code(adults: int, children: int, booking_date: date, board: str) -> str:
    # @gg/mm = giorno in cui arriva la prenotazione, non il check-in
    pax = adults + children
    return (f"{pax}pax | @{booking_date.strftime('%d/%m')} | {board}"
            f" | {constants.PAYMENT_DEFAULT}")


def is_room_available(room_number: int, checkin: date, checkout: date,
                      exclude_id: int | None = None) -> bool:
    """Camera libera nell'intervallo [checkin, checkout).

    Il giorno di check-out la camera torna prenotabile per nuovi arrivi.
    """
    query = ("SELECT COUNT(*) FROM reservations"
             " WHERE room_number = ? AND status IN ('booked', 'checked_in')"
             " AND checkin_date < ? AND checkout_date > ?")
    params: list = [room_number, checkout.isoformat(), checkin.isoformat()]
    if exclude_id is not None:
        query += " AND id != ?"
        params.append(exclude_id)
    return get_conn().execute(query, params).fetchone()[0] == 0


def available_rooms(checkin: date, checkout: date):
    """Camere esistenti, non bloccate e libere nel periodo richiesto."""
    return [r for r in rooms.all_rooms()
            if not r["blocked"]
            and is_room_available(r["number"], checkin, checkout)]


def capacity_warning(room_number: int, adults: int, children: int) -> str | None:
    """Messaggio di avviso se i pax superano la capienza, altrimenti None."""
    room = rooms.get_room(room_number)
    if room is None:
        return None
    problems = []
    if adults > room["max_adults"]:
        problems.append(f"{adults} adulti (max {room['max_adults']})")
    if children > room["max_children"]:
        problems.append(f"{children} bambini (max {room['max_children']})")
    if not problems:
        return None
    return (f"La camera {room_number} supera la capienza: "
            + ", ".join(problems) + ".")


def create_reservation(*, first_name: str, last_name: str, room_number: int,
                       checkin: date, checkout: date, adults: int,
                       children: int, price_per_night: float, board: str,
                       discount: float | None, phone: str, email: str,
                       color: str, comments: str) -> int:
    first_name, last_name = first_name.strip(), last_name.strip()
    if not first_name and not last_name:
        raise ValidationError("Inserire almeno il nome o il cognome.")
    if checkout <= checkin:
        raise ValidationError("La data di check-out deve essere successiva al check-in.")
    if board not in constants.BOARDS:
        raise ValidationError(f"Soluzione '{board}' non valida.")
    if adults < 1:
        raise ValidationError("Serve almeno un adulto.")

    room = rooms.get_room(room_number)
    if room is None:
        raise ValidationError(f"La camera {room_number} non esiste.")
    if room["blocked"]:
        raise ValidationError(f"La camera {room_number} e bloccata.")
    if not is_room_available(room_number, checkin, checkout):
        raise ValidationError(
            f"La camera {room_number} non e libera nel periodo scelto.")

    conn = get_conn()
    booking_date = clock.today()
    cur = conn.execute(
        "INSERT INTO reservations (code, room_number, first_name, last_name,"
        " checkin_date, checkout_date, adults, children, price_per_night,"
        " board, discount, phone, email, color, comments, payment, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (make_code(adults, children, booking_date, board), room_number,
         first_name, last_name, checkin.isoformat(), checkout.isoformat(),
         adults, children, price_per_night, board, discount,
         phone.strip(), email.strip(), color, comments.strip(),
         constants.PAYMENT_DEFAULT, booking_date.isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def get(res_id: int):
    return get_conn().execute(
        "SELECT * FROM reservations WHERE id = ?", (res_id,)).fetchone()


def current_for_room(room_number: int):
    """Prenotazione checked-in della camera, se presente."""
    return get_conn().execute(
        "SELECT * FROM reservations WHERE room_number = ?"
        " AND status = 'checked_in' ORDER BY checkin_date LIMIT 1",
        (room_number,)).fetchone()


def arrival_on(room_number: int, day: date):
    """Prenotazione con check-in esattamente nel giorno indicato (un arrivo)."""
    return get_conn().execute(
        "SELECT * FROM reservations WHERE room_number = ?"
        " AND status IN ('booked', 'checked_in') AND checkin_date = ?"
        " ORDER BY id LIMIT 1",
        (room_number, day.isoformat())).fetchone()


def upcoming_for_room(room_number: int, today: date):
    """Prossime prenotazioni attive della camera (per la scheda camera)."""
    return get_conn().execute(
        "SELECT * FROM reservations WHERE room_number = ?"
        " AND status IN ('booked', 'checked_in') AND checkout_date >= ?"
        " ORDER BY checkin_date",
        (room_number, today.isoformat())).fetchall()


def in_range(start: date, end: date):
    """Prenotazioni attive che intersecano [start, end] (per la timeline)."""
    return get_conn().execute(
        "SELECT * FROM reservations WHERE status IN ('booked', 'checked_in')"
        " AND checkin_date <= ? AND checkout_date >= ?"
        " ORDER BY room_number, checkin_date",
        (end.isoformat(), start.isoformat())).fetchall()


def active_on(day: date, include_checked_out: bool = False):
    """Prenotazioni attive che coprono il giorno indicato.

    Con include_checked_out=True comprende anche chi e gia partito
    (serve al foglio pulizie del giorno di check-out).
    """
    statuses = "('booked', 'checked_in', 'checked_out')" \
        if include_checked_out else "('booked', 'checked_in')"
    return get_conn().execute(
        "SELECT r.*, rm.is_suite FROM reservations r"
        " JOIN rooms rm ON rm.number = r.room_number"
        f" WHERE r.status IN {statuses}"
        " AND r.checkin_date <= ? AND r.checkout_date >= ?"
        " ORDER BY r.room_number",
        (day.isoformat(), day.isoformat())).fetchall()


def do_checkin(res_id: int, guest_list: list[dict]) -> None:
    """Conferma il check-in registrando gli ospiti.

    guest_list: dict con first_name, last_name, birth_date, birth_place,
    document_type, document_number, is_child. Serve almeno un ospite con
    nome e cognome.
    """
    if not any(g["first_name"].strip() and g["last_name"].strip()
               for g in guest_list):
        raise ValidationError(
            "Serve almeno un ospite con nome e cognome completi.")

    res = get(res_id)
    if res is None or res["status"] != "booked":
        raise ValidationError("Prenotazione non valida per il check-in.")

    conn = get_conn()
    for g in guest_list:
        guest_id = guests.upsert(g)
        conn.execute(
            "INSERT INTO reservation_guests (reservation_id, guest_id, is_child)"
            " VALUES (?, ?, ?)", (res_id, guest_id, int(g.get("is_child", False))))
    conn.execute("UPDATE reservations SET status = 'checked_in' WHERE id = ?",
                 (res_id,))
    conn.commit()
    rooms.set_dirty(res["room_number"], True)


def checkin_guest(res_id: int, guest: dict) -> None:
    """Registra un singolo ospite; al primo mette la prenotazione in check-in.

    Usato dalla reception, dove ogni ospite arriva e si registra separatamente.
    """
    conn = get_conn()
    guest_id = guests.upsert(guest)
    conn.execute(
        "INSERT INTO reservation_guests (reservation_id, guest_id, is_child,"
        " checked_in_at) VALUES (?, ?, ?, ?)",
        (res_id, guest_id, int(guest.get("is_child", False)),
         clock.now().isoformat()))
    res = get(res_id)
    conn.execute("UPDATE reservations SET status = 'checked_in' WHERE id = ?"
                 " AND status = 'booked'", (res_id,))
    conn.commit()
    if res["status"] == "booked":
        rooms.set_dirty(res["room_number"], True)


def do_checkout(res_id: int) -> None:
    """Conferma il check-out: la camera si libera ma resta sporca."""
    res = get(res_id)
    if res is None or res["status"] != "checked_in":
        raise ValidationError("Prenotazione non valida per il check-out.")
    conn = get_conn()
    conn.execute("UPDATE reservations SET status = 'checked_out' WHERE id = ?",
                 (res_id,))
    conn.commit()
    rooms.set_dirty(res["room_number"], True)

    # il conto alimenta il bilancio: netto come introito, IVA come perdita
    t = billing.bill_totals(res)
    note = f"Camera {res['room_number']} - {guest_display_name(res)}"
    budget.record(budget.INCOME, "Soggiorno", t["net"], note)
    if t["vat"]:
        budget.record(budget.LOSS, "IVA", t["vat"], note)


def guest_display_name(res) -> str:
    """Nome del primo ospite registrato, o intestatario della prenotazione."""
    row = get_conn().execute(
        "SELECT g.first_name, g.last_name FROM reservation_guests rg"
        " JOIN guests g ON g.id = rg.guest_id"
        " WHERE rg.reservation_id = ? ORDER BY rg.id LIMIT 1",
        (res["id"],)).fetchone()
    if row and (row["first_name"] or row["last_name"]):
        return f"{row['first_name']} {row['last_name']}".strip()
    return f"{res['first_name']} {res['last_name']}".strip()
