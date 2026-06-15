"""Utility condivise per l'interfaccia."""

from datetime import date, datetime


def parse_date_it(text: str) -> date:
    """Converte 'gg/mm/aaaa' in date. Solleva ValueError se non valida."""
    return datetime.strptime(text.strip(), "%d/%m/%Y").date()


def format_date_it(day: date) -> str:
    return day.strftime("%d/%m/%Y")
