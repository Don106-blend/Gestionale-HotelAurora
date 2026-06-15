"""Orologio di sistema con override opzionale.

Tutto il programma legge la data odierna da `clock.today()` invece che da
`date.today()`, cosi lo strumento di debug puo simulare un giorno diverso
senza modificare l'orologio reale del sistema. L'override vale solo finche
l'app resta aperta (non viene salvato).
"""

from datetime import date

_override: date | None = None


def today() -> date:
    return _override if _override is not None else date.today()


def set_today(day: date | None) -> None:
    """Imposta la data simulata; con None ripristina la data reale."""
    global _override
    _override = day
