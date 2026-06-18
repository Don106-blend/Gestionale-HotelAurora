"""Finestre ospiti: tabella di camera (color-coded) e metadati (debug)."""

import tkinter as tk
from tkinter import ttk

from hotel import clock, guest_state, guests, reservations


class GuestRoomWindow(tk.Toplevel):
    """Ospiti di una camera: una riga per ospite, colore per stato (termico)."""

    COLUMNS = (("name", "Nome / Cognome", 180), ("stato", "Stato", 110),
               ("locazione", "Locazione", 180), ("emozione", "Emozione", 90),
               ("bisogno", "Bisogno", 90))

    def __init__(self, master, room_number):
        super().__init__(master)
        self.room_number = room_number
        self.title(f"Camera {room_number} - ospiti")
        self.geometry("680x300")
        self.tree = ttk.Treeview(self, show="headings",
                                 columns=[c[0] for c in self.COLUMNS])
        for key, heading, width in self.COLUMNS:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, anchor="w")
        for st, color in guest_state.COLORS.items():
            self.tree.tag_configure(st, background=color, foreground="white")
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        self._sig = None
        self._refresh()

    def show(self, room_number):
        """Riusa la stessa finestra puntandola a un'altra camera."""
        self.room_number = room_number
        self.title(f"Camera {room_number} - ospiti")
        self._sig = None
        self._redraw()
        self.deiconify()
        self.lift()

    def _rows(self):
        now = clock.now()
        res = reservations.current_for_room(self.room_number)
        if res is None:
            return []
        return [guest_state.describe(g, now)
                for g in guests.for_reservation(res["id"])]

    def _redraw(self):
        rows = self._rows()
        sig = tuple((r["name"], r["stato"], r["locazione"]) for r in rows)
        if sig != self._sig:   # ridisegna solo se cambia (niente flicker)
            self._sig = sig
            self.tree.delete(*self.tree.get_children())
            for r in rows:
                self.tree.insert("", "end", tags=(r["stato"],),
                                 values=(r["name"], r["stato"], r["locazione"],
                                         r["emozione"], r["bisogno"]))

    def _refresh(self):
        if not self.winfo_exists():
            return
        self._redraw()
        self.after(1000, self._refresh)


class GuestMetadataWindow(tk.Toplevel):
    """Debug: genoma di tutti gli ospiti (carta d'identita)."""

    COLUMNS = (("name", "Ospite", 200), ("birth", "Nascita", 110),
               ("sleep", "Ora sonno (base)", 120), ("wake", "Ore sonno", 90))

    def __init__(self, master):
        super().__init__(master)
        self.title("Metadati ospiti")
        self.geometry("560x360")
        tree = ttk.Treeview(self, show="headings",
                            columns=[c[0] for c in self.COLUMNS])
        for key, heading, width in self.COLUMNS:
            tree.heading(key, text=heading)
            tree.column(key, width=width, anchor="w")
        for g in guests.all_guests():
            meta = guest_state.metadata(g["id"])
            name = f"{g['last_name']} {g['first_name']}".strip()
            tree.insert("", "end", values=(name, g["birth_date"] or "n.d.",
                                           guest_state.sleep_base_str(g["id"]),
                                           meta["wake_hours"]))
        tree.pack(fill="both", expand=True, padx=8, pady=8)
