"""Foglio pulizie: calcolo ore per camera e bilanciamento operatori."""

import math
from dataclasses import dataclass
from datetime import date

from . import constants, reservations

FRIDAY = 4


@dataclass
class CleaningTask:
    room_number: int
    hours: float
    note: str


def tasks_for_day(day: date) -> list[CleaningTask]:
    """Camere da pulire nel giorno indicato, con relative ore.

    - giorno di check-out: 0.5h (RES in suite: 3h)
    - rimanenza (dal giorno dopo il check-in): 0.25h
    - suite con soluzione RES: nessuna pulizia tranne il venerdi (1h)
    """
    tasks = []
    for res in reservations.active_on(day, include_checked_out=True):
        checkin = date.fromisoformat(res["checkin_date"])
        checkout = date.fromisoformat(res["checkout_date"])
        is_res_suite = res["is_suite"] and res["board"] == "RES"

        if is_res_suite:
            if day == checkout:
                tasks.append(CleaningTask(res["room_number"],
                                          constants.CLEAN_RES_CHECKOUT_HOURS,
                                          "check-out RES"))
            elif day.weekday() == FRIDAY and day > checkin:
                tasks.append(CleaningTask(res["room_number"],
                                          constants.CLEAN_RES_FRIDAY_HOURS,
                                          "RES venerdi"))
        elif day == checkout:
            tasks.append(CleaningTask(res["room_number"],
                                      constants.CLEAN_CHECKOUT_HOURS,
                                      "check-out"))
        elif day > checkin:
            tasks.append(CleaningTask(res["room_number"],
                                      constants.CLEAN_STAYOVER_HOURS,
                                      "rimanenza"))
    return tasks


def assign_operators(tasks: list[CleaningTask]) -> list[list[CleaningTask]]:
    """Distribuisce i lavori sul minor numero di operatori (max 8h ciascuno)
    mantenendo i carichi bilanciati (assegnazione LPT: il lavoro piu lungo
    va sempre all'operatore meno carico)."""
    total = sum(t.hours for t in tasks)
    if total == 0:
        return []
    n_ops = max(1, math.ceil(total / constants.OPERATOR_MAX_HOURS))
    operators: list[list[CleaningTask]] = [[] for _ in range(n_ops)]
    loads = [0.0] * n_ops
    for task in sorted(tasks, key=lambda t: -t.hours):
        i = loads.index(min(loads))
        operators[i].append(task)
        loads[i] += task.hours
    return operators


def sheet_text(day: date) -> str:
    """Foglio ore pulizie in formato testo."""
    tasks = tasks_for_day(day)
    out = [f"HotelAurora - Foglio pulizie del {day.strftime('%d/%m/%Y')}", ""]
    if not tasks:
        out.append("Nessuna camera da pulire.")
        return "\n".join(out)

    for i, op_tasks in enumerate(assign_operators(tasks), start=1):
        op_total = sum(t.hours for t in op_tasks)
        out.append(f"Operatore {i}  (totale {op_total:g}h)")
        for t in sorted(op_tasks, key=lambda t: t.room_number):
            out.append(f"  Camera {t.room_number:<6} {t.hours:g}h"
                       f"   ({t.note})")
        out.append("")
    out.append(f"Totale complessivo: {sum(t.hours for t in tasks):g}h"
               f" su {len(tasks)} camere")
    return "\n".join(out)
