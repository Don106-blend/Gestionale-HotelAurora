"""Conto e conferma del check-out."""

import tkinter as tk
from tkinter import messagebox, ttk

from hotel import billing, reservations


class CheckoutView(tk.Toplevel):
    def __init__(self, master, res, on_done):
        super().__init__(master)
        self.res = res
        self.on_done = on_done
        self.title(f"Conto camera {res['room_number']}")
        self.resizable(False, False)
        self.transient(master)
        self._build()

    def _build(self):
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        text = tk.Text(frame, width=48, height=18, font=("Courier New", 10))
        text.pack()
        guest_name = reservations.guest_display_name(self.res)
        text.insert("1.0", billing.bill_text(self.res, guest_name))
        text.configure(state="disabled")

        buttons = ttk.Frame(frame)
        buttons.pack(pady=(10, 0))
        ttk.Button(buttons, text="Conferma check-out",
                   command=self._confirm).pack(side="left", padx=4)
        ttk.Button(buttons, text="Chiudi",
                   command=self.destroy).pack(side="left", padx=4)

    def _confirm(self):
        if not messagebox.askyesno(
                "Check-out",
                f"Confermare il check-out della camera"
                f" {self.res['room_number']}?", parent=self):
            return
        try:
            reservations.do_checkout(self.res["id"])
        except reservations.ValidationError as exc:
            messagebox.showerror("Errore", str(exc), parent=self)
            return
        self.on_done()
        self.destroy()
