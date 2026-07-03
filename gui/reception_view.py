"""Finestra Reception: ospiti in arrivo (check-in) e in partenza (check-out)."""

import tkinter as tk
from datetime import datetime
from tkinter import ttk

from hotel import clock, reception, reservations, staff

from .checkout_view import CheckoutView


class ReceptionWindow(tk.Toplevel):
    """Indipendente dalla dashboard (come le mail); si aggiorna da sola."""

    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change or (lambda: None)
        self.title("Reception")
        self.geometry("520x380")
        self.desk_lbl = ttk.Label(self, padding=(12, 8, 12, 0),
                                  font=("TkDefaultFont", 9, "italic"))
        self.desk_lbl.pack(anchor="w")
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
        rec = staff.receptionist_on_duty(clock.now())
        self.desk_lbl.config(text=(
            "Al banco: nessun receptionist" if rec is None else
            f"Al banco: {rec['first_name']} {rec['last_name']}"
            f" ({staff.BONUSES[rec['bonus']][0]})"))
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

    LABELS = {"checkout": "Check-out", "checkin": "Check-in",
              "food": "Reclamo cibo", "service": "Reclamo servizio",
              "table": "Reclamo tavoli", "problem": "Problema"}
    BUTTONS = {"checkout": "Check-out", "checkin": "Check-in",
               "food": "Parla", "service": "Parla", "table": "Parla",
               "problem": "Parla"}

    def _row(self, entry):
        kind = self.LABELS.get(entry["kind"], "Check-in")
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
        ttk.Button(fr, text=self.BUTTONS.get(entry["kind"], "Check-in"),
                   command=lambda: self._act(entry)).pack(side="right")

    def _act(self, entry):
        if entry["kind"] == "checkout":
            CheckoutView(self, reservations.get(entry["reservation_id"]),
                         on_done=lambda: (reception.remove(entry["id"]),
                                          self.on_change(), self._refresh()))
        elif entry["kind"] in ("food", "service", "table", "problem"):
            FoodComplaintView(self, entry,
                              on_done=lambda: (reception.remove(entry["id"]),
                                               self.on_change(), self._refresh()))
        else:
            reception.checkin_entry(entry["id"])
            self.on_change()
            self._refresh()


class FoodComplaintView(tk.Toplevel):
    """L'ospite rimasto a bocca asciutta si lamenta: una serie di messaggi che
    si chiudono uno alla volta col tasto 'Scusati'. Finiti, torna in camera."""

    MESSAGES = {
        "food": (
            "Scusate, ero sceso per il pasto ma non c'e niente da mangiare!",
            "Ho prenotato il trattamento coi pasti inclusi, e una vergogna.",
            "Vi prego di rifornire la cucina al piu presto.",
        ),
        "service": (
            "Sono in sala da un'ora e nessuno e venuto a servirci!",
            "Non c'e abbastanza personale, i tavoli sono abbandonati.",
            "Assumete piu camerieri, cosi non si puo mangiare.",
        ),
        "table": (
            "Siamo scesi a mangiare ma non c'e un tavolo libero per noi!",
            "Non possiamo mica mangiare in piedi.",
            "Comprate piu tavoli e sedie, la sala e minuscola.",
        ),
    }
    TITLES = {"food": "Reclamo: manca il cibo",
              "service": "Reclamo: servizio in sala",
              "table": "Reclamo: nessun tavolo libero",
              "problem": "Problema segnalato"}

    def __init__(self, master, entry, on_done):
        super().__init__(master)
        self.entry = entry
        self.on_done = on_done
        if entry["kind"] == "problem":     # testo del guaio raccontato
            self._msgs = (entry["note"] or "C'e un problema, venite a vedere!",
                          "Vi prego di sistemarlo al piu presto.")
        else:
            self._msgs = self.MESSAGES.get(entry["kind"],
                                           self.MESSAGES["food"])
        self.title(self.TITLES.get(entry["kind"], "Reclamo"))
        self.transient(master)
        self.grab_set()
        self._i = 0
        self._body = ttk.Frame(self, padding=16)
        self._body.pack(fill="both", expand=True)
        self._render()

    def _render(self):
        for w in self._body.winfo_children():
            w.destroy()
        name = f"{self.entry['first_name']} {self.entry['last_name']}".strip()
        ttk.Label(self._body, text=f"{name} (Camera {self.entry['room_number']})",
                  font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        ttk.Label(self._body, text=self._msgs[self._i], wraplength=320,
                  justify="left").pack(anchor="w", pady=(8, 12))
        ttk.Button(self._body, text="Scusati", command=self._next).pack()

    def _next(self):
        self._i += 1
        if self._i >= len(self._msgs):
            self.on_done()
            self.destroy()
        else:
            self._render()
