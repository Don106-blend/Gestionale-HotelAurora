"""Connessione SQLite, schema e popolamento iniziale delle camere."""

import json
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
    inserted    INTEGER NOT NULL DEFAULT 0,
    kind        TEXT NOT NULL DEFAULT 'request',  -- 'request' | 'spam'
    rejected    INTEGER NOT NULL DEFAULT 0,
    archived    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS blacklist (
    first_name TEXT NOT NULL,
    last_name  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meals_served (
    guest_id INTEGER NOT NULL,
    day      TEXT NOT NULL,
    meal     TEXT NOT NULL,
    ok       INTEGER NOT NULL DEFAULT 1,   -- 0 = pasto mancato (reclamo)
    PRIMARY KEY (guest_id, day, meal)
);

CREATE TABLE IF NOT EXISTS employees (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name  TEXT NOT NULL,
    role       TEXT NOT NULL,              -- 'pulizie' | 'sala'
    hourly     REAL NOT NULL DEFAULT 7.0,  -- paga oraria lorda
    hired_on   TEXT NOT NULL,
    served     INTEGER NOT NULL DEFAULT 0  -- ospiti serviti (solo sala)
);

CREATE TABLE IF NOT EXISTS work_hours (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    day         TEXT NOT NULL,
    hours       REAL NOT NULL,
    paid        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dining_tables (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    kind   TEXT NOT NULL DEFAULT 'single',  -- 'single' (4 posti) | 'double' (6)
    chairs INTEGER NOT NULL DEFAULT 0,
    col    INTEGER NOT NULL DEFAULT 0,
    row    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reviews (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    day   TEXT NOT NULL,
    guest TEXT NOT NULL,
    stars INTEGER NOT NULL,
    text  TEXT NOT NULL
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
        _seed_dining(_conn)
        _conn.commit()
    return _conn


def kv_get(key: str, default=None):
    """Legge un valore JSON dalla tabella settings (KV di gioco)."""
    row = get_conn().execute(
        "SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def kv_set(key: str, value) -> None:
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                 (key, json.dumps(value)))
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    # colonne aggiunte dopo: le inserisce nei DB esistenti (CREATE non basta)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(reservation_guests)")]
    if "checked_in_at" not in cols:
        conn.execute("ALTER TABLE reservation_guests ADD COLUMN checked_in_at TEXT")
    mail_cols = [r[1] for r in conn.execute("PRAGMA table_info(mails)")]
    for col, ddl in (("kind", "TEXT NOT NULL DEFAULT 'request'"),
                     ("rejected", "INTEGER NOT NULL DEFAULT 0"),
                     ("archived", "INTEGER NOT NULL DEFAULT 0")):
        if col not in mail_cols:
            conn.execute(f"ALTER TABLE mails ADD COLUMN {col} {ddl}")
    ms_cols = [r[1] for r in conn.execute("PRAGMA table_info(meals_served)")]
    if "ok" not in ms_cols:
        conn.execute("ALTER TABLE meals_served ADD COLUMN ok INTEGER"
                     " NOT NULL DEFAULT 1")
    res_cols = [r[1] for r in conn.execute("PRAGMA table_info(reservations)")]
    if "complaints" not in res_cols:      # reclami subiti durante il soggiorno
        conn.execute("ALTER TABLE reservations ADD COLUMN complaints INTEGER"
                     " NOT NULL DEFAULT 0")
    room_cols = [r[1] for r in conn.execute("PRAGMA table_info(rooms)")]
    if "wear" not in room_cols:           # usura: check-out dall'ultimo rinnovo
        conn.execute("ALTER TABLE rooms ADD COLUMN wear INTEGER"
                     " NOT NULL DEFAULT 0")


def _seed_rooms(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] > 0:
        return
    # hotel scalabile: si parte con poche camere al piano 1 (le ultime suite)
    for n in range(1, constants.INITIAL_ROOMS + 1):
        is_suite = n > constants.INITIAL_ROOMS - constants.INITIAL_SUITES
        max_adults = (constants.SUITE_MAX_ADULTS if is_suite
                      else constants.STD_MAX_ADULTS)
        conn.execute(
            "INSERT INTO rooms (number, floor, is_suite, max_adults, max_children)"
            " VALUES (?, ?, ?, ?, ?)",
            (100 + n, 1, int(is_suite), max_adults, constants.MAX_CHILDREN))


def _seed_dining(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM dining_tables").fetchone()[0] > 0:
        return
    # sala pasti di partenza: 4 tavoli singoli con 4 sedie ciascuno
    for i in range(4):
        conn.execute("INSERT INTO dining_tables (kind, chairs, col, row)"
                     " VALUES ('single', 4, ?, 0)", (i,))
