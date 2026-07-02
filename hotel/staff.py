"""Dipendenti: anagrafica, turni, foglio ore, paghe e simulazione dei lavori.

Due ruoli:
- 'pulizie': lavorano 7-15 (Mattina + Pranzo), max 8h/giorno; girano le camere
  da pulire (rimanenze prima, check-out solo dopo che l'ospite e uscito).
- 'sala': coprono i pasti (max 2 turni al giorno), ognuno gestisce fino a 24
  ospiti; le ore accreditate sono la durata dei turni assegnati.

Gli stipendi partono il 20 di ogni mese: ore non ancora pagate x paga oraria
lorda x costo azienda.
"""

import math
import random
from datetime import date, datetime, time, timedelta

from . import budget, cleaning, clock, constants, names, reservations, rooms
from .database import get_conn, kv_get, kv_set

ROLE_CLEANING = "pulizie"
ROLE_DINING = "sala"
ROLES = (ROLE_CLEANING, ROLE_DINING)
ROLE_LABELS = {ROLE_CLEANING: "Pulizie", ROLE_DINING: "Sala pasti"}

HOURLY_GROSS = 7.0    # paga oraria lorda di default
# Costo azienda (Italia): lordo + contributi INPS/INAIL a carico del datore
# (~31%) + TFR (~6,9%) + rateo tredicesima (~8,3%) ~= lordo x 1.46
EMPLOYER_COST_MULT = 1.46
PAYDAY = 20           # stipendi addebitati il 20 del mese

CLEAN_START, CLEAN_END = 7, 15   # turno pulizie: Mattina fino a fine Pranzo
DINING_GUESTS_PER_OP = 24        # ospiti gestibili da un operatore di sala
DINING_MAX_SHIFTS = 2            # turni pasto massimi al giorno per operatore

rng = random.Random()


class StaffError(Exception):
    """Operazione sul personale non possibile."""


# --- anagrafica ---------------------------------------------------------------

def ensure_seed() -> None:
    """Primo avvio: 1 operatore pulizie e 2 di sala gia assunti."""
    if kv_get("staff_seeded", False):
        return
    for role, n in ((ROLE_CLEANING, 1), (ROLE_DINING, 2)):
        for _ in range(n):
            hire(role)
    kv_set("roster", {ROLE_CLEANING: 1, ROLE_DINING: 2})
    kv_set("staff_seeded", True)


def all_employees():
    return get_conn().execute(
        "SELECT * FROM employees ORDER BY role, id").fetchall()


def get(emp_id: int):
    return get_conn().execute(
        "SELECT * FROM employees WHERE id = ?", (emp_id,)).fetchone()


def headcount(role: str) -> int:
    return get_conn().execute(
        "SELECT COUNT(*) FROM employees WHERE role = ?", (role,)).fetchone()[0]


def hire(role: str, hourly: float = HOURLY_GROSS) -> int:
    if role not in ROLES:
        raise StaffError("Ruolo sconosciuto.")
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO employees (first_name, last_name, role, hourly, hired_on)"
        " VALUES (?, ?, ?, ?, ?)",
        (names.random_first_name(rng), names.random_last_name(rng), role,
         hourly, clock.today().isoformat()))
    conn.commit()
    return cur.lastrowid


def fire(emp_id: int) -> float:
    """Licenzia e liquida subito le ore non pagate. Ritorna il costo."""
    e = get(emp_id)
    if e is None:
        raise StaffError("Dipendente inesistente.")
    due = unpaid_hours(emp_id)
    cost = round(due * e["hourly"] * EMPLOYER_COST_MULT, 2)
    if cost > 0:
        budget.record(budget.LOSS, "Stipendi", cost,
                      f"Liquidazione {e['first_name']} {e['last_name']}"
                      f" ({due:g}h)")
    conn = get_conn()
    conn.execute("DELETE FROM work_hours WHERE employee_id = ?", (emp_id,))
    conn.execute("DELETE FROM employees WHERE id = ?", (emp_id,))
    conn.commit()
    return cost


# --- turni (roster): le modifiche valgono dal giorno dopo ---------------------

def roster() -> dict:
    """Quanti dipendenti per ruolo sono in servizio oggi."""
    _roster_rollover()
    r = kv_get("roster", {}) or {}
    return {role: min(int(r.get(role, 0)), headcount(role)) for role in ROLES}


def roster_next() -> dict:
    """Il roster che varra da domani (quello corrente se non modificato)."""
    nxt = kv_get("roster_next")
    base = nxt if nxt else (kv_get("roster", {}) or {})
    return {role: int(base.get(role, 0)) for role in ROLES}


def set_roster_next(role: str, count: int) -> None:
    """Programma quanti chiamarne da domani (il giocatore pianifica)."""
    nxt = roster_next()
    nxt[role] = max(0, min(int(count), headcount(role)))
    kv_set("roster_next", nxt)
    kv_set("roster_next_day",
           (clock.today() + timedelta(days=1)).isoformat())


def _roster_rollover() -> None:
    day = kv_get("roster_next_day")
    if day and day <= clock.today().isoformat():
        kv_set("roster", kv_get("roster_next") or {})
        kv_set("roster_next", None)
        kv_set("roster_next_day", None)


SICK_PROB = 0.03    # probabilita giornaliera di malattia


def is_sick(emp_id: int, day: date) -> bool:
    """Malattia deterministica per (dipendente, giorno): non si presenta."""
    return random.Random(f"sick:{emp_id}:{day.isoformat()}").random() < SICK_PROB


def on_duty(role: str):
    """I dipendenti chiamati oggi per il ruolo (i primi N assunti), esclusi
    i malati: chi e a casa non lavora (e non viene pagato)."""
    rows = get_conn().execute(
        "SELECT * FROM employees WHERE role = ? ORDER BY id LIMIT ?",
        (role, roster().get(role, 0))).fetchall()
    today = clock.today()
    return [r for r in rows if not is_sick(r["id"], today)]


# --- foglio ore ----------------------------------------------------------------

def log_hours(emp_id: int, day: date, hours: float) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO work_hours (employee_id, day, hours) VALUES (?, ?, ?)",
        (emp_id, day.isoformat(), hours))
    conn.commit()


def unpaid_hours(emp_id: int) -> float:
    return get_conn().execute(
        "SELECT COALESCE(SUM(hours), 0) FROM work_hours"
        " WHERE employee_id = ? AND paid = 0", (emp_id,)).fetchone()[0]


def month_hours(emp_id: int, day: date) -> float:
    return get_conn().execute(
        "SELECT COALESCE(SUM(hours), 0) FROM work_hours"
        " WHERE employee_id = ? AND day LIKE ?",
        (emp_id, day.strftime("%Y-%m") + "%")).fetchone()[0]


def unpaid_cost() -> float:
    """Stima del prossimo stipendio complessivo (costo azienda)."""
    return round(sum(unpaid_hours(e["id"]) * e["hourly"] * EMPLOYER_COST_MULT
                     for e in all_employees()), 2)


def speed_factor(emp_id: int) -> float:
    """Esperienza: +5% di velocita ogni 50 ore lavorate in carriera (max +50%)."""
    lifetime = get_conn().execute(
        "SELECT COALESCE(SUM(hours), 0) FROM work_hours"
        " WHERE employee_id = ?", (emp_id,)).fetchone()[0]
    return min(1.5, 1.0 + 0.05 * int(lifetime // 50))


def hours_sheet(day: date) -> str:
    """Foglio ore del mese in formato testo."""
    out = [f"HotelAurora - Foglio ore {day.strftime('%m/%Y')}", ""]
    for e in all_employees():
        rows = get_conn().execute(
            "SELECT day, SUM(hours) AS h FROM work_hours"
            " WHERE employee_id = ? AND day LIKE ? GROUP BY day ORDER BY day",
            (e["id"], day.strftime("%Y-%m") + "%")).fetchall()
        tot = sum(r["h"] for r in rows)
        out.append(f"{e['first_name']} {e['last_name']}"
                   f"  ({ROLE_LABELS[e['role']]}, € {e['hourly']:g}/h lordi)"
                   f" — mese: {tot:g}h, da pagare: {unpaid_hours(e['id']):g}h")
        for r in rows:
            out.append(f"  {date.fromisoformat(r['day']).strftime('%d/%m')}:"
                       f" {r['h']:g}h")
        out.append("")
    out.append(f"Stima stipendi del {PAYDAY} del mese (costo azienda"
               f" x{EMPLOYER_COST_MULT:g}): € {unpaid_cost():,.2f}")
    return "\n".join(out)


# --- paghe: il 20 del mese ------------------------------------------------------

def run_payroll(today: date) -> float:
    """Dal 20 del mese addebita tutte le ore non ancora pagate (una volta
    per mese). Ritorna il totale pagato."""
    month = today.strftime("%Y-%m")
    if today.day < PAYDAY or kv_get("last_payroll") == month:
        return 0.0
    total = 0.0
    conn = get_conn()
    for e in all_employees():
        hours = unpaid_hours(e["id"])
        if hours <= 0:
            continue
        cost = round(hours * e["hourly"] * EMPLOYER_COST_MULT, 2)
        budget.record(budget.LOSS, "Stipendi", cost,
                      f"{e['first_name']} {e['last_name']}: {hours:g}h"
                      f" x € {e['hourly']:g} lordi (costo azienda)")
        total += cost
    conn.execute("UPDATE work_hours SET paid = 1 WHERE paid = 0")
    conn.commit()
    kv_set("last_payroll", month)
    return round(total, 2)


# --- simulazione pulizie ---------------------------------------------------------
# ponytail: stato del giorno in memoria; a riavvio a meta giornata le camere
# check-out gia pulite (dirty=0) non si rifanno, al peggio una rimanenza da
# 0.25h viene ripetuta. Persistere lo stato se mai diventasse un problema.
_hk = {"day": None, "busy": {}, "hours": {}, "done": set()}
# busy: emp_id -> (camera, fine lavoro, ore del lavoro)


def _hk_reset(day: date) -> None:
    _hk.update(day=day, busy={}, hours={}, done=set())


def cleaner_in_room(number: int) -> bool:
    """Un operatore delle pulizie e dentro la camera adesso (pallino rosa)."""
    return any(room == number for room, _end, _h in _hk["busy"].values())


def _eligible_tasks(day: date) -> list:
    """Lavori disponibili: rimanenze prima; i check-out solo quando l'ospite
    e uscito. Esclude camere gia fatte o in corso."""
    taken = _hk["done"] | {room for room, _e, _h in _hk["busy"].values()}
    out = []
    for t in cleaning.tasks_for_day(day):
        if t.room_number in taken:
            continue
        if "check-out" in t.note:
            if reservations.current_for_room(t.room_number) is not None:
                continue          # l'ospite non ha ancora fatto il check-out
            room = rooms.get_room(t.room_number)
            if room is not None and not room["dirty"]:
                continue          # gia pulita (es. dopo un riavvio)
        out.append(t)
    out.sort(key=lambda t: ("check-out" in t.note, t.room_number))
    return out


def housekeeping_tick(now: datetime) -> bool:
    """Fa avanzare gli operatori: chiude i lavori finiti e ne assegna di
    nuovi dentro il turno 7-15 e il tetto di 8 ore. True se e cambiato algo."""
    if _hk["day"] != now.date():
        _hk_reset(now.date())
    changed = False
    for emp_id, (room, end, h) in list(_hk["busy"].items()):
        if now >= end:
            rooms.set_dirty(room, False)     # pulita in automatico
            log_hours(emp_id, now.date(), h)
            _hk["hours"][emp_id] = _hk["hours"].get(emp_id, 0.0) + h
            _hk["done"].add(room)
            del _hk["busy"][emp_id]
            changed = True

    if not (CLEAN_START <= now.hour < CLEAN_END):
        return changed
    idle = [e for e in on_duty(ROLE_CLEANING) if e["id"] not in _hk["busy"]]
    if not idle:
        return changed
    tasks = _eligible_tasks(now.date())
    end_of_shift = datetime.combine(now.date(), time(CLEAN_END))
    for e in idle:
        done_h = _hk["hours"].get(e["id"], 0.0)
        speed = speed_factor(e["id"])   # esperienza: pulisce piu in fretta
        for i, t in enumerate(tasks):
            dur = round(t.hours / speed, 4)
            end = now + timedelta(hours=dur)
            if (done_h + dur <= constants.OPERATOR_MAX_HOURS
                    and end <= end_of_shift):
                _hk["busy"][e["id"]] = (t.room_number, end, dur)
                tasks.pop(i)
                changed = True
                break
    return changed


# --- sala pasti -------------------------------------------------------------------

def dining_plan(day: date) -> dict:
    """Assegna gli operatori di sala ai pasti del giorno: almeno uno a pasto,
    e ceil(ospiti attesi / 24) dove i fogli pasti prevedono piu gente. I pasti
    piu affollati scelgono per primi, ognuno lavora al massimo 2 turni."""
    from . import guest_state, meals
    ops = on_duty(ROLE_DINING)
    shifts = {e["id"]: 0 for e in ops}
    plan = {meal: [] for meal in guest_state.MEALS}
    demand = {meal: sum(r[2] for r in meals.meal_rows(meal.lower(), day))
              for meal in plan}
    for meal in sorted(plan, key=lambda m: -demand[m]):
        need = max(1, math.ceil(demand[meal] / DINING_GUESTS_PER_OP))
        for e in ops:
            if len(plan[meal]) >= need:
                break
            if shifts[e["id"]] < DINING_MAX_SHIFTS:
                plan[meal].append(e["id"])
                shifts[e["id"]] += 1
    return plan


def dining_capacity(meal: str, day: date) -> int:
    return DINING_GUESTS_PER_OP * len(dining_plan(day)[meal])


def add_served(meal: str, day: date) -> None:
    """+1 'ospiti serviti' all'operatore meno carico del turno."""
    ids = dining_plan(day)[meal]
    if not ids:
        return
    conn = get_conn()
    emp = conn.execute(
        f"SELECT id FROM employees WHERE id IN"
        f" ({','.join('?' * len(ids))}) ORDER BY served LIMIT 1",
        ids).fetchone()
    conn.execute("UPDATE employees SET served = served + 1 WHERE id = ?",
                 (emp["id"],))
    conn.commit()


def dining_tick(now: datetime) -> None:
    """A fine turno pasto accredita le ore (durata della finestra) agli
    operatori assegnati. Dedup su KV: niente doppi accrediti dopo un riavvio."""
    from . import guest_state
    state = kv_get("dining_logged") or {}
    if state.get("day") != now.date().isoformat():
        state = {"day": now.date().isoformat(), "meals": []}
    plan = None
    for meal, win in guest_state.MEALS.items():
        if meal in state["meals"] or now.hour < win["end"]:
            continue
        if plan is None:
            plan = dining_plan(now.date())
        for emp_id in plan[meal]:
            log_hours(emp_id, now.date(), float(win["end"] - win["start"]))
        state["meals"].append(meal)
    kv_set("dining_logged", state)


# --- tick unico per la GUI ----------------------------------------------------------

def tick(now: datetime) -> int:
    """Rollover turni, pulizie, ore di sala e stipendi. 1 se serve refresh."""
    changed = housekeeping_tick(now)
    dining_tick(now)
    if run_payroll(now.date()):
        changed = True
    return int(changed)
