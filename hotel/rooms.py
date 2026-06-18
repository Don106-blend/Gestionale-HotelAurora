"""Operazioni sulle camere (stato pulizia e blocco)."""

from .database import get_conn


def all_rooms():
    return get_conn().execute("SELECT * FROM rooms ORDER BY number").fetchall()


def floors() -> list:
    """Piani posseduti (anche se ancora senza camere), in ordine."""
    from . import estate   # import differito: estate usa il bilancio
    return sorted(estate.owned_floors())


def get_room(number: int):
    return get_conn().execute(
        "SELECT * FROM rooms WHERE number = ?", (number,)).fetchone()


def set_dirty(number: int, dirty: bool) -> None:
    conn = get_conn()
    conn.execute("UPDATE rooms SET dirty = ? WHERE number = ?",
                 (int(dirty), number))
    conn.commit()


def set_blocked(number: int, blocked: bool) -> None:
    conn = get_conn()
    conn.execute("UPDATE rooms SET blocked = ? WHERE number = ?",
                 (int(blocked), number))
    conn.commit()
