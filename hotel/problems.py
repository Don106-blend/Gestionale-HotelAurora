"""Problemi di camere e servizi: nascono, l'ospite li racconta in reception,
si risolvono dalla lista To Do pagando o mandando le pulizie.

Risolvere non e istantaneo: paga/assegna le ore avvia la riparazione, che si
chiude da sola dopo PROBLEMS[...]['hours'] ore di gioco (il tecnico ci mette
del tempo; i guai piu grossi possono richiedere giorni). 'due_at' segna la
scadenza; finche non e passata il problema resta "in corso" nel To Do.

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

PROB_PER_HOUR = 0.05        # probabilita di un nuovo problema a ora di gioco
PURGE_DAYS = 7              # i risolti spariscono dal To Do dopo 7 giorni
EMOTION_REVIEW_PROB = 0.35  # chance che l'emozione finisca in recensione

# --- potenziamenti manutenzione ------------------------------------------------
MAX_REPAIRS_BASE = 1             # riparazioni contemporanee di base (una alla volta)
REPAIR_SLOT_BASE_COST = 800.0    # "Contatti da tuttofare": ogni acquisto raddoppia
TOOLBOX_COST = 1500.0            # "Cassetta degli attrezzi": una tantum
TOOLBOX_TIME_MULT = 0.75         # -25% tempo di riparazione
COMPLIANCE_COST = 1000.0         # "Controllo delle norme": ricomprabile a scadenza
COMPLIANCE_DAYS = 30
COMPLIANCE_FACTOR = 0.5          # -50% probabilita nuovi problemi, mentre attivo

# fix: ("money", euro) da pagare, oppure ("cleaning", ore) da assegnare a un
# operatore delle pulizie (finiscono sul suo foglio ore di fine mese).
# hours: ore di gioco perche la riparazione (gia pagata/assegnata) si concluda.
# scope: "room" oppure la chiave del servizio richiesto (amenities).
PROBLEMS = {
    "lampadina": {"label": "Lampadina del bagno fulminata", "scope": "room",
                  "fix": ("money", 20.0), "hours": 1, "emotion": "Ansia"},
    "ac": {"label": "Aria condizionata guasta", "scope": "room",
           "fix": ("money", 80.0), "hours": 6, "emotion": "Accaldato"},
    "riscaldamento": {"label": "Riscaldamento in tilt", "scope": "room",
                      "fix": ("money", 70.0), "hours": 6,
                      "emotion": "Infreddolito"},
    "acqua_calda": {"label": "Acqua calda assente", "scope": "room",
                    "fix": ("money", 50.0), "hours": 8,
                    "emotion": "Infreddolito"},
    "tv": {"label": "TV che non si accende", "scope": "room",
           "fix": ("money", 40.0), "hours": 2, "emotion": "Annoiato"},
    "materasso": {"label": "Materasso cigolante", "scope": "room",
                  "fix": ("money", 60.0), "hours": 24, "emotion": "Insonne"},
    "finestra": {"label": "Finestra che non si chiude bene", "scope": "room",
                 "fix": ("money", 35.0), "hours": 12,
                 "emotion": "Infreddolito"},
    "rubinetto": {"label": "Rubinetto che gocciola", "scope": "room",
                  "fix": ("cleaning", 0.25), "hours": 1,
                  "emotion": "Infastidito"},
    "scarafaggio": {"label": "Scarafaggio avvistato", "scope": "room",
                    "fix": ("cleaning", 0.5), "hours": 4,
                    "emotion": "Disgustato"},
    "puzza": {"label": "Cattivo odore in camera", "scope": "room",
              "fix": ("cleaning", 0.25), "hours": 3, "emotion": "Disgustato"},
    "diffusore": {"label": "Diffusore impazzito: profumo di lavanda ovunque",
                  "scope": "room", "fix": ("money", 10.0), "hours": 1,
                  "emotion": "Rilassato"},
    "wifi_camera": {"label": "Wi-Fi assente in camera", "scope": "room",
                    "requires": "wifi", "fix": ("money", 25.0), "hours": 4,
                    "emotion": "Frustrato"},
    # problemi dei servizi: esistono solo se il servizio e sbloccato
    "cacca_piscina": {"label": "Cacca in piscina", "scope": "pool",
                      "fix": ("cleaning", 0.25), "hours": 2, "emotion": None},
    "piscina_verde": {"label": "Acqua della piscina verde", "scope": "pool",
                      "fix": ("money", 90.0), "hours": 48, "emotion": None},
    "slot": {"label": "Slot machine inceppata", "scope": "casino",
             "fix": ("money", 120.0), "hours": 12, "emotion": None},
    "proiettore": {"label": "Proiettore della sala riunioni fuori uso",
                   "scope": "meeting", "fix": ("money", 60.0), "hours": 6,
                   "emotion": None},
    "wifi_hotel": {"label": "Wi-Fi dell'hotel a terra", "scope": "wifi",
                   "fix": ("money", 50.0), "hours": 24, "emotion": None},
    "distributore": {"label": "Distributore della zona ristoro bloccato",
                     "scope": "snackbar", "fix": ("money", 30.0), "hours": 3,
                     "emotion": None},
    "insegna": {"label": "Insegna della reception lampeggiante",
                "scope": "lobby", "fix": ("money", 40.0), "hours": 2,
                "emotion": None},
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


def not_started_problems():
    """Aperti e non ancora presi in carico (nessuna riparazione avviata)."""
    return get_conn().execute(
        "SELECT * FROM problems WHERE resolved_at IS NULL AND due_at IS NULL"
        " ORDER BY id").fetchall()


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


def maybe_spawn(now, factor: float = 1.0) -> bool:
    """Una possibilita di guaio nuovo a ogni ora di gioco. `factor` scala
    ulteriormente la probabilita (es. meta in idle); 'Controllo delle norme'
    attivo la dimezza altrettanto (si moltiplicano)."""
    stamp = now.strftime("%Y-%m-%dT%H")
    if kv_get("problems_hour") == stamp:
        return False
    kv_set("problems_hour", stamp)
    prob = PROB_PER_HOUR * factor
    if compliance_active(now.date()):
        prob *= COMPLIANCE_FACTOR
    if rng.random() >= prob:
        return False
    keys = _eligible_keys()
    return bool(keys) and spawn(rng.choice(keys), now) is not None


# --- risoluzione -----------------------------------------------------------------

def resolve(problem_id: int, operator_id: int | None = None,
            free: bool = False) -> None:
    """Avvia la riparazione dal To Do: paga, oppure assegna le ore a un
    operatore delle pulizie. Il problema resta "in corso" finche non passano
    le ore previste (vedi PROBLEMS[...]['hours']); a quel punto si chiude da
    solo (complete_due). free=True (tuttofare): gratis e istantaneo."""
    from . import estate, staff   # import differiti
    p = get(problem_id)
    if p is None or p["resolved_at"] is not None:
        raise ProblemError("Problema inesistente o gia risolto.")
    if p["due_at"] is not None:
        raise ProblemError("Riparazione gia in corso.")
    if not free and active_repairs() >= max_concurrent_repairs():
        limit = max_concurrent_repairs()
        raise ProblemError(
            f"Si puo riparare al massimo {limit} problema"
            f"{'i' if limit != 1 else ''} alla volta"
            " (compra 'Contatti da tuttofare' per aumentarlo).")
    info = PROBLEMS[p["key"]]
    kind, amount = info["fix"]
    if not free:
        if kind == "money":
            estate._spend(amount, f"Riparazione: {describe(p)}")
        else:
            op = staff.get(operator_id) if operator_id else None
            if op is None or op["role"] != staff.ROLE_CLEANING:
                raise ProblemError("Serve un operatore delle pulizie.")
            staff.log_hours(operator_id, clock.today(), amount)
    now = clock.now()
    conn = get_conn()
    if free:
        conn.execute("UPDATE problems SET due_at = ?, resolved_at = ?"
                     " WHERE id = ?", (now.isoformat(), now.isoformat(),
                                       problem_id))
    else:
        hours = info["hours"] * (TOOLBOX_TIME_MULT if has_toolbox() else 1.0)
        due = now + timedelta(hours=hours)
        conn.execute("UPDATE problems SET due_at = ? WHERE id = ?",
                     (due.isoformat(), problem_id))
    conn.commit()


def block_room(problem_id: int) -> None:
    """Blocca la camera del problema mentre la riparazione e in corso; si
    sblocca da sola (vedi complete_due) quando il problema si risolve.
    Solo per problemi di camera gia avviati (due_at impostato)."""
    from . import rooms
    p = get(problem_id)
    if p is None or p["resolved_at"] is not None:
        raise ProblemError("Problema inesistente o gia risolto.")
    if p["due_at"] is None:
        raise ProblemError("Avvia prima la riparazione.")
    if p["room_number"] is None:
        raise ProblemError("Questo problema non riguarda una camera.")
    rooms.set_blocked(p["room_number"], True)
    conn = get_conn()
    conn.execute("UPDATE problems SET room_blocked = 1 WHERE id = ?", (problem_id,))
    conn.commit()


# --- potenziamenti manutenzione ------------------------------------------------

def active_repairs() -> int:
    """Riparazioni avviate ma non ancora completate (occupano uno slot)."""
    return get_conn().execute(
        "SELECT COUNT(*) FROM problems WHERE due_at IS NOT NULL"
        " AND resolved_at IS NULL").fetchone()[0]


def repair_slots_bought() -> int:
    return kv_get("repair_slots_bought", 0)


def max_concurrent_repairs() -> int:
    return MAX_REPAIRS_BASE + repair_slots_bought()


def repair_slot_cost() -> float:
    return round(REPAIR_SLOT_BASE_COST * 2 ** repair_slots_bought(), 2)


def buy_repair_slot() -> int:
    """'Contatti da tuttofare': +1 riparazione contemporanea; ogni acquisto
    costa il doppio del precedente (ripetibile senza limite)."""
    from . import estate
    estate._spend(repair_slot_cost(), "Contatti da tuttofare")
    kv_set("repair_slots_bought", repair_slots_bought() + 1)
    return max_concurrent_repairs()


def has_toolbox() -> bool:
    return bool(kv_get("toolbox_bought", False))


def buy_toolbox() -> None:
    """'Cassetta degli attrezzi': -25% tempo di riparazione, una tantum."""
    from . import estate
    if has_toolbox():
        raise ProblemError("Cassetta degli attrezzi gia acquistata.")
    estate._spend(TOOLBOX_COST, "Cassetta degli attrezzi")
    kv_set("toolbox_bought", True)


def compliance_until():
    """Data (str ISO) fino a cui e' attivo 'Controllo delle norme', o None."""
    return kv_get("compliance_until")


def compliance_active(today) -> bool:
    until = compliance_until()
    return bool(until) and today.isoformat() <= until


def buy_compliance(today) -> None:
    """'Controllo delle norme': -50% probabilita di nuovi problemi per 30
    giorni; ricomprabile allo stesso prezzo solo dopo la scadenza."""
    from . import estate
    if compliance_active(today):
        raise ProblemError(f"Controllo gia attivo fino al {compliance_until()}.")
    estate._spend(COMPLIANCE_COST, "Controllo delle norme")
    kv_set("compliance_until", (today + timedelta(days=COMPLIANCE_DAYS)).isoformat())


def complete_due(now) -> int:
    """Chiude le riparazioni avviate la cui scadenza (due_at) e arrivata,
    sbloccando la camera se era stata bloccata per quel problema. Ritorna
    quante ne ha chiuse.

    ponytail: se la camera era gia bloccata a mano per un altro motivo, qui
    viene comunque sbloccata insieme al problema -- caso raro, non tracciato.
    """
    rows = get_conn().execute(
        "SELECT id, room_number, room_blocked FROM problems WHERE due_at IS NOT NULL"
        " AND resolved_at IS NULL AND due_at <= ?", (now.isoformat(),)
    ).fetchall()
    if not rows:
        return 0
    from . import rooms
    conn = get_conn()
    for r in rows:
        conn.execute("UPDATE problems SET resolved_at = ? WHERE id = ?",
                     (now.isoformat(), r["id"]))
        if r["room_blocked"] and r["room_number"] is not None:
            rooms.set_blocked(r["room_number"], False)
    conn.commit()
    return len(rows)


def autofix(now) -> bool:
    """Receptionist 'tuttofare' di turno: una riparazione gratis al giorno,
    presa da quelle non ancora avviate (nel To Do compare gia barrata)."""
    from . import staff
    day = now.date().isoformat()
    if kv_get("tuttofare_done") == day:
        return False
    if not staff.on_duty_bonus("tuttofare", now):
        return False
    candidates = not_started_problems()
    if not candidates:
        return False
    resolve(candidates[0]["id"], free=True)
    kv_set("tuttofare_done", day)
    return True


def purge(now) -> None:
    """I risolti spariscono dal To Do dopo PURGE_DAYS giorni di gioco."""
    cutoff = (now - timedelta(days=PURGE_DAYS)).isoformat()
    conn = get_conn()
    conn.execute("DELETE FROM problems WHERE resolved_at IS NOT NULL"
                 " AND resolved_at <= ?", (cutoff,))
    conn.commit()


def tick(now, factor: float = 1.0) -> int:
    changed = int(maybe_spawn(now, factor))
    changed += int(autofix(now))
    changed += complete_due(now)
    purge(now)
    return changed
