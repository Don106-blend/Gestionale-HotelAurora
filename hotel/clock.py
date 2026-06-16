"""Orologio con data/ora simulata e avanzamento in scala (gameplay).

`now()`/`today()` leggono il tempo simulato se impostato, altrimenti quello
reale. Con `running=True`, `tick()` fa avanzare il tempo simulato di `scale`
ore di gioco per ogni ora reale (default 24: un giorno di gioco per ora reale).
"""

import time
from datetime import date, datetime, timedelta

_sim: datetime | None = None
_last_mono: float | None = None
scale: float = 24.0      # ore di gioco per 1 ora reale (base, dal debug)
running: bool = False

# Controllo velocita "al volo": moltiplicatore SOPRA le basi del debug, non le
# modifica. speed = 1x/2x/5x; realtime = orologio a tempo reale; paused = fermo.
speed: float = 1.0
paused: bool = False
realtime: bool = False

# (ora inizio, ora fine, nome, colore) — la Notte scavalca la mezzanotte
SHIFTS = (
    (7, 12, "Mattina", "#cfe2f3"),
    (12, 15, "Pranzo", "#fff2cc"),
    (15, 19, "Pomeriggio", "#fce5cd"),
    (19, 23, "Sera", "#d9d2e9"),
    (23, 7, "Notte", "#c9ccd1"),
)


def now() -> datetime:
    return _sim if _sim is not None else datetime.now()


def today() -> date:
    return now().date()


def set_now(dt: datetime | None) -> None:
    global _sim
    _sim = dt


def set_today(day: date | None) -> None:
    """Imposta la data simulata mantenendo l'ora; None = torna al tempo reale."""
    global _sim
    _sim = None if day is None else datetime.combine(day, now().time())


def tick() -> None:
    """Avanza il tempo simulato in base al tempo reale trascorso."""
    global _sim, _last_mono
    mono = time.monotonic()
    if not running or paused:
        _last_mono = mono
        return
    if _sim is None:
        _sim = datetime.now()
    if _last_mono is not None:
        factor = 1.0 if realtime else scale * speed
        _sim += timedelta(seconds=(mono - _last_mono) * factor)
    _last_mono = mono


def freq_factor() -> float:
    """Moltiplicatore comune a tutte le frequenze di gioco (mail, reception...).

    0 in pausa, 1 a tempo reale, altrimenti la velocita selezionata.
    """
    if paused:
        return 0.0
    return 1.0 if realtime else speed


def shift(dt: datetime | None = None) -> tuple[str, str]:
    """(nome, colore) del turno della giornata per l'ora indicata."""
    h = (dt or now()).hour
    for start, end, name, color in SHIFTS:
        inside = start <= h < end if start < end else (h >= start or h < end)
        if inside:
            return name, color
    return SHIFTS[-1][2], SHIFTS[-1][3]
