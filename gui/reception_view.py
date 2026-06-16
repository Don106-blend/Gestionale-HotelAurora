"""Finestra Reception: ospiti in arrivo (check-in) e in partenza (check-out)."""

import tkinter as tk
from datetime import datetime
from tkinter import ttk

from hotel import clock, reception, reservations

from .checkout_view import CheckoutView


class ReceptionWindow(tk.Toplevel):
    """Indipendente dalla dashboard (come le mail); si aggiorna da sola."""

    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change or (lambda: None)
        self.title("Reception")
        self.geometry("520x360")
        self._body = ttk.Frame(self, padding=12)
        self._body.pack(fill="both", expand=True)
        self._sig = None
        self._refresh()

    def _late(self, entry) -> bool:
        arrived = datetime.fromisoformat(entry["arrived_at"])
        return (clock.now() - arrived).total_seconds() > 3600

    def _refresh(self):
        if not self.winfo_exists():
            return
        rows = reception.pending()
        # ridisegna solo quando cambia qualcosa (niente flicker ogni secondo)
        sig = tuple((e["id"], self._late(e)) for e in rows)
        if sig != self._sig:
            self._sig = sig
            self._render(rows)
        self.after(1000, self._refresh)

    def _render(self, rows):
        for w in self._body.winfo_children():
            w.destroy()
        if not rows:
            ttk.Label(self._body, text="Nessun ospite in attesa.").pack(anchor="w")
        for entry in rows:
            self._row(entry)

    def _row(self, entry):
        kind = "Check-out" if entry["kind"] == "checkout" else "Check-in"
        arrived = datetime.fromisoformat(entry["arrived_at"])

        fr = ttk.Frame(self._body)
        fr.pack(fill="x", pady=2)
        ttk.Label(fr, width=40, anchor="w",
                  text=f"{entry['first_name']} {entry['last_name']}"
                       f"   Camera {entry['room_number']}   ({kind})"
                  ).pack(side="left")
        time_lbl = tk.Label(fr, text=arrived.strftime("%H:%M"),
                            foreground="red" if self._late(entry) else "black")
        time_lbl.pack(side="left", padx=6)
        ttk.Button(fr, text=kind,
                   command=lambda: self._act(entry)).pack(side="right")

    def _act(self, entry):
        if entry["kind"] == "checkout":
            CheckoutView(self, reservations.get(entry["reservation_id"]),
                         on_done=lambda: (reception.remove(entry["id"]),
                                          self.on_change(), self._refresh()))
        else:
            reception.checkin_entry(entry["id"])
            self.on_change()
            self._refresh()
