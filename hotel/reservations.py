"""Prenotazioni: creazione, disponibilita, check-in e check-out."""

import random
from datetime import date, timedelta

from . import billing, budget, clock, constants, guests, rooms
from .database import get_conn


class ValidationError(Exception):
    """Errore bloccante nei dati di una prenotazione."""


def price_for(board: str) -> float:
    """Prezzo per notte di mercato: listino base x upgrade delle camere.
    E lui a decidere il prezzo, non l'operatore al banco."""
    from . import amenities            # import differiti: evitano i cicli
    from .debug_seed import DEFAULT_BOARD_PRICES
    return round(DEFAULT_BOARD_PRICES[board] * amenities.price_mult(), 2)


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


def change_room(res_id: int, new_room: int) -> None:
    """Sposta la prenotazione su un'altra camera, stesse date.

    Solo prima del check-in: una prenotazione gia in camera non si sposta.
    """
    res = get(res_id)
    if res is None or res["status"] != "booked":
        raise ValidationError(
            "Solo le prenotazioni non ancora in check-in si possono spostare.")
    if new_room == res["room_number"]:
        return
    room = rooms.get_room(new_room)
    if room is None:
        raise ValidationError(f"La camera {new_room} non esiste.")
    if room["blocked"]:
        raise ValidationError(f"La camera {new_room} e bloccata.")
    checkin = date.fromisoformat(res["checkin_date"])
    checkout = date.fromisoformat(res["checkout_date"])
    if not is_room_available(new_room, checkin, checkout, exclude_id=res_id):
        raise ValidationError(
            f"La camera {new_room} non e libera in quel periodo.")
    conn = get_conn()
    conn.execute("UPDATE reservations SET room_number = ? WHERE id = ?",
                 (new_room, res_id))
    conn.commit()


def current_for_room(room_number: int):
    """Prenotazione checked-in della camera, se presente."""
    return get_conn().execute(
        "SELECT * FROM reservations WHERE room_number = ?"
        " AND status = 'checked_in' ORDER BY checkin_date LIMIT 1",
        (room_number,)).fetchone()


def arrival_on(room_number: int, day: date):
    """Prenotazione ancora in arrivo (non ancora arrivata) nel giorno indicato.

    Solo 'booked': dopo il check-in il marcatore di arrivo deve sparire.
    """
    return get_conn().execute(
        "SELECT * FROM reservations WHERE room_number = ?"
        " AND status = 'booked' AND checkin_date = ?"
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


def do_checkout(res_id: int, *, paid: bool = True, receptionist=None) -> None:
    """Conferma il check-out: la camera si libera ma resta sporca.

    Con paid=False (uscita d'ufficio) registra a bilancio importo 0.
    `receptionist` e chi sta al banco: il suo bonus puo gonfiare/scontare il
    conto, generare mance o recensioni dedicate.
    """
    res = get(res_id)
    if res is None or res["status"] != "checked_in":
        raise ValidationError("Prenotazione non valida per il check-out.")
    from . import reviews   # import differito: evita il ciclo
    bonus = receptionist["bonus"] if receptionist is not None else None
    conn = get_conn()
    conn.execute("UPDATE reservations SET status = 'checked_out' WHERE id = ?",
                 (res_id,))
    # usura: camera gia logora -> l'ospite se ne accorge (reclamo implicito);
    # col manutentore assunto l'usura cresce la meta
    room = rooms.get_room(res["room_number"])
    complaints = res["complaints"] + (1 if room["wear"] >= constants.WEAR_LIMIT
                                      else 0)
    r = random.Random(f"co:{res_id}")
    from . import staff   # import differito: staff importa reservations
    if not (staff.employed_bonus("manutentore") and r.random() < 0.5):
        conn.execute("UPDATE rooms SET wear = wear + 1 WHERE number = ?",
                     (res["room_number"],))
    conn.commit()
    rooms.set_dirty(res["room_number"], True)

    # recensione: 5 stelle, -2 a reclamo, -1 se non paga; le positive escono
    # solo grazie a servizi dell'hotel o al receptionist di turno
    from . import problems   # import differito
    guest_name = f"{res['first_name']} {res['last_name']}".strip()
    stars = reviews.STARS_MAX - 2 * complaints - (0 if paid else 1)
    force, skip_review = None, False
    if bonus == "truffatore":
        force = "negative"
    elif bonus == "pappamolle" or (bonus == "memorabile"
                                   and r.random() < 0.5):
        force = "positive"
    if bonus == "cucciolo" and force is None and stars <= 3:
        # 50%: la recensione negativa sparisce; meta delle volte si ribalta
        if r.random() < 0.5:
            skip_review = True
            if r.random() < 0.5:
                force, skip_review = "positive", False
    if not skip_review:
        reviews.leave_checkout(guest_name, stars, force)
    # un problema aperto in camera puo finire in recensione (l'emozione)
    emotion = problems.emotion_for_room(res["room_number"])
    if emotion and r.random() < problems.EMOTION_REVIEW_PROB:
        reviews.leave_emotion(guest_name, emotion,
                              emotion in problems.POSITIVE_EMOTIONS)

    if not paid:
        budget.record(budget.INCOME, "Soggiorno", 0, "L'ospite non ha pagato.")
        return

    # si incassa il 100% del ricavato; l'IVA si accantona e si versa a fine
    # mese con le tasse. Persuasore/truffatore/pappamolle ritoccano il totale.
    from . import taxes   # import differito
    mult = {"persuasore": 1.25, "truffatore": 1.5,
            "pappamolle": 0.75}.get(bonus, 1.0)
    t = billing.bill_totals(res)
    note = f"Camera {res['room_number']} - {guest_display_name(res)}"
    budget.record(budget.INCOME, "Soggiorno", round(t["total"] * mult, 2), note)
    taxes.accrue_vat(round(t["vat"] * mult, 2))
    if bonus == "bell_aspetto" and r.random() < 0.4:
        budget.record(budget.INCOME, "Mance", round(r.uniform(5, 20), 2), note)


def auto_checkout_overstayers(now) -> int:
    """Sicurezza: chi e ancora in camera il giorno di check-out dopo le 14:30
    (o gia oltre) viene fatto uscire d'ufficio, senza addebito. Col 'brutto
    muso' di turno, pero, nessuno scappa senza pagare. Ritorna quanti."""
    from . import reception, staff   # import differiti: evitano il ciclo
    forced_pay = staff.on_duty_bonus("brutto_muso", now)
    today = now.date().isoformat()
    deadline = now.replace(hour=14, minute=30, second=0, microsecond=0)
    rows = get_conn().execute(
        "SELECT id, checkout_date FROM reservations WHERE status = 'checked_in'"
        " AND checkout_date <= ?", (today,)).fetchall()
    done = 0
    for r in rows:
        if r["checkout_date"] < today or now >= deadline:
            get_conn().execute(
                "DELETE FROM reception WHERE reservation_id = ?", (r["id"],))
            do_checkout(r["id"], paid=forced_pay)
            done += 1
    return done


def shorten_stay(res_id: int) -> None:
    """Bonus '???': l'ospite resta una notte in meno (minimo 1) ma il totale
    del conto non cambia (prezzo per notte ricalibrato)."""
    res = get(res_id)
    checkin = date.fromisoformat(res["checkin_date"])
    checkout = date.fromisoformat(res["checkout_date"])
    nights = (checkout - checkin).days
    if nights <= 1:
        return
    conn = get_conn()
    conn.execute(
        "UPDATE reservations SET checkout_date = ?, price_per_night = ?"
        " WHERE id = ?",
        ((checkout - timedelta(days=1)).isoformat(),
         round(res["price_per_night"] * nights / (nights - 1), 2), res_id))
    conn.commit()


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
