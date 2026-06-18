"""Configurazione al primo avvio: nome utente e nome dell'hotel."""

import tkinter as tk
from tkinter import ttk

from hotel import estate


class SetupDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Benvenuto in HotelAurora")
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # va compilato

        f = ttk.Frame(self, padding=16)
        f.pack()
        ttk.Label(f, text="Configura il tuo hotel",
                  font=("TkDefaultFont", 12, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 12))
        ttk.Label(f, text="Il tuo nome:").grid(row=1, column=0, sticky="w")
        self.user = ttk.Entry(f, width=26)
        self.user.grid(row=1, column=1, pady=4)
        ttk.Label(f, text="Nome dell'hotel:").grid(row=2, column=0, sticky="w")
        self.hotel = ttk.Entry(f, width=26)
        self.hotel.grid(row=2, column=1, pady=4)
        ttk.Button(f, text="Inizia", command=self._ok).grid(
            row=3, column=0, columnspan=2, pady=(12, 0))
        self.user.focus_set()
        self.bind("<Return>", lambda _e: self._ok())

    def _ok(self):
        estate.complete_setup(self.user.get(), self.hotel.get())
        self.destroy()
