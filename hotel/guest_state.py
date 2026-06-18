"""Stato dinamico degli ospiti: "genoma" (sonno/sveglia) e posizione in camera.

Il genoma e deterministico dal guest_id (carta d'identita stabile, niente da
salvare). Ogni notte i tempi reali hanno una tolleranza di +/-1h, deterministica
per (ospite, data): abitudine senza ripetersi identica ogni giorno.
"""

import random
from datetime import datetime, time, timedelta

from . import guests, reception

# colori "visione termica": freddo = dorme, caldo = sveglio, grigio = assente
COLORS = {"Sveglio": "#e64a19", "Addormentato": "#1a237e",
          "Assente": "#757575", "N/A": "#9e9e9e"}

LOCATIONS = (
    "A letto",
    "Sul divano",
    "Sulla sedia",
    "Guarda la TV dal letto",
    "Guarda la TV dalla sedia",
    "In bagno",
    "Alla finestra",
    "Al telefono",
    "Si sta preparando",
    "Legge un libro",
    "Sul balcone",
    "Lavora al laptop",
    "Ordina il bagaglio",
    "Si rilassa",
    "Ascolta musica",
    "Fa yoga",
    "Si trucca",
    "Ricarica i dispositivi",
    "Sfoglia il menu",
    "Consulta la mappa",
)

EXTERNAL_LOCATIONS = (
    "Fuori a passeggio",
    "Al ristorante",
    "In piscina",
    "Alla SPA",
    "In palestra",
    "In citta",
    "Al bar",
    "In giardino",
    "In escursione",
    "In spiaggia",
    "Al centro benessere",
    "Alla reception",
    "Nel parcheggio",
    "Al negozio di souvenir",
    "Alla fermata del bus",
    "Visita turistica",
    "Al campo da tennis",
    "Al campo da golf",
    "Al museo",
    "Allo shopping",
    "Al porto",
    "In escursione in barca",
    "Al mercato locale",
    "In una visita guidata",
    "Al cinema",
    "Al parco",
)

# pasti: finestra oraria (riferita ai turni), durata 1h, sala
MEALS = {
    "Colazione": {"start": 6, "end": 10, "room": "Sala colazione"},
    "Pranzo": {"start": 12, "end": 15, "room": "Sala pranzo"},   # turno Pranzo
    "Cena": {"start": 19, "end": 23, "room": "Sala cena"},        # turno Sera
}
BOARD_MEALS = {
    "BB": ("Colazione",),
    "RO": (),
    "RES": (),
    "HB": ("Colazione", "Cena"),
    "FB": ("Colazione", "Pranzo", "Cena"),
}

TOLERANCE_MIN = 60   # +/-1h di tolleranza giornaliera


def metadata(guest_id: int) -> dict:
    """Genoma stabile: ora di sonno base (turno notte) e durata sonno (4-9h)."""
    r = random.Random(guest_id)
    return {"sleep_offset": r.randint(60, 540),  # minuti dopo le 22:00 (23:00-07:00)
            "wake_hours": r.randint(4, 9)}


def sleep_window(guest_id: int, anchor):
    """(addormentamento, risveglio) per la notte ancorata ad `anchor`."""
    meta = metadata(guest_id)
    r = random.Random(f"{guest_id}:{anchor.isoformat()}")   # jitter della notte
    onset_off = meta["sleep_offset"] + r.randint(-TOLERANCE_MIN, TOLERANCE_MIN)
    duration = meta["wake_hours"] * 60 + r.randint(-TOLERANCE_MIN, TOLERANCE_MIN)
    onset = datetime.combine(anchor, time(22, 0)) + timedelta(minutes=onset_off)
    return onset, onset + timedelta(minutes=duration)


def _is_asleep(guest_id: int, now: datetime) -> bool:
    # la notte puo scavalcare la mezzanotte: controlla stasera e ieri sera
    for anchor in (now.date(), now.date() - timedelta(days=1)):
        onset, wake = sleep_window(guest_id, anchor)
        if onset <= now < wake:
            return True
    return False


def stato(guest_id: int, now: datetime) -> str:
    try:
        return "Addormentato" if _is_asleep(guest_id, now) else "Sveglio"
    except Exception:
        return "N/A"   # fallback in caso di problemi


def locazione(stato_value: str, guest_id: int, now: datetime) -> str:
    if stato_value == "Addormentato":
        return "Letto"
    if stato_value == "N/A":
        return "N/A"
    # da sveglio si sposta: cambia ogni ora di gioco
    r = random.Random(f"loc:{guest_id}:{now.date()}:{now.hour}")
    return r.choice(LOCATIONS)


def settle_minutes(rg_id: int) -> int:
    """Minuti (1-30) in cui l'ospite, appena fatto il check-in, e 'Assente'."""
    return random.Random(f"vis:{rg_id}").randint(1, 30)


def _external(guest_id: int, now: datetime) -> str:
    r = random.Random(f"ext:{guest_id}:{now.date()}:{now.hour}")
    return r.choice(EXTERNAL_LOCATIONS)


def _on_outing(guest_id: int, now: datetime) -> bool:
    """Uscite della giornata (0-2), deterministiche per (ospite, giorno)."""
    day = now.date()
    r = random.Random(f"out:{guest_id}:{day.isoformat()}")
    for _ in range(r.randint(0, 2)):
        start = datetime.combine(day, time(r.randint(9, 19), r.randint(0, 59)))
        if start <= now < start + timedelta(minutes=r.randint(60, 180)):
            return True
    return False


# Motivi di assenza in ordine di priorita; ognuno -> locazione oppure None.
# Per aggiungere assenze future (dai metadati) basta aggiungere una funzione.
def _absent_food(row, now):
    return ("Reception" if reception.has_food_complaint(
        row["reservation_id"], row["first_name"], row["last_name"]) else None)


def _absent_reception(row, now):
    return "Reception" if reception.has_checkout(row["reservation_id"]) else None


def _absent_settling(row, now):
    if row["checked_in_at"] is None:
        return None
    arrived = datetime.fromisoformat(row["checked_in_at"])
    if now < arrived + timedelta(minutes=settle_minutes(row["rg_id"])):
        return _external(row["id"], now)
    return None


def _absent_outing(row, now):
    # uscita solo da sveglio: chi dorme resta in stanza
    if _on_outing(row["id"], now) and not _is_asleep(row["id"], now):
        return _external(row["id"], now)
    return None


def _meal_slot(guest_id: int, day, meal: str):
    """Slot di 1h (inizio, fine) del pasto, deterministico per (ospite, giorno)."""
    win = MEALS[meal]
    r = random.Random(f"meal:{guest_id}:{day.isoformat()}:{meal}")
    span = (win["end"] - 1 - win["start"]) * 60   # 1h di attivita entro la finestra
    start = (datetime.combine(day, time(win["start"]))
             + timedelta(minutes=r.randint(0, span)))
    return start, start + timedelta(hours=1)


def current_meal(now: datetime):
    """Pasto in corso secondo l'ora del giorno, oppure None."""
    for meal, win in MEALS.items():
        if win["start"] <= now.hour < win["end"]:
            return meal
    return None


def is_eating(guest_id: int, board: str, meal: str, now: datetime) -> bool:
    if meal not in BOARD_MEALS.get(board, ()):
        return False
    start, end = _meal_slot(guest_id, now.date(), meal)
    return start <= now < end and not _is_asleep(guest_id, now)


def has_done_meal(guest_id: int, board: str, meal: str, now: datetime) -> bool:
    """Ha gia fatto il pasto oggi (slot finito). Si azzera al giorno nuovo."""
    if meal not in BOARD_MEALS.get(board, ()):
        return False
    return now >= _meal_slot(guest_id, now.date(), meal)[1]


def _meal_now(guest_id: int, board: str, now: datetime):
    meal = current_meal(now)
    if meal and is_eating(guest_id, board, meal, now):
        return MEALS[meal]["room"]
    return None


def reservation_at_meal(res_id: int, now: datetime) -> bool:
    """Un ospite della prenotazione sta facendo un pasto (no check-out adesso)."""
    return any(_meal_now(g["id"], g["board"], now)
               for g in guests.for_reservation(res_id))


def _absent_meal(row, now):
    return _meal_now(row["id"], row["board"], now)


ABSENCE_CHECKS = (_absent_food, _absent_reception, _absent_settling,
                  _absent_meal, _absent_outing)


def absence_location(row, now: datetime):
    """Locazione se l'ospite e Assente, altrimenti None."""
    for check in ABSENCE_CHECKS:
        loc = check(row, now)
        if loc is not None:
            return loc
    return None


def describe(row, now: datetime) -> dict:
    """Riga tabella: nome, stato, locazione, emozione, bisogno, colore."""
    out = absence_location(row, now)
    if out is not None:
        st, loc = "Assente", out
    else:
        st = stato(row["id"], now)
        loc = locazione(st, row["id"], now)
    return {"name": f"{row['first_name']} {row['last_name']}".strip(),
            "stato": st, "locazione": loc,
            "emozione": "N/A", "bisogno": "N/A", "color": COLORS[st]}


def sleep_base_str(guest_id: int) -> str:
    total = (22 * 60 + metadata(guest_id)["sleep_offset"]) % 1440
    return f"{total // 60:02d}:{total % 60:02d}"
