"""Scheda 'Sala Pranzo' (debug): ospiti che stanno facendo il pasto in corso."""

import tkinter as tk
from tkinter import ttk

from hotel import clock, guest_state, guests


class DiningRoomWindow(tk.Toplevel):
    """Come la reception ma in sola lettura; intestazione fatti/aventi diritto."""

    COLUMNS = (("room", "Camera", 80), ("name", "Ospite", 220),
               ("meal", "Pasto", 130))

    def __init__(self, master):
        super().__init__(master)
        self.title("Sala Pranzo")
        self.geometry("470x320")
        self.header = ttk.Label(self, padding=8,
                                font=("TkDefaultFont", 11, "bold"))
        self.header.pack(anchor="w")
        self.tree = ttk.Treeview(self, show="headings",
                                 columns=[c[0] for c in self.COLUMNS])
        for key, heading, width in self.COLUMNS:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._sig = None
        self._refresh()

    def _data(self):
        now = clock.now()
        meal = guest_state.current_meal(now)
        if meal is None:
            return "Nessun pasto in corso", [], None
        people = guests.checked_in_guests()
        entitled = [g for g in people
                    if meal in guest_state.BOARD_MEALS.get(g["board"], ())]
        done = sum(1 for g in entitled
                   if guest_state.has_done_meal(g["id"], g["board"], meal, now))
        eating = [g for g in entitled
                  if guest_state.is_eating(g["id"], g["board"], meal, now)]
        return f"{meal}: {done} / {len(entitled)} ospiti", eating, meal

    def _refresh(self):
        if not self.winfo_exists():
            return
        header, eating, meal = self._data()
        sig = (header, tuple(g["rg_id"] for g in eating))
        if sig != self._sig:
            self._sig = sig
            self.header.config(text=header)
            self.tree.delete(*self.tree.get_children())
            for g in eating:
                self.tree.insert("", "end", values=(
                    g["room_number"],
                    f"{g['first_name']} {g['last_name']}".strip(), meal))
        self.after(1000, self._refresh)
