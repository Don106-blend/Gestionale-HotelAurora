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
ROLE_RECEPTION = "reception"
ROLES = (ROLE_CLEANING, ROLE_DINING)       # ruoli con roster a conteggio
ROLE_LABELS = {ROLE_CLEANING: "Pulizie", ROLE_DINING: "Sala pasti",
               ROLE_RECEPTION: "Reception"}

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


def _cost_mult(emp) -> float:
    """Costo azienda: gli 'in nero' sono pagati flat, senza oneri."""
    return 1.0 if emp["contract"] == "nero" else EMPLOYER_COST_MULT


def fire(emp_id: int) -> float:
    """Licenzia e liquida subito le ore non pagate. Ritorna il costo."""
    e = get(emp_id)
    if e is None:
        raise StaffError("Dipendente inesistente.")
    due = unpaid_hours(emp_id)
    cost = round(due * e["hourly"] * _cost_mult(e), 2)
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
    return round(sum(unpaid_hours(e["id"]) * e["hourly"] * _cost_mult(e)
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
        cost = round(hours * e["hourly"] * _cost_mult(e), 2)
        if hours <= 0 or cost <= 0:      # stagista: ore gratuite
            continue
        budget.record(budget.LOSS, "Stipendi", cost,
                      f"{e['first_name']} {e['last_name']}: {hours:g}h"
                      f" x € {e['hourly']:g}"
                      + (" flat (in nero)" if e["contract"] == "nero"
                         else " lordi (costo azienda)"))
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


# --- receptionist: bonus, contratti, candidature e turni settimanali -----------
# I receptionist sono rari e potenti: ognuno ha UN bonus passivo. Si assumono
# dalle candidature (Browser) con un contratto; i turni si pianificano su una
# tabella settimanale (il giorno corrente e bloccato: preavviso di un giorno).

BONUSES = {
    "bell_aspetto": ("Bell'aspetto",
                     "Al check-out i clienti possono lasciare una mancia."),
    "brutto_muso": ("Brutto muso",
                    "Nel suo turno nessuno scappa senza pagare."),
    "calmo": ("Calmo",
              "Nel suo turno i clienti non si arrabbiano in reception."),
    "memorabile": ("Memorabile",
                   "I clienti possono lasciare una recensione positiva su di lui."),
    "animale_notturno": ("Animale notturno",
                         "Di notte nel suo turno arrivano piu mail."),
    "persuasore": ("Persuasore",
                   "Chi fa check-out con lui paga 1.25x."),
    "truffatore": ("Truffatore",
                   "Chi fa check-out con lui paga 1.5x ma lascia una recensione"
                   " negativa."),
    "pappamolle": ("Pappamolle",
                   "Chi fa check-out con lui paga 0.75x ma lascia una recensione"
                   " positiva."),
    "misterioso": ("???",
                   "Chi fa check-in con lui resta una notte in meno (min 1) ma"
                   " paga il prezzo pieno."),
    "sfruttabile": ("Sfruttabile",
                    "Puo lavorare 8h in piu a settimana, gratuite."),
    "barista": ("Barista",
                "Nel suo turno gli ospiti spendono 5-10 al bar (1 volta al di)."),
    "tuttofare": ("Tuttofare",
                  "Una volta al giorno nel suo turno ripara gratis un"
                  " problema (nel To Do compare gia barrato)."),
    "socievole": ("Socievole",
                  "Nel suo turno arrivano il 30% di mail in piu."),
    "contabile": ("Contabile", "Le bollette costano il 20% in meno."),
    "reclutatore": ("Reclutatore",
                    "Ogni settimana arrivano 2 candidature in piu."),
    "mediatore": ("Mediatore",
                  "Nel suo turno i reclami non pesano sulle recensioni."),
    "venditore": ("Venditore",
                  "Nel suo turno il room service e ordinato il doppio."),
    "manutentore": ("Manutentore", "Le camere si usurano la meta."),
    "insonne": ("Insonne", "Le sue ore notturne (23-7) costano la meta."),
    "carismatico": ("Carismatico",
                    "Gli ospiti abituali tornano il 50% piu volentieri."),
    "poliglotta": ("Poliglotta",
                   "Le prenotazioni inserite nel suo turno pagano il 10% in piu."),
    "fortunato": ("Fortunato", "Nel suo turno il casino rende il doppio."),
    "autonomo": ("Autonomo",
                 "Nel suo turno sbriga da solo check-in e check-out."),
    "cucciolo": ("Cucciolo",
                 "50% che una recensione negativa non venga lasciata;"
                 " se ci riesce, 50% che diventi positiva."),
    "cashback": ("Cashback",
                 "A fine turno restituisce il 10% dei soldi spesi durante"
                 " il suo turno."),
    "stagista": ("Stagista",
                 "Nessuno stipendio; solo part-time e al massimo un mese."),
}

CONTRACTS = {
    "full": {"label": "Full-time", "week_hours": 40, "hourly": HOURLY_GROSS},
    "part": {"label": "Part-time", "week_hours": 20, "hourly": HOURLY_GROSS},
    "nero": {"label": "In nero", "week_hours": 16, "hourly": 9.0,
             "max_days": 2},   # pagato flat, senza oneri
}
TRIAL_MONTHS = 3          # durata del contratto iniziale
QUIT_PROB = 0.35          # a fine contratto: se ne va?

# turni pianificabili: blocchi da 8h (full/nero) o 4h (part)
SHIFTS_8H = ("7-15", "15-23", "23-7")
SHIFTS_4H = ("7-11", "11-15", "15-19", "19-23", "23-3", "3-7")


def receptionists():
    return get_conn().execute(
        "SELECT * FROM employees WHERE role = 'reception' ORDER BY id"
    ).fetchall()


def hire_receptionist(first: str, last: str, bonus: str, contract: str) -> int:
    if bonus not in BONUSES or contract not in CONTRACTS:
        raise StaffError("Bonus o contratto sconosciuto.")
    hourly = CONTRACTS[contract]["hourly"]
    until = clock.today() + timedelta(days=TRIAL_MONTHS * 30)
    if bonus == "stagista":       # gratis, solo part-time, massimo un mese
        contract, hourly = "part", 0.0
        until = clock.today() + timedelta(days=30)
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO employees (first_name, last_name, role, hourly, hired_on,"
        " bonus, contract, contract_until, permanent)"
        " VALUES (?, ?, 'reception', ?, ?, ?, ?, ?, 0)",
        (first, last, hourly, clock.today().isoformat(), bonus, contract,
         until.isoformat()))
    conn.commit()
    return cur.lastrowid


# --- candidature: poche, casuali, rinnovate ogni settimana ----------------------

def _make_candidate(rng: random.Random) -> dict:
    return {"first_name": names.random_first_name(rng),
            "last_name": names.random_last_name(rng),
            "bonus": rng.choice(sorted(BONUSES))}


def candidates() -> list:
    """Candidati della settimana (deterministici), esclusi i gia assunti."""
    year, week, _ = clock.today().isocalendar()
    rng = random.Random(f"cand:{year}:{week}")
    extra = 2 if _employed_bonus("reclutatore") else 0
    taken = set(kv_get("cand_taken", []))
    out = []
    for i in range(3 + extra):
        c = _make_candidate(rng)
        c["key"] = f"{year}-{week}:{i}"
        if c["key"] not in taken:
            out.append(c)
    return out


def hire_candidate(key: str, contract: str) -> int:
    match = [c for c in candidates() if c["key"] == key]
    if not match:
        raise StaffError("Candidatura non piu disponibile.")
    c = match[0]
    emp_id = hire_receptionist(c["first_name"], c["last_name"], c["bonus"],
                               contract)
    kv_set("cand_taken", kv_get("cand_taken", []) + [key])
    return emp_id


def first_candidates() -> list:
    """I 4 receptionist tra cui scegliere al primo avvio (stabili finche
    non si sceglie)."""
    seed = kv_get("first_cand_seed")
    if seed is None:
        seed = random.random()
        kv_set("first_cand_seed", seed)
    rng = random.Random(f"first:{seed}")
    return [_make_candidate(rng) for _ in range(4)]


# --- turni settimanali -----------------------------------------------------------

def schedule() -> dict:
    """{emp_id(str): {weekday(str 0-6): 'inizio-fine' | None}}"""
    return kv_get("rec_schedule", {})


def shift_hours(shift: str) -> int:
    start, end = (int(x) for x in shift.split("-"))
    return (end - start) % 24


def allowed_shifts(contract: str) -> tuple:
    return SHIFTS_4H if contract == "part" else SHIFTS_8H


def week_limit(emp) -> int:
    limit = CONTRACTS[emp["contract"]]["week_hours"]
    if emp["bonus"] == "sfruttabile":
        limit += 8            # ore extra gratuite
    return limit


def set_shift(emp_id: int, weekday: int, shift) -> None:
    """Imposta il turno del giorno (None = riposo). Il giorno corrente e
    bloccato (preavviso di un giorno) e valgono i limiti del contratto."""
    e = get(emp_id)
    if e is None or e["role"] != "reception":
        raise StaffError("Receptionist inesistente.")
    if weekday == clock.today().weekday():
        raise StaffError("Il giorno corrente non si puo modificare"
                         " (preavviso di un giorno).")
    if shift is not None and shift not in allowed_shifts(e["contract"]):
        raise StaffError("Turno non previsto dal contratto.")
    sched = schedule()
    week = dict(sched.get(str(emp_id), {}))
    week[str(weekday)] = shift
    hours = sum(shift_hours(s) for s in week.values() if s)
    if hours > week_limit(e):
        raise StaffError(f"Oltre il limite settimanale ({week_limit(e)}h).")
    days = sum(1 for s in week.values() if s)
    max_days = CONTRACTS[e["contract"]].get("max_days")
    if max_days and days > max_days:
        raise StaffError(f"Contratto in nero: massimo {max_days} giorni.")
    sched[str(emp_id)] = week
    kv_set("rec_schedule", sched)


def _shift_at(emp_id: int, now: datetime):
    """Il turno che copre `now` (gestendo i turni a cavallo di mezzanotte)."""
    week = schedule().get(str(emp_id), {})
    for day, back in ((now.weekday(), False),
                      ((now.weekday() - 1) % 7, True)):
        shift = week.get(str(day))
        if not shift:
            continue
        start, end = (int(x) for x in shift.split("-"))
        if not back and start < end and start <= now.hour < end:
            return shift
        if start > end:      # scavalca mezzanotte
            if not back and now.hour >= start:
                return shift
            if back and now.hour < end:
                return shift
    return None


def on_duty_receptionists(now: datetime) -> list:
    return [e for e in receptionists() if _shift_at(e["id"], now)]


def receptionist_on_duty(now: datetime):
    """Chi sta al banco adesso (il primo per anzianita), oppure None."""
    on = on_duty_receptionists(now)
    return on[0] if on else None


def on_duty_bonus(bonus: str, now: datetime) -> bool:
    return any(e["bonus"] == bonus for e in on_duty_receptionists(now))


def _employed_bonus(bonus: str) -> bool:
    return get_conn().execute(
        "SELECT 1 FROM employees WHERE role = 'reception' AND bonus = ?"
        " LIMIT 1", (bonus,)).fetchone() is not None


def employed_bonus(bonus: str) -> bool:
    return _employed_bonus(bonus)


def mail_boost(now: datetime) -> float:
    """Moltiplicatore mail dai receptionist di turno."""
    boost = 1.0
    if on_duty_bonus("socievole", now):
        boost *= 1.3
    if (on_duty_bonus("animale_notturno", now)
            and clock.shift(now)[0] == "Notte"):
        boost *= 3.0
    return boost


# --- ore e contratti dei receptionist ---------------------------------------------

def _week_paid_hours(emp_id: int, day: date) -> float:
    monday = day - timedelta(days=day.weekday())
    return get_conn().execute(
        "SELECT COALESCE(SUM(hours), 0) FROM work_hours WHERE employee_id = ?"
        " AND day BETWEEN ? AND ?",
        (emp_id, monday.isoformat(),
         (monday + timedelta(days=6)).isoformat())).fetchone()[0]


def reception_tick(now: datetime) -> None:
    """Accredita le ore del turno di oggi (una volta per turno, all'inizio).
    Insonne: le ore del turno di notte contano la meta. Sfruttabile: le ore
    oltre il limite base del contratto sono gratuite."""
    state = kv_get("rec_logged") or {}
    if state.get("day") != now.date().isoformat():
        state = {"day": now.date().isoformat(), "done": []}
    for e in receptionists():
        shift = _shift_at(e["id"], now)
        key = f"{e['id']}:{shift}"
        if not shift or key in state["done"]:
            continue
        hours = float(shift_hours(shift))
        if e["bonus"] == "insonne" and shift in ("23-7", "23-3", "3-7"):
            hours /= 2
        base_limit = CONTRACTS[e["contract"]]["week_hours"]
        room = max(0.0, base_limit - _week_paid_hours(e["id"], now.date()))
        hours = min(hours, room)     # sfruttabile: l'extra non si paga
        if hours > 0:
            log_hours(e["id"], now.date(), hours)
        state["done"].append(key)
    kv_set("rec_logged", state)


def _cashback_tick(now: datetime) -> bool:
    """Bonus cashback: fotografa le spese all'inizio del turno e a fine turno
    restituisce il 10% di quanto speso nel frattempo."""
    snaps = kv_get("cashback_snap", {}) or {}
    on = {str(e["id"]) for e in on_duty_receptionists(now)
          if e["bonus"] == "cashback"}
    changed = False
    for emp_id in on:                    # inizio turno: snapshot delle perdite
        if emp_id not in snaps:
            snaps[emp_id] = budget.totals()["loss"]
            changed = True
    for emp_id in list(snaps):           # fine turno: rimborso del 10%
        if emp_id in on:
            continue
        spent = round(budget.totals()["loss"] - snaps.pop(emp_id), 2)
        changed = True
        if spent > 0:
            e = get(int(emp_id))
            who = (f"{e['first_name']} {e['last_name']}" if e
                   else "receptionist")
            budget.record(budget.INCOME, "Cashback", round(spent * 0.10, 2),
                          f"Turno di {who}")
    if changed:
        kv_set("cashback_snap", snaps)
    return changed


def contracts_tick(today: date) -> list:
    """A fine periodo di prova il receptionist decide (deterministico):
    se ne va (liquidato) o resta a tempo indeterminato. Ritorna i partiti."""
    gone = []
    for e in receptionists():
        if e["permanent"] or not e["contract_until"]:
            continue
        if today.isoformat() < e["contract_until"]:
            continue
        if e["bonus"] == "stagista":     # lo stage finisce sempre
            fire(e["id"])
            gone.append(f"{e['first_name']} {e['last_name']}")
        elif random.Random(f"quit:{e['id']}").random() < QUIT_PROB:
            fire(e["id"])         # liquidazione delle ore residue
            gone.append(f"{e['first_name']} {e['last_name']}")
        else:
            conn = get_conn()
            conn.execute("UPDATE employees SET permanent = 1 WHERE id = ?",
                         (e["id"],))
            conn.commit()
    return gone


# --- tick unico per la GUI ----------------------------------------------------------

def tick(now: datetime) -> int:
    """Rollover turni, pulizie, ore, contratti e stipendi. 1 se serve refresh."""
    changed = housekeeping_tick(now)
    dining_tick(now)
    reception_tick(now)
    if _cashback_tick(now):
        changed = True
    if contracts_tick(now.date()):
        changed = True
    if run_payroll(now.date()):
        changed = True
    return int(changed)
