"""Finestra 'Orario': orologio, data, ora e turno del tempo simulato."""

import tkinter as tk
from tkinter import ttk

from hotel import clock

GIORNI = ("lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato",
          "domenica")
MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre")


def long_date(dt) -> str:
    return f"{GIORNI[dt.weekday()]} {dt.day} {MESI[dt.month - 1]} {dt.year}"


class TimeWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Orario")
        self.resizable(False, False)
        # niente transient: finestra indipendente dalla dashboard (come le mail)
        frame = ttk.Frame(self, padding=16)
        frame.pack()
        self.time_lbl = tk.Label(frame, font=("TkDefaultFont", 30, "bold"))
        self.time_lbl.pack()
        self.date_lbl = tk.Label(frame, font=("TkDefaultFont", 12))
        self.date_lbl.pack(pady=(2, 8))
        self.shift_lbl = tk.Label(frame, font=("TkDefaultFont", 14, "bold"),
                                  padx=12, pady=4)
        self.shift_lbl.pack()
        self._refresh()

    def _refresh(self):
        if not self.winfo_exists():
            return
        n = clock.now()
        self.time_lbl.config(text=n.strftime("%H:%M:%S"))
        self.date_lbl.config(text=long_date(n))
        name, color = clock.shift(n)
        self.shift_lbl.config(text=f"Turno: {name}", background=color)
        self.after(1000, self._refresh)
