"""Scheda camera: stato, prenotazioni e azioni contestuali."""

import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from hotel import clock, reservations, rooms


class RoomDialog(tk.Toplevel):
    def __init__(self, master, room_number: int, on_change):
        super().__init__(master)
        self.room_number = room_number
        self.on_change = on_change
        self.title(f"Camera {room_number}")
        self.resizable(False, False)
        self.transient(master)
        self._build()

    def show(self, room_number: int):
        """Riusa la stessa finestra puntandola a un'altra camera."""
        self.room_number = room_number
        self.title(f"Camera {room_number}")
        self._build()
        self.deiconify()
        self.lift()

    def _build(self):
        for child in self.winfo_children():
            child.destroy()
        today = clock.today()
        room = rooms.get_room(self.room_number)
        current = reservations.current_for_room(self.room_number)

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        kind = "Suite" if room["is_suite"] else "Camera standard"
        state = "Occupata" if current else "Libera"
        info = [f"{kind} - max {room['max_adults']} adulti"
                f" + {room['max_children']} bambino",
                f"Stato: {state}"
                f" | {'Sporca' if room['dirty'] else 'Pulita'}"
                f" | {'Bloccata' if room['blocked'] else 'Sbloccata'}"]
        for line in info:
            ttk.Label(frame, text=line).pack(anchor="w")

        ttk.Separator(frame).pack(fill="x", pady=8)
        ttk.Label(frame, text="Prenotazioni:").pack(anchor="w")
        upcoming = reservations.upcoming_for_room(self.room_number, today)
        if not upcoming:
            ttk.Label(frame, text="  nessuna").pack(anchor="w")
        for res in upcoming[:6]:
            label = (f"  {res['code']}  "
                     f"{date.fromisoformat(res['checkin_date']).strftime('%d/%m')}"
                     f" - {date.fromisoformat(res['checkout_date']).strftime('%d/%m')}"
                     f"  {reservations.guest_display_name(res)}"
                     f"  [{res['status']}]")
            ttk.Label(frame, text=label).pack(anchor="w")

        ttk.Separator(frame).pack(fill="x", pady=8)
        ttk.Label(frame, text="Check-in e check-out si gestiscono"
                              " dalla Reception.").pack(anchor="w")
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")

        clean_label = "Segna pulita" if room["dirty"] else "Segna sporca"
        ttk.Button(buttons, text=clean_label,
                   command=lambda: self._toggle_clean(room)
                   ).pack(side="left", padx=2)

        block_label = "Sblocca" if room["blocked"] else "Blocca"
        ttk.Button(buttons, text=block_label,
                   command=lambda: self._toggle_block(room, current)
                   ).pack(side="left", padx=2)

        ttk.Button(buttons, text="Chiudi",
                   command=self.destroy).pack(side="right", padx=2)

    def _refresh(self):
        self.on_change()
        self._build()

    def _toggle_clean(self, room):
        rooms.set_dirty(self.room_number, not room["dirty"])
        self._refresh()

    def _toggle_block(self, room, current):
        if not room["blocked"] and current is not None:
            messagebox.showwarning(
                "Camera occupata",
                "Non si puo bloccare una camera occupata.", parent=self)
            return
        rooms.set_blocked(self.room_number, not room["blocked"])
        self._refresh()
