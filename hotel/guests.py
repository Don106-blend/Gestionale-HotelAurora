"""Anagrafica ospiti, riutilizzabile per gli ospiti abituali."""

from .database import get_conn


def search(term: str):
    """Cerca ospiti per nome o cognome (per il richiamo degli abituali)."""
    like = f"%{term.strip()}%"
    return get_conn().execute(
        "SELECT * FROM guests WHERE first_name LIKE ? OR last_name LIKE ?"
        " ORDER BY last_name, first_name LIMIT 30", (like, like)).fetchall()


def all_guests():
    return get_conn().execute(
        "SELECT * FROM guests ORDER BY last_name, first_name").fetchall()


def for_reservation(res_id: int):
    """Ospiti registrati per la prenotazione, con id riga, check-in e board."""
    return get_conn().execute(
        "SELECT g.*, rg.id AS rg_id, rg.reservation_id, rg.checked_in_at,"
        " rg.is_child, r.board FROM reservation_guests rg"
        " JOIN guests g ON g.id = rg.guest_id"
        " JOIN reservations r ON r.id = rg.reservation_id"
        " WHERE rg.reservation_id = ? ORDER BY rg.id", (res_id,)).fetchall()


def checked_in_guests():
    """Tutti gli ospiti attualmente in hotel (con board e camera)."""
    return get_conn().execute(
        "SELECT g.*, rg.id AS rg_id, rg.reservation_id, rg.checked_in_at,"
        " r.board, r.room_number FROM reservation_guests rg"
        " JOIN guests g ON g.id = rg.guest_id"
        " JOIN reservations r ON r.id = rg.reservation_id"
        " WHERE r.status = 'checked_in' ORDER BY r.room_number, rg.id").fetchall()


def upsert(data: dict) -> int:
    """Riusa l'ospite se gia presente (stesso nome, cognome e data di nascita),
    aggiornandone i dati; altrimenti lo crea. Ritorna l'id."""
    conn = get_conn()
    first = data["first_name"].strip()
    last = data["last_name"].strip()
    birth = data.get("birth_date", "").strip()

    existing = None
    if first and last:
        existing = conn.execute(
            "SELECT id FROM guests WHERE first_name = ? COLLATE NOCASE"
            " AND last_name = ? COLLATE NOCASE AND birth_date = ?",
            (first, last, birth)).fetchone()

    fields = (first, last, birth,
              data.get("birth_place", "").strip(),
              data.get("document_type", "").strip(),
              data.get("document_number", "").strip())
    if existing:
        conn.execute(
            "UPDATE guests SET first_name = ?, last_name = ?, birth_date = ?,"
            " birth_place = ?, document_type = ?, document_number = ?"
            " WHERE id = ?", fields + (existing["id"],))
        conn.commit()
        return existing["id"]
    cur = conn.execute(
        "INSERT INTO guests (first_name, last_name, birth_date, birth_place,"
        " document_type, document_number) VALUES (?, ?, ?, ?, ?, ?)", fields)
    conn.commit()
    return cur.lastrowid
