"""Connessione SQLite, schema e popolamento iniziale delle camere."""

import sqlite3
from pathlib import Path

from . import constants

DB_PATH = Path(__file__).resolve().parent.parent / "hotel.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    number      INTEGER PRIMARY KEY,
    floor       INTEGER NOT NULL,
    is_suite    INTEGER NOT NULL DEFAULT 0,
    max_adults  INTEGER NOT NULL,
    max_children INTEGER NOT NULL,
    dirty       INTEGER NOT NULL DEFAULT 0,
    blocked     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reservations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL,
    room_number     INTEGER NOT NULL REFERENCES rooms(number),
    first_name      TEXT NOT NULL DEFAULT '',
    last_name       TEXT NOT NULL DEFAULT '',
    checkin_date    TEXT NOT NULL,
    checkout_date   TEXT NOT NULL,
    adults          INTEGER NOT NULL,
    children        INTEGER NOT NULL DEFAULT 0,
    price_per_night REAL NOT NULL DEFAULT 0,
    board           TEXT NOT NULL DEFAULT 'RO',
    discount        REAL,
    phone           TEXT NOT NULL DEFAULT '',
    email           TEXT NOT NULL DEFAULT '',
    color           TEXT NOT NULL DEFAULT '',
    comments        TEXT NOT NULL DEFAULT '',
    payment         TEXT NOT NULL DEFAULT 'Pagdir',
    status          TEXT NOT NULL DEFAULT 'booked',
    created_at      TEXT NOT NULL DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS guests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name      TEXT NOT NULL DEFAULT '',
    last_name       TEXT NOT NULL DEFAULT '',
    birth_date      TEXT NOT NULL DEFAULT '',
    birth_place     TEXT NOT NULL DEFAULT '',
    document_type   TEXT NOT NULL DEFAULT '',
    document_number TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS reservation_guests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_id  INTEGER NOT NULL REFERENCES reservations(id),
    guest_id        INTEGER NOT NULL REFERENCES guests(id),
    is_child        INTEGER NOT NULL DEFAULT 0,
    checked_in_at   TEXT
);

CREATE TABLE IF NOT EXISTS ledger (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    day         TEXT NOT NULL,
    kind        TEXT NOT NULL,        -- 'income' | 'loss'
    category    TEXT NOT NULL,        -- 'Soggiorno', 'IVA', futuro: 'Bolletta'...
    amount      REAL NOT NULL,
    note        TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS mails (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at TEXT NOT NULL,
    sender      TEXT NOT NULL,
    subject     TEXT NOT NULL,
    body        TEXT NOT NULL,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    checkin     TEXT NOT NULL,
    checkout    TEXT NOT NULL,
    adults      INTEGER NOT NULL,
    children    INTEGER NOT NULL,
    board       TEXT NOT NULL,
    inserted    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reception (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_id INTEGER NOT NULL,
    kind           TEXT NOT NULL,     -- 'checkin' | 'checkout'
    first_name     TEXT NOT NULL,
    last_name      TEXT NOT NULL,
    is_child       INTEGER NOT NULL DEFAULT 0,
    arrived_at     TEXT NOT NULL
);
"""

_conn = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys = ON")
        _conn.executescript(_SCHEMA)
        _migrate(_conn)
        _seed_rooms(_conn)
        _conn.commit()
    return _conn


def _migrate(conn: sqlite3.Connection) -> None:
    # colonne aggiunte dopo: le inserisce nei DB esistenti (CREATE non basta)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(reservation_guests)")]
    if "checked_in_at" not in cols:
        conn.execute("ALTER TABLE reservation_guests ADD COLUMN checked_in_at TEXT")


def _seed_rooms(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] > 0:
        return
    for floor in constants.FLOORS:
        for n in range(1, constants.ROOMS_PER_FLOOR + 1):
            is_suite = n in constants.SUITE_NUMBERS
            max_adults = (constants.SUITE_MAX_ADULTS if is_suite
                          else constants.STD_MAX_ADULTS)
            conn.execute(
                "INSERT INTO rooms (number, floor, is_suite, max_adults, max_children)"
                " VALUES (?, ?, ?, ?, ?)",
                (floor * 100 + n, floor, int(is_suite), max_adults,
                 constants.MAX_CHILDREN),
            )
