"""Sala pasti: tavoli, sedie, layout a griglia e assegnazione dei posti.

I tavoli vivono su una griglia (col, row) spostabile dall'editor di layout.
Le sedie si comprano una a una e finiscono da sole sul tavolo piu scarico.
A tavola: un gruppo per tavolo (gli ospiti della stessa camera stanno insieme
e non si mischiano con chi non conoscono).
"""

from . import estate
from .database import get_conn

GRID_COLS, GRID_ROWS = 6, 4          # celle del layout della sala

TABLE_SEATS = {"single": 4, "double": 6}
TABLE_COSTS = {"single": 50.0, "double": 100.0}
CHAIR_COST = 20.0


class DiningError(estate.EstateError):
    """Acquisto/spostamento in sala non possibile."""


def tables():
    return get_conn().execute(
        "SELECT * FROM dining_tables ORDER BY id").fetchall()


def counts() -> dict:
    row = get_conn().execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(chairs), 0) AS chairs"
        " FROM dining_tables").fetchone()
    return {"tavoli": row["n"], "sedie": row["chairs"]}


def _free_cell() -> tuple:
    used = {(t["col"], t["row"]) for t in tables()}
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            if (col, row) not in used:
                return col, row
    raise DiningError("Sala piena: nessuna cella libera per un tavolo.")


def buy_table(kind: str) -> int:
    if kind not in TABLE_SEATS:
        raise DiningError("Tipo di tavolo sconosciuto.")
    col, row = _free_cell()
    estate._spend(TABLE_COSTS[kind],
                  f"Tavolo {'doppio' if kind == 'double' else 'singolo'}")
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO dining_tables (kind, chairs, col, row)"
        " VALUES (?, 0, ?, ?)", (kind, col, row))
    conn.commit()
    return cur.lastrowid


def buy_chair() -> int:
    """Compra una sedia e la mette al tavolo con meno sedie (se c'e posto)."""
    target = None
    for t in sorted(tables(), key=lambda t: (t["chairs"], t["id"])):
        if t["chairs"] < TABLE_SEATS[t["kind"]]:
            target = t
            break
    if target is None:
        raise DiningError("Tutti i tavoli sono gia al completo di sedie.")
    estate._spend(CHAIR_COST, f"Sedia (tavolo {target['id']})")
    conn = get_conn()
    conn.execute("UPDATE dining_tables SET chairs = chairs + 1 WHERE id = ?",
                 (target["id"],))
    conn.commit()
    return target["id"]


def move_table(table_id: int, col: int, row: int) -> None:
    if not (0 <= col < GRID_COLS and 0 <= row < GRID_ROWS):
        raise DiningError("Fuori dalla sala.")
    conn = get_conn()
    taken = conn.execute(
        "SELECT 1 FROM dining_tables WHERE col = ? AND row = ? AND id != ?",
        (col, row, table_id)).fetchone()
    if taken:
        raise DiningError("C'e gia un tavolo in quella posizione.")
    conn.execute("UPDATE dining_tables SET col = ?, row = ? WHERE id = ?",
                 (col, row, table_id))
    conn.commit()


# --- posti a sedere -------------------------------------------------------------

def assign_tables(groups: dict, tabs: list) -> tuple:
    """Best-fit: gruppi grandi prima, ogni tavolo ospita un solo gruppo.

    groups: {reservation_id: [ospiti]}. Ritorna ({table_id: (res_id, ospiti)},
    [(res_id, ospiti) senza tavolo]).
    """
    free = sorted(tabs, key=lambda t: t["chairs"])
    placements, waiting = {}, []
    for res_id, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        for i, t in enumerate(free):
            if t["chairs"] >= len(members):
                placements[t["id"]] = (res_id, members)
                free.pop(i)
                break
        else:
            waiting.append((res_id, members))
    return placements, waiting


def seating(now):
    """(pasto, {table_id: (res_id, ospiti)}, in_attesa) per il pasto in corso."""
    from . import guest_state, guests   # differiti: evitano cicli di import
    meal = guest_state.current_meal(now)
    if meal is None:
        return None, {}, []
    groups = {}
    for g in guests.checked_in_guests():
        if guest_state.is_eating(g["id"], g["board"], meal, now):
            groups.setdefault(g["reservation_id"], []).append(g)
    placements, waiting = assign_tables(groups, tables())
    return meal, placements, waiting
