"""Piccolo calendario per scegliere una data (stdlib calendar, zero dipendenze)."""

import calendar
import tkinter as tk
from datetime import date
from tkinter import ttk

from hotel import clock

from .time_view import MESI
from .utils import format_date_it, parse_date_it

GIORNI_BREVI = ("Lu", "Ma", "Me", "Gi", "Ve", "Sa", "Do")


class DatePicker(tk.Toplevel):
    def __init__(self, master, initial: date, on_pick):
        super().__init__(master)
        self.title("Scegli data")
        self.resizable(False, False)
        self.transient(master)
        self.on_pick = on_pick
        self.year, self.month = initial.year, initial.month
        self._build()

    def _build(self):
        for w in self.winfo_children():
            w.destroy()
        head = ttk.Frame(self, padding=6)
        head.pack()
        ttk.Button(head, text="<", width=3, command=self._prev).pack(side="left")
        ttk.Label(head, width=18, anchor="center",
                  text=f"{MESI[self.month - 1].capitalize()} {self.year}"
                  ).pack(side="left")
        ttk.Button(head, text=">", width=3, command=self._next).pack(side="left")

        grid = ttk.Frame(self, padding=(6, 0, 6, 6))
        grid.pack()
        for c, wd in enumerate(GIORNI_BREVI):
            ttk.Label(grid, text=wd, width=3, anchor="center").grid(row=0, column=c)
        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(
            self.year, self.month)
        for r, week in enumerate(weeks, start=1):
            for c, day in enumerate(week):
                if day:
                    ttk.Button(grid, text=str(day), width=3,
                               command=lambda d=day: self._pick(d)
                               ).grid(row=r, column=c, padx=1, pady=1)

    def _shift(self, delta):
        m = self.month - 1 + delta
        self.year += m // 12
        self.month = m % 12 + 1
        self._build()

    def _prev(self):
        self._shift(-1)

    def _next(self):
        self._shift(1)

    def _pick(self, day):
        self.on_pick(date(self.year, self.month, day))
        self.destroy()


def choose_into(master, var: tk.StringVar, after=None):
    """Apre il calendario partendo dal valore corrente del campo e lo riscrive."""
    try:
        initial = parse_date_it(var.get())
    except ValueError:
        initial = clock.today()

    def on_pick(picked):
        var.set(format_date_it(picked))
        if after:
            after()

    DatePicker(master, initial, on_pick)
