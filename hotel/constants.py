"""Costanti di dominio per HotelAurora."""

from dataclasses import dataclass

FLOORS = (1, 2, 3)
ROOMS_PER_FLOOR = 27
SUITE_NUMBERS = range(23, 28)  # camere 23-27 di ogni piano

STD_MAX_ADULTS = 2
SUITE_MAX_ADULTS = 4
MAX_CHILDREN = 1

VAT_RATE = 0.22
PAYMENT_DEFAULT = "Pagdir"

# Ore di lavoro per le pulizie
CLEAN_CHECKOUT_HOURS = 0.5
CLEAN_STAYOVER_HOURS = 0.25
CLEAN_RES_FRIDAY_HOURS = 1.0
CLEAN_RES_CHECKOUT_HOURS = 3.0
OPERATOR_MAX_HOURS = 8.0


@dataclass(frozen=True)
class Board:
    code: str
    label: str
    breakfast: bool
    lunch: bool
    dinner: bool


BOARDS = {
    "BB": Board("BB", "Bed & Breakfast", True, False, False),
    "RO": Board("RO", "Room only", False, False, False),
    "HB": Board("HB", "Half Board", True, False, True),
    "FB": Board("FB", "Full Board", True, True, True),
    "RES": Board("RES", "Residence", False, False, False),
}

DOCUMENT_TYPES = ("Carta d'identita", "Passaporto", "Patente", "Altro")

# Colori interfaccia (sobri)
COLOR_FREE = "#ffffff"
COLOR_OCCUPIED = "#9fc99f"
COLOR_CHECKOUT_DAY = "#e3d27a"        # striscia a destra: check-out oggi
COLOR_BOOKED_BAR = "#a8bdd4"
COLOR_DIRTY_LINE = "#8a8a8a"
COLOR_BLOCKED_LINE = "#b03030"
COLOR_ARRIVAL_TODAY = "#cc2e88"       # quadrato in alto a destra: arrivo oggi
COLOR_ARRIVAL_NEXT = "#2d6cdf"        # quadrato in basso a destra: arrivo domani
