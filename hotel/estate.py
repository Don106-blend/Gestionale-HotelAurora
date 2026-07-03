"""Patrimonio dell'hotel: setup iniziale, piani e acquisto camere.

Hotel scalabile: si parte con poche camere e se ne comprano altre col bilancio.
Costo camera: parte da 1000 e cresce di 250 a ogni acquisto; dopo le prime 10
camere acquistate l'incremento sale a 500. La suite costa il doppio.
Un piano nuovo costa 10000 e ospita al massimo 50 camere.
"""

from . import budget, constants
from .database import get_conn, kv_get, kv_set

ROOM_BASE_COST = 1000.0
ROOM_STEP = 250.0            # incremento per camera acquistata...
ROOM_STEP_HIGH = 500.0      # ...che sale dopo STEP_THRESHOLD acquisti
STEP_THRESHOLD = 10
FLOOR_COST = 10000.0
MAX_ROOMS_PER_FLOOR = 50

STARTING_BUDGET = 10000.0   # capitale con cui parte una nuova partita

# Dispensa cibo (AllFoods!): 1 unita = 1 pasto servito.
FOOD_UNIT_COST = 10.0
FOOD_INITIAL = 50           # unita al primo avvio
FOOD_CAP_BASE = 100         # capienza dispensa al primo avvio
FOOD_CAP_STEP = 50          # +50 a ogni potenziamento
FOOD_CAP_UPGRADE_BASE = 2000.0
FOOD_CAP_UPGRADE_MULT = 1.5  # il costo del potenziamento sale di 0,5x ogni volta


class EstateError(Exception):
    """Acquisto non possibile (saldo, piano pieno, ecc.)."""


# --- setup iniziale ----------------------------------------------------------

def is_setup_done() -> bool:
    return bool(kv_get("setup_done", False))


def complete_setup(user_name: str, hotel_name: str) -> None:
    kv_set("user_name", user_name.strip() or "Direttore")
    kv_set("hotel_name", hotel_name.strip() or "HotelAurora")
    kv_set("setup_done", True)


def grant_starting_capital() -> None:
    """Accredita il capitale iniziale, una volta sola per partita."""
    if kv_get("capital_granted", False):
        return
    budget.record(budget.INCOME, "Capitale iniziale", STARTING_BUDGET,
                  "Fondo di partenza")
    kv_set("capital_granted", True)


def user_name() -> str:
    return kv_get("user_name", "Direttore")


def hotel_name() -> str:
    return kv_get("hotel_name", "HotelAurora")


# --- piani -------------------------------------------------------------------

def owned_floors() -> list:
    return kv_get("floors", [1])


def floor_room_count(floor: int) -> int:
    return get_conn().execute(
        "SELECT COUNT(*) FROM rooms WHERE floor = ?", (floor,)).fetchone()[0]


def next_floor_number() -> int:
    return max(owned_floors()) + 1


def buy_floor() -> int:
    new = next_floor_number()
    _spend(FLOOR_COST, f"Nuovo piano {new}")
    kv_set("floors", owned_floors() + [new])
    return new


# --- camere ------------------------------------------------------------------

def rooms_purchased() -> int:
    # contatore esplicito (non il numero di camere nel DB): cosi il costo non
    # dipende da camere preesistenti / vecchi salvataggi.
    return kv_get("rooms_purchased", 0)


def room_cost(suite: bool = False) -> float:
    from . import amenities   # differito: amenities usa estate._spend
    p = rooms_purchased()
    if p <= STEP_THRESHOLD:
        base = ROOM_BASE_COST + ROOM_STEP * p
    else:
        base = (ROOM_BASE_COST + ROOM_STEP * STEP_THRESHOLD
                + ROOM_STEP_HIGH * (p - STEP_THRESHOLD))
    # camere migliorate/luxury: costruire (e vendere) costa di piu
    return round(base * (2 if suite else 1) * amenities.price_mult(), 2)


def _next_room_number(floor: int) -> int:
    used = {r["number"] % 100 for r in get_conn().execute(
        "SELECT number FROM rooms WHERE floor = ?", (floor,)).fetchall()}
    for n in range(1, MAX_ROOMS_PER_FLOOR + 1):
        if n not in used:
            return floor * 100 + n   # ponytail: max 50 camere/piano -> n < 100
    raise EstateError("Piano pieno (max 50 camere).")


def buy_room(floor: int, suite: bool = False) -> int:
    if floor not in owned_floors():
        raise EstateError("Piano non posseduto.")
    if floor_room_count(floor) >= MAX_ROOMS_PER_FLOOR:
        raise EstateError("Piano pieno (max 50 camere).")
    number = _next_room_number(floor)
    _spend(room_cost(suite), f"Camera {number}" + (" (suite)" if suite else ""))
    max_adults = constants.SUITE_MAX_ADULTS if suite else constants.STD_MAX_ADULTS
    get_conn().execute(
        "INSERT INTO rooms (number, floor, is_suite, max_adults, max_children)"
        " VALUES (?, ?, ?, ?, ?)",
        (number, floor, int(suite), max_adults, constants.MAX_CHILDREN))
    kv_set("rooms_purchased", rooms_purchased() + 1)
    get_conn().commit()
    return number


def _spend(cost: float, note: str) -> None:
    if budget.totals()["balance"] < cost:
        raise EstateError("Saldo insufficiente.")
    budget.record(budget.LOSS, "Ristrutturazione", cost, note)


# --- bollette e rinnovo camere ------------------------------------------------

UTILITY_BASE = 150.0      # utenze mensili fisse
UTILITY_PER_ROOM = 2.0    # + quota per camera posseduta
RENOVATE_COST = 300.0     # rinnovo di una camera logora (azzera l'usura)


def run_utilities(today) -> float:
    """Al cambio mese addebita le utenze (base + quota camere). Il primo mese
    di gioco e gratis: registra solo il mese di partenza."""
    month = today.strftime("%Y-%m")
    last = kv_get("last_utilities")
    if last == month:
        return 0.0
    kv_set("last_utilities", month)
    if last is None:            # primo avvio: nessun addebito retroattivo
        return 0.0
    n_rooms = get_conn().execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    amount = round(UTILITY_BASE + UTILITY_PER_ROOM * n_rooms, 2)
    # receptionist 'contabile' assunto: ottimizza le utenze (-20%)
    if get_conn().execute("SELECT 1 FROM employees WHERE role = 'reception'"
                          " AND bonus = 'contabile' LIMIT 1").fetchone():
        amount = round(amount * 0.8, 2)
    budget.record(budget.LOSS, "Bollette", amount, f"Utenze {month}")
    return amount


def renovate_room(number: int) -> None:
    """Rinnova una camera logora: costa RENOVATE_COST e azzera l'usura."""
    room = get_conn().execute("SELECT * FROM rooms WHERE number = ?",
                              (number,)).fetchone()
    if room is None:
        raise EstateError("Camera inesistente.")
    if room["wear"] < constants.WEAR_LIMIT:
        raise EstateError("La camera non ha bisogno di rinnovo.")
    _spend(RENOVATE_COST, f"Rinnovo camera {number}")
    get_conn().execute("UPDATE rooms SET wear = 0 WHERE number = ?", (number,))
    get_conn().commit()


# --- dispensa cibo (AllFoods!) ----------------------------------------------

def food() -> int:
    return kv_get("food", FOOD_INITIAL)


def food_cap() -> int:
    return FOOD_CAP_BASE + FOOD_CAP_STEP * kv_get("food_cap_upgrades", 0)


def set_food(n: int) -> None:
    """Debug: imposta le unita possedute (limitate alla capienza)."""
    kv_set("food", max(0, min(int(n), food_cap())))


def consume_food(n: int = 1) -> bool:
    """Consuma n unita; False (senza scalare) se non bastano."""
    cur = food()
    if cur < n:
        return False
    kv_set("food", cur - n)
    return True


def buy_food(units: int) -> int:
    units = int(units)
    if units <= 0:
        raise EstateError("Quantita non valida.")
    space = food_cap() - food()
    if units > space:
        raise EstateError(f"Capienza insufficiente: spazio per {space} unita.")
    _spend(FOOD_UNIT_COST * units, f"AllFoods! x{units}")
    kv_set("food", food() + units)
    return food()


def food_cap_upgrade_cost() -> float:
    return round(FOOD_CAP_UPGRADE_BASE
                 * FOOD_CAP_UPGRADE_MULT ** kv_get("food_cap_upgrades", 0), 2)


def upgrade_food_cap() -> int:
    _spend(food_cap_upgrade_cost(), "Aumento capienza dispensa")
    kv_set("food_cap_upgrades", kv_get("food_cap_upgrades", 0) + 1)
    return food_cap()


# --- reset totale ------------------------------------------------------------

def reset_all() -> None:
    """Cancella tutto: alla riapertura il gestionale riparte dal primo avvio."""
    conn = get_conn()
    for table in ("reservation_guests", "reservations", "guests", "ledger",
                  "mails", "reception", "blacklist", "meals_served",
                  "work_hours", "employees", "dining_tables", "reviews",
                  "problems", "rooms", "settings"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
