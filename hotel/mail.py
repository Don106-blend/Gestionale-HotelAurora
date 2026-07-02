"""Gameplay grezzo: email di richiesta prenotazione che arrivano nel tempo.

Ogni email e una richiesta generata a caso; si puo inserire a mano (leggendo
il testo) o automaticamente. I template sono semplici stringhe str.format:
aggiungerne uno = appenderlo a TEMPLATES.
"""

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from . import clock, constants, names, reservations
from .database import get_conn
from .debug_seed import DEFAULT_BOARD_PRICES

rng = random.Random()


@dataclass
class MailConfig:
    enabled: bool = False
    block_new_bookings: bool = False     # blocca l'arrivo di nuove prenotazioni
    interval_seconds: int = 60
    probability: float = 0.5
    auto_insert: bool = False
    returning_probability: float = 0.5   # quota di mail da ospiti abituali
    window_days: int = 5                 # check-in entro N giorni dal tempo simulato
    # probabilita per turno; i turni non elencati usano `probability` (standard)
    shift_probability: dict = field(default_factory=lambda: {
        "Pranzo": 0.2, "Sera": 0.2, "Notte": 0.05})


config = MailConfig()


def shift_probability() -> float:
    """Probabilita mail del turno corrente (standard se non specificata)."""
    return config.shift_probability.get(clock.shift()[0], config.probability)


# Stagionalita della domanda: estate piena, dicembre festivo, novembre morto.
SEASON_FACTOR = {1: 0.7, 2: 0.6, 3: 0.8, 4: 1.0, 5: 1.1, 6: 1.3,
                 7: 1.5, 8: 1.5, 9: 1.1, 10: 0.8, 11: 0.6, 12: 1.2}


def demand_factor() -> float:
    """Moltiplicatore del flusso prenotazioni: stagione x reputazione."""
    from . import reviews
    return SEASON_FACTOR[clock.today().month] * reviews.demand_factor()

# Template in tono naturale. Placeholder: name, email, pax, guests, nights,
# checkin, checkout, board. Aggiungere un template = aggiungere una stringa.
TEMPLATES = (
    """Buongiorno,
mi chiamo {name} e vorrei prenotare una camera da voi.
Saremmo in {pax}: {guests}.
Pensavamo di arrivare il {checkin} e ripartire il {checkout}, quindi {nights} notti.
Se possibile gradiremmo il trattamento {board}.
Fatemi sapere se avete disponibilita, grazie mille!

{name}
{email}""",
    """Salve,
vi scrivo per chiedere disponibilita per {nights} notti, dal {checkin} al {checkout}.
Siamo {pax} ({guests}) e ci piacerebbe la soluzione {board}.
Resto in attesa di un vostro riscontro.
Cordiali saluti,
{name} - {email}""",
)

EXPIRY_HOURS = 48  # una richiesta non gestita scade dopo 48h

# Reclamo di chi si e arrabbiato aspettando il check-in: mail "spam", non inseribile.
COMPLAINT_TEMPLATE = """Spett.le Hotel,
sono {name} e avevo prenotato dal {checkin} al {checkout}.
Sono arrivato in reception e ho aspettato oltre un'ora e mezza senza che
nessuno mi facesse il check-in. Stanco di aspettare ho annullato il soggiorno.
Non mettero mai piu piede nel vostro hotel.
{name}"""


def _it(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def _pick_returning_guest():
    """Un ospite abituale senza prenotazioni attive, oppure None.

    Riusa il DB ospiti con probabilita config.returning_probability (ridotta
    dalla reputazione: chi si e trovato male non torna) ed esclude chi ha gia
    una prenotazione programmata (stesso nome): niente doppioni.
    """
    from . import reviews
    if rng.random() >= config.returning_probability * (reviews.reputation()
                                                       / reviews.STARS_MAX):
        return None
    rows = get_conn().execute(
        "SELECT DISTINCT first_name, last_name FROM guests g"
        " WHERE first_name != '' AND last_name != '' AND NOT EXISTS ("
        "  SELECT 1 FROM reservations r"
        "  WHERE r.status IN ('booked', 'checked_in')"
        "  AND r.first_name = g.first_name COLLATE NOCASE"
        "  AND r.last_name = g.last_name COLLATE NOCASE)"
        " AND NOT EXISTS ("                       # esclude chi si e arrabbiato
        "  SELECT 1 FROM blacklist b"
        "  WHERE b.first_name = g.first_name COLLATE NOCASE"
        "  AND b.last_name = g.last_name COLLATE NOCASE)").fetchall()
    return rng.choice(rows) if rows else None


def _generate() -> dict:
    guest = _pick_returning_guest()
    if guest is not None:
        first, last = guest["first_name"], guest["last_name"]
    else:
        first, last = names.random_first_name(rng), names.random_last_name(rng)
    adults = rng.randint(1, 3)
    children = rng.randint(0, 1)
    nights = rng.randint(1, 7)
    checkin = clock.today() + timedelta(days=rng.randint(0, max(config.window_days, 0)))
    checkout = checkin + timedelta(days=nights)
    guests = [f"{first} {last}"]
    for _ in range(adults - 1 + children):
        guests.append(f"{names.random_first_name(rng)} {last}")
    return {
        "first_name": first, "last_name": last,
        "email": f"{first}.{last}".lower().replace(" ", "") + "@email.com",
        "adults": adults, "children": children, "nights": nights,
        "checkin": checkin.isoformat(), "checkout": checkout.isoformat(),
        "board": rng.choice(list(constants.BOARDS)), "guests": guests,
    }


def _render(data: dict) -> str:
    return rng.choice(TEMPLATES).format(
        name=f"{data['first_name']} {data['last_name']}",
        email=data["email"], pax=data["adults"] + data["children"],
        guests=", ".join(data["guests"]), nights=data["nights"],
        checkin=_it(data["checkin"]), checkout=_it(data["checkout"]),
        board=constants.BOARDS[data["board"]].label)


def spawn() -> int:
    """Genera e salva una nuova email; con auto_insert la inserisce subito."""
    data = _generate()
    cur = get_conn().execute(
        "INSERT INTO mails (received_at, sender, subject, body, first_name,"
        " last_name, checkin, checkout, adults, children, board)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (clock.now().isoformat(), data["email"],
         f"Richiesta prenotazione {_it(data['checkin'])}", _render(data),
         data["first_name"], data["last_name"], data["checkin"],
         data["checkout"], data["adults"], data["children"], data["board"]))
    get_conn().commit()
    mail_id = cur.lastrowid
    if config.auto_insert:
        try:
            insert(mail_id)
        except reservations.ValidationError:
            pass
    return mail_id


def spawn_complaint(res) -> int:
    """Mail di reclamo (spam) dell'ospite arrabbiato: niente da inserire."""
    name = f"{res['first_name']} {res['last_name']}".strip()
    body = COMPLAINT_TEMPLATE.format(name=name, checkin=_it(res["checkin_date"]),
                                     checkout=_it(res["checkout_date"]))
    cur = get_conn().execute(
        "INSERT INTO mails (received_at, sender, subject, body, first_name,"
        " last_name, checkin, checkout, adults, children, board, kind)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'spam')",
        (clock.now().isoformat(), res["email"] or "ospite@email.com",
         "Reclamo: attesa al check-in", body, res["first_name"],
         res["last_name"], res["checkin_date"], res["checkout_date"],
         res["adults"], res["children"], res["board"]))
    get_conn().commit()
    return cur.lastrowid


def all_mails():
    return get_conn().execute("SELECT * FROM mails ORDER BY id DESC").fetchall()


def search_mails(term: str = "", archived: bool = False):
    """Email filtrate per testo (mittente/oggetto/nome) e stato archiviazione."""
    like = f"%{term.strip()}%"
    return get_conn().execute(
        "SELECT * FROM mails WHERE archived = ? AND (sender LIKE ?"
        " OR subject LIKE ? OR first_name LIKE ? OR last_name LIKE ?)"
        " ORDER BY id DESC", (int(archived), like, like, like, like)).fetchall()


def get(mail_id: int):
    return get_conn().execute(
        "SELECT * FROM mails WHERE id = ?", (mail_id,)).fetchone()


def is_expired(m, now: datetime | None = None) -> bool:
    """Scaduta: passate 48h dalla ricezione o superata la data di check-in."""
    now = now or clock.now()
    if datetime.fromisoformat(m["received_at"]) + timedelta(hours=EXPIRY_HOURS) <= now:
        return True
    return date.fromisoformat(m["checkin"]) < now.date()


def status(m, now: datetime | None = None) -> str:
    """Etichetta di stato: Spam / Inserita / Rifiutata / Scaduta / Da gestire."""
    if m["kind"] == "spam":
        return "Spam"
    if m["inserted"]:
        return "Inserita"
    if m["rejected"]:
        return "Rifiutata"
    if is_expired(m, now):
        return "Scaduta"
    return "Da gestire"


def reject(mail_id: int) -> None:
    get_conn().execute(
        "UPDATE mails SET rejected = 1 WHERE id = ? AND inserted = 0", (mail_id,))
    get_conn().commit()


def archive(mail_id: int) -> None:
    get_conn().execute("UPDATE mails SET archived = 1 WHERE id = ?", (mail_id,))
    get_conn().commit()


def delete(mail_id: int) -> None:
    get_conn().execute("DELETE FROM mails WHERE id = ?", (mail_id,))
    get_conn().commit()


def insert(mail_id: int) -> int:
    """Crea la prenotazione dalla mail e la marca inserita. Ritorna la camera.
    Solleva ValidationError se non inseribile o senza camere libere."""
    m = get(mail_id)
    if m is None:
        raise reservations.ValidationError("Email inesistente.")
    st = status(m)
    if st != "Da gestire":
        raise reservations.ValidationError(f"Email {st.lower()}: non inseribile.")
    checkin = date.fromisoformat(m["checkin"])
    checkout = date.fromisoformat(m["checkout"])
    free = reservations.available_rooms(checkin, checkout)
    if not free:
        raise reservations.ValidationError("Nessuna camera libera nel periodo.")
    room = rng.choice(free)
    reservations.create_reservation(
        first_name=m["first_name"], last_name=m["last_name"],
        room_number=room["number"], checkin=checkin, checkout=checkout,
        adults=m["adults"], children=m["children"],
        price_per_night=DEFAULT_BOARD_PRICES[m["board"]], board=m["board"],
        discount=None, phone="", email=m["sender"], color="",
        comments=f"Da email: {m['sender']}")
    get_conn().execute("UPDATE mails SET inserted = 1 WHERE id = ?", (mail_id,))
    get_conn().commit()
    return room["number"]
