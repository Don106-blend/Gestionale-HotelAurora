"""Fogli pasti: colazione, pranzo e cena per un dato giorno."""

from datetime import date

from . import constants, reservations

MEALS = {
    "colazione": "breakfast",
    "pranzo": "lunch",
    "cena": "dinner",
}


def _serves_meal(res, meal_attr: str, day: date) -> bool:
    board = constants.BOARDS[res["board"]]
    if not getattr(board, meal_attr):
        return False
    checkin = date.fromisoformat(res["checkin_date"])
    checkout = date.fromisoformat(res["checkout_date"])
    if meal_attr == "breakfast":
        # la colazione parte dal mattino dopo la prima notte,
        # inclusa quella del giorno di check-out
        return checkin < day <= checkout
    # pranzo e cena dal giorno di arrivo fino alla vigilia del check-out
    return checkin <= day < checkout


def meal_rows(meal_it: str, day: date) -> list[tuple[int, str, int]]:
    """Righe (camera, nome ospite, n. ospiti) per il pasto indicato."""
    meal_attr = MEALS[meal_it]
    rows = []
    for res in reservations.active_on(day):
        if _serves_meal(res, meal_attr, day):
            pax = res["adults"] + res["children"]
            rows.append((res["room_number"],
                         reservations.guest_display_name(res), pax))
    return rows


def sheet_text(meal_it: str, day: date) -> str:
    """Foglio pasto in formato testo."""
    rows = meal_rows(meal_it, day)
    out = [f"HotelAurora - {meal_it.capitalize()} del"
           f" {day.strftime('%d/%m/%Y')}", ""]
    if not rows:
        out.append("Nessun ospite previsto.")
        return "\n".join(out)
    out.append(f"{'Camera':<8} {'Ospite':<30} {'N. ospiti':>9}")
    out.append("-" * 49)
    for room, name, pax in rows:
        out.append(f"{room:<8} {name:<30} {pax:>9}")
    out.append("-" * 49)
    out.append(f"{'Totale ospiti':<39} {sum(r[2] for r in rows):>9}")
    return "\n".join(out)
