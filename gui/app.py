"""Finestra principale di HotelAurora."""

import tkinter as tk
from tkinter import ttk

from .booking_form import BookingForm
from .debug_tool import DebugToolWindow
from .reports import ReportWindow
from .room_dialog import RoomDialog
from .room_grid import RoomGrid
from .timeline import Timeline


class HotelApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HotelAurora")
        self.geometry("1120x760")
        self._build()

    def _build(self):
        toolbar = ttk.Frame(self, padding=6)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Nuova prenotazione",
                   command=self._new_booking).pack(side="left", padx=2)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y",
                                                       padx=6)
        for kind in ("pulizie", "colazione", "pranzo", "cena"):
            ttk.Button(toolbar, text=f"Foglio {kind}",
                       command=lambda k=kind: ReportWindow(self, k)
                       ).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Aggiorna",
                   command=self.refresh).pack(side="right", padx=2)
        ttk.Button(toolbar, text="Debug",
                   command=self._open_debug).pack(side="right", padx=2)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        self.grid_page = RoomGrid(notebook, on_room_click=self._open_room)
        self.timeline_page = Timeline(notebook)
        notebook.add(self.grid_page, text="Camere")
        notebook.add(self.timeline_page, text="Timeline")

        legend = ttk.Label(self, padding=4, justify="left", text=(
            "Legenda:  bianco = libera  |  verde/colore custom = occupata  |"
            "  striscia gialla a destra = check-out oggi  |"
            "  quadrato fucsia (alto dx) = arrivo oggi  |"
            "  quadrato blu (basso dx) = arrivo domani\n"
            "linea grigia = sporca  |  linea rossa = bloccata  |  S = suite"))
        legend.pack(fill="x")

    def refresh(self):
        self.grid_page.refresh()
        self.timeline_page.refresh()

    def _new_booking(self):
        BookingForm(self, on_done=self.refresh)

    def _open_room(self, room_number: int):
        RoomDialog(self, room_number, on_change=self.refresh)

    def _open_debug(self):
        DebugToolWindow(self, on_done=self.refresh)
