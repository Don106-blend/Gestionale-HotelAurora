"""Scheda 'Browser': hub da cui aprire i sistemi (mail, ristrutturazioni, ...)."""

import tkinter as tk
from tkinter import ttk

from hotel import mail

from .allfoods import AllFoodsWindow
from .bank_view import BankWindow
from .mail_view import MailInbox
from .reception_staff import CandidatesWindow
from .renovation import RenovationWindow
from .reviews_view import ReviewsWindow


class BrowserPage(ttk.Frame):
    """Griglia di 'app'; in futuro raccogliera anche gli altri sistemi."""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        ttk.Label(self, text="Browser", font=("TkDefaultFont", 14, "bold")).pack(
            pady=12)
        grid = ttk.Frame(self)
        grid.pack()
        apps = (
            ("Mail", lambda: MailInbox(self.app, on_change=self.app.refresh)),
            ("Ristrutturazioni",
             lambda: RenovationWindow(self.app, on_change=self.app.refresh)),
            ("AllFoods!",
             lambda: AllFoodsWindow(self.app, on_change=self.app.refresh)),
            ("TrustHotel", lambda: ReviewsWindow(self.app)),
            ("JobHotel",
             lambda: CandidatesWindow(self.app, on_change=self.app.refresh)),
            ("Banca di Aurora",
             lambda: BankWindow(self.app, on_change=self.app.refresh)),
        )
        for i, (label, cmd) in enumerate(apps):
            ttk.Button(grid, text=label, width=22, command=cmd).grid(
                row=i // 3, column=i % 3, padx=10, pady=10, ipady=24)

        booking = ttk.LabelFrame(self, text="Booking", padding=10)
        booking.pack(pady=16)
        self.block_var = tk.BooleanVar(value=mail.config.block_new_bookings)
        ttk.Checkbutton(booking, text="Blocca l'arrivo di nuove prenotazioni",
                        variable=self.block_var, command=self._toggle_block).pack(
            anchor="w")

    def _toggle_block(self):
        mail.config.block_new_bookings = self.block_var.get()

    def refresh(self):
        self.block_var.set(mail.config.block_new_bookings)
