"""Tasse di fine mese: IVA accantonata e rate dei prestiti.

L'IVA sui soggiorni non e piu una perdita immediata: si incassa il 100% del
ricavato e l'IVA maturata si versa al cambio mese, insieme alle rate della
banca (bank.pay_due). Il mese di avvio registra soltanto, niente addebiti
retroattivi (stesso pattern delle bollette).
"""

from . import bank, budget
from .database import kv_get, kv_set


def accrue_vat(amount: float) -> None:
    """Accantona IVA incassata: verra versata a fine mese."""
    kv_set("vat_due", round((kv_get("vat_due", 0.0) or 0.0) + amount, 2))


def vat_due() -> float:
    return kv_get("vat_due", 0.0) or 0.0


def settle(today) -> float:
    """Al cambio mese versa IVA maturata + rate dei prestiti.
    Ritorna il totale addebitato."""
    month = today.strftime("%Y-%m")
    last = kv_get("last_taxes")
    if last == month:
        return 0.0
    kv_set("last_taxes", month)
    if last is None:          # primo avvio: registra il mese e basta
        return 0.0
    total = 0.0
    due = vat_due()
    if due > 0:
        budget.record(budget.LOSS, "IVA", due, f"IVA versata ({month})")
        kv_set("vat_due", 0.0)
        total += due
    total += bank.pay_due(today)
    return round(total, 2)
