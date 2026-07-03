"""Problemi di camere e servizi: nascono, l'ospite li racconta in reception,
si risolvono dalla lista To Do pagando o mandando le pulizie.

Ogni problema di camera assegna un'emozione agli ospiti dentro; al check-out
c'e una probabilita che l'emozione finisca in recensione (positiva o negativa
a seconda dell'emozione). I problemi dei servizi esistono solo se il servizio
e stato sbloccato. Risolto = barrato nel To Do, sparisce dopo 7 giorni.
"""

import random
from datetime import timedelta

from . import amenities, clock, guests, reception
from .database import get_conn, kv_get, kv_set

rng = random.Random()

PROB_PER_HOUR = 0.10        # probabilita di un nuovo problema a ora di gioco
PURGE_DAYS = 7              # i risolti spariscono dal To Do dopo 7 giorni
EMOTION_REVIEW_PROB = 0.35  # chance che l'emozione finisca in recensione

# fix: ("money", euro) da pagare, oppure ("cleaning", ore) da assegnare a un
# operatore delle pulizie (finiscono sul suo foglio ore di fine mese).
# scope: "room" oppure la chiave del servizio richiesto (amenities).
PROBLEMS = {
    "lampadina": {"label": "Lampadina del bagno fulminata", "scope": "room",
                  "fix": ("money", 20.0), "emotion": "Ansia"},
    "ac": {"label": "Aria condizionata guasta", "scope": "room",
           "fix": ("money", 80.0), "emotion": "Accaldato"},
    "riscaldamento": {"label": "Riscaldamento in tilt", "scope": "room",
                      "fix": ("money", 70.0), "emotion": "Infreddolito"},
    "acqua_calda": {"label": "Acqua calda assente", "scope": "room",
                    "fix": ("money", 50.0), "emotion": "Infreddolito"},
    "tv": {"label": "TV che non si accende", "scope": "room",
           "fix": ("money", 40.0), "emotion": "Annoiato"},
    "materasso": {"label": "Materasso cigolante", "scope": "room",
                  "fix": ("money", 60.0), "emotion": "Insonne"},
    "finestra": {"label": "Finestra che non si chiude bene", "scope": "room",
                 "fix": ("money", 35.0), "emotion": "Infreddolito"},
    "rubinetto": {"label": "Rubinetto che gocciola", "scope": "room",
                  "fix": ("cleaning", 0.25), "emotion": "Infastidito"},
    "scarafaggio": {"label": "Scarafaggio avvistato", "scope": "room",
                    "fix": ("cleaning", 0.5), "emotion": "Disgustato"},
    "puzza": {"label": "Cattivo odore in camera", "scope": "room",
              "fix": ("cleaning", 0.25), "emotion": "Disgustato"},
    "diffusore": {"label": "Diffusore impazzito: profumo di lavanda ovunque",
                  "scope": "room", "fix": ("money", 10.0),
                  "emotion": "Rilassato"},
    "wifi_camera": {"label": "Wi-Fi assente in camera", "scope": "room",
                    "requires": "wifi", "fix": ("money", 25.0),
                    "emotion": "Frustrato"},
    # problemi dei servizi: esistono solo se il servizio e sbloccato
    "cacca_piscina": {"label": "Cacca in piscina", "scope": "pool",
                      "fix": ("cleaning", 0.25), "emotion": None},
    "piscina_verde": {"label": "Acqua della piscina verde", "scope": "pool",
                      "fix": ("money", 90.0), "emotion": None},
    "slot": {"label": "Slot machine inceppata", "scope": "casino",
             "fix": ("money", 120.0), "emotion": None},
    "proiettore": {"label": "Proiettore della sala riunioni fuori uso",
                   "scope": "meeting", "fix": ("money", 60.0),
                   "emotion": None},
    "wifi_hotel": {"label": "Wi-Fi dell'hotel a terra", "scope": "wifi",
                   "fix": ("money", 50.0), "emotion": None},
    "distributore": {"label": "Distributore della zona ristoro bloccato",
                     "scope": "snackbar", "fix": ("money", 30.0),
                     "emotion": None},
    "insegna": {"label": "Insegna della reception lampeggiante",
                "scope": "lobby", "fix": ("money", 40.0), "emotion": None},
}

POSITIVE_EMOTIONS = {"Rilassato"}   # il resto delle emozioni e negativo


class ProblemError(Exception):
    """Risoluzione non possibile (operatore mancante, gia risolto...)."""


def get(problem_id: int):
    return get_conn().execute("SELECT * FROM problems WHERE id = ?",
                              (problem_id,)).fetchone()


def open_problems():
    return get_conn().execute(
        "SELECT * FROM problems WHERE resolved_at IS NULL ORDER BY id"
    ).fetchall()


def todo_list():
    """Aperti prima, poi i risolti (barrati) non ancora spariti."""
    return get_conn().execute(
        "SELECT * FROM problems ORDER BY resolved_at IS NOT NULL, id DESC"
    ).fetchall()


def describe(p) -> str:
    info = PROBLEMS[p["key"]]
    if p["room_number"]:
        return f"{info['label']} (camera {p['room_number']})"
    where = amenities.AMENITIES.get(info["scope"], {}).get("label", "hotel")
    return f"{info['label']} ({where})"


def emotion_for_room(room_number: int):
    """Emozione del primo problema aperto della camera, oppure None."""
    for p in get_conn().execute(
            "SELECT key FROM problems WHERE room_number = ?"
            " AND resolved_at IS NULL ORDER BY id", (room_number,)).fetchall():
        emo = PROBLEMS[p["key"]]["emotion"]
        if emo:
            return emo
    return None


def emotion_for_reservation(res_id: int):
    row = get_conn().execute(
        "SELECT room_number FROM reservations WHERE id = ?",
        (res_id,)).fetchone()
    return emotion_for_room(row["room_number"]) if row else None


# --- nascita dei problemi -------------------------------------------------------

def _eligible_keys() -> list:
    owned = amenities.owned()
    out = []
    for key, info in PROBLEMS.items():
        if info["scope"] != "room" and info["scope"] not in owned:
            continue
        if info.get("requires") and info["requires"] not in owned:
            continue
        out.append(key)
    return out


def spawn(key: str, now, room_number: int | None = None):
    """Crea il problema e manda un ospite in reception a raccontarlo.
    Ritorna l'id, o None se non c'e nessuno che possa lamentarsi."""
    info = PROBLEMS[key]
    people = guests.checked_in_guests()
    if not people:
        return None
    if info["scope"] == "room":
        if room_number is None:
            open_rooms = {p["room_number"] for p in open_problems()
                          if p["key"] == key}
            candidates = [g["room_number"] for g in people
                          if g["room_number"] not in open_rooms]
            if not candidates:
                return None
            room_number = rng.choice(candidates)
        reporter = next(g for g in people if g["room_number"] == room_number)
    else:
        if any(p["key"] == key for p in open_problems()):
            return None          # niente doppioni dello stesso guaio di zona
        room_number = None
        reporter = rng.choice(people)
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO problems (key, room_number, created_at)"
        " VALUES (?, ?, ?)", (key, room_number, now.isoformat()))
    pid = cur.lastrowid
    reception._add(reporter["reservation_id"], "problem",
                   reporter["first_name"], reporter["last_name"], False, now,
                   note=describe(get(pid)))
    conn.commit()
    return pid


def maybe_spawn(now) -> bool:
    """Una possibilita di guaio nuovo a ogni ora di gioco."""
    stamp = now.strftime("%Y-%m-%dT%H")
    if kv_get("problems_hour") == stamp:
        return False
    kv_set("problems_hour", stamp)
    if rng.random() >= PROB_PER_HOUR:
        return False
    keys = _eligible_keys()
    return bool(keys) and spawn(rng.choice(keys), now) is not None


# --- risoluzione -----------------------------------------------------------------

def resolve(problem_id: int, operator_id: int | None = None,
            free: bool = False) -> None:
    """Risolve dal To Do: paga la riparazione, oppure assegna le ore a un
    operatore delle pulizie. free=True (tuttofare): gratis."""
    from . import estate, staff   # import differiti
    p = get(problem_id)
    if p is None or p["resolved_at"] is not None:
        raise ProblemError("Problema inesistente o gia risolto.")
    kind, amount = PROBLEMS[p["key"]]["fix"]
    if not free:
        if kind == "money":
            estate._spend(amount, f"Riparazione: {describe(p)}")
        else:
            op = staff.get(operator_id) if operator_id else None
            if op is None or op["role"] != staff.ROLE_CLEANING:
                raise ProblemError("Serve un operatore delle pulizie.")
            staff.log_hours(operator_id, clock.today(), amount)
    conn = get_conn()
    conn.execute("UPDATE problems SET resolved_at = ? WHERE id = ?",
                 (clock.now().isoformat(), problem_id))
    conn.commit()


def autofix(now) -> bool:
    """Receptionist 'tuttofare' di turno: una riparazione gratis al giorno
    (nel To Do compare gia barrata)."""
    from . import staff
    day = now.date().isoformat()
    if kv_get("tuttofare_done") == day:
        return False
    if not staff.on_duty_bonus("tuttofare", now):
        return False
    problems_open = open_problems()
    if not problems_open:
        return False
    resolve(problems_open[0]["id"], free=True)
    kv_set("tuttofare_done", day)
    return True


def purge(now) -> None:
    """I risolti spariscono dal To Do dopo PURGE_DAYS giorni di gioco."""
    cutoff = (now - timedelta(days=PURGE_DAYS)).isoformat()
    conn = get_conn()
    conn.execute("DELETE FROM problems WHERE resolved_at IS NOT NULL"
                 " AND resolved_at <= ?", (cutoff,))
    conn.commit()


def tick(now) -> int:
    changed = int(maybe_spawn(now))
    changed += int(autofix(now))
    purge(now)
    return changed
