"""Banca: prestiti all'hotel, rimborsati a rate mensili con le tasse.

Ogni prestito ha un tasso annuo (TAN): il totale da restituire e il capitale
piu gli interessi, spalmato su 12 rate mensili. Le rate vengono addebitate a
fine mese insieme a IVA e bollette (vedi taxes.settle).
"""

from . import budget
from .database import get_conn, kv_get, kv_set

# capitale -> (tasso annuo, mesi di rimborso). Piu chiedi, piu ti costa.
LOAN_TIERS = {
    5000:  {"rate": 0.05, "months": 12},
    15000: {"rate": 0.08, "months": 12},
    40000: {"rate": 0.12, "months": 12},
}
MAX_LOANS = 3   # prestiti aperti contemporaneamente


class BankError(Exception):
    """Operazione bancaria non possibile."""


def loans() -> list:
    return kv_get("loans", [])


def total_debt() -> float:
    return round(sum(l["remaining"] for l in loans()), 2)


def monthly_due() -> float:
    return round(sum(l["installment"] for l in loans()), 2)


def take_loan(principal: int) -> None:
    if principal not in LOAN_TIERS:
        raise BankError("Importo di prestito non disponibile.")
    if len(loans()) >= MAX_LOANS:
        raise BankError(f"Massimo {MAX_LOANS} prestiti aperti.")
    info = LOAN_TIERS[principal]
    total = round(principal * (1 + info["rate"]), 2)
    installment = round(total / info["months"], 2)
    budget.record(budget.INCOME, "Prestito", float(principal),
                  f"Prestito € {principal:,} @ {info['rate'] * 100:g}% TAN")
    kv_set("loans", loans() + [{
        "principal": principal, "rate": info["rate"],
        "remaining": total, "installment": installment}])


def pay_due(today) -> float:
    """Addebita una rata per ogni prestito aperto. Ritorna il totale pagato."""
    paid, still_open = 0.0, []
    for l in loans():
        rate_pay = min(l["remaining"], l["installment"])
        budget.record(budget.LOSS, "Rata prestito", rate_pay,
                      f"Rata prestito € {l['principal']:,}")
        paid += rate_pay
        remaining = round(l["remaining"] - rate_pay, 2)
        if remaining > 0.01:
            still_open.append({**l, "remaining": remaining})
    kv_set("loans", still_open)
    return round(paid, 2)
