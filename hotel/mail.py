"""Gameplay grezzo: email di richiesta prenotazione che arrivano nel tempo.

Ogni email e una richiesta generata a caso; si puo inserire a mano (leggendo
il testo) o automaticamente. I template sono semplici stringhe str.format:
aggiungerne uno = appenderlo a TEMPLATES.
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta

from . import clock, constants, names, reservations
from .database import get_conn
from .debug_seed import DEFAULT_BOARD_PRICES

rng = random.Random()


@dataclass
class MailConfig:
    enabled: bool = False
    interval_seconds: int = 60
    probability: float = 0.5
    auto_insert: bool = False


config = MailConfig()

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


def _it(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def _generate() -> dict:
    first = names.random_first_name(rng)
    last = names.random_last_name(rng)
    adults = rng.randint(1, 3)
    children = rng.randint(0, 1)
    nights = rng.randint(1, 7)
    checkin = clock.today() + timedelta(days=rng.randint(0, 14))
    checkout = checkin + timedelta(days=nights)
    guests = [f"{first} {last}"]
    for _ in range(adults - 1 + children):
        guests.append(f"{names.random_first_name(rng)} {last}")
    return {
        "first_name": first, "last_name": last,
        "email": f"{first}.{last}@email.com".lower(),
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
        (clock.today().isoformat(), data["email"],
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


def all_mails():
    return get_conn().execute("SELECT * FROM mails ORDER BY id DESC").fetchall()


def get(mail_id: int):
    return get_conn().execute(
        "SELECT * FROM mails WHERE id = ?", (mail_id,)).fetchone()


def insert(mail_id: int) -> int:
    """Crea la prenotazione dalla mail e la marca inserita. Ritorna la camera.
    Solleva ValidationError se gia inserita o senza camere libere."""
    m = get(mail_id)
    if m is None or m["inserted"]:
        raise reservations.ValidationError("Email gia inserita.")
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
