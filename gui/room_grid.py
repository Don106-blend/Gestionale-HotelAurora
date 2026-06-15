"""Pagina principale: griglia delle 81 camere con i codici colore di stato."""

import tkinter as tk
from datetime import timedelta
from tkinter import ttk

from hotel import clock, constants, reservations, rooms

CELL_W = 108
CELL_H = 46
PAD = 8
COLS = 9  # camere per riga (27 camere = 3 righe per piano)

STRIPE_W = 10  # larghezza della striscia di check-out sul lato destro
MARK = 12      # lato dei quadrati di arrivo


class RoomGrid(ttk.Frame):
    """Canvas con un rettangolo per camera, raggruppate per piano."""

    def __init__(self, master, on_room_click):
        super().__init__(master)
        self.on_room_click = on_room_click
        width = PAD + COLS * (CELL_W + PAD)
        self.canvas = tk.Canvas(self, width=width, height=640,
                                background="#f0f0f0", highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical",
                               command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.refresh()

    def refresh(self):
        self.canvas.delete("all")
        today = clock.today()
        tomorrow = today + timedelta(days=1)
        y = PAD
        for floor in constants.FLOORS:
            self.canvas.create_text(PAD, y + 8, anchor="w",
                                    text=f"Piano {floor}",
                                    font=("TkDefaultFont", 10, "bold"))
            y += 24
            floor_rooms = [r for r in rooms.all_rooms() if r["floor"] == floor]
            for i, room in enumerate(floor_rooms):
                x = PAD + (i % COLS) * (CELL_W + PAD)
                ry = y + (i // COLS) * (CELL_H + PAD)
                self._draw_room(room, x, ry, today, tomorrow)
            y += ((len(floor_rooms) + COLS - 1) // COLS) * (CELL_H + PAD) + PAD
        self.canvas.configure(scrollregion=(0, 0, 0, y))

    def _draw_room(self, room, x, y, today, tomorrow):
        number = room["number"]
        res = reservations.current_for_room(number, today)

        fill = constants.COLOR_FREE
        label2 = ""
        checkout_today = False
        if res is not None:
            fill = res["color"] or constants.COLOR_OCCUPIED
            label2 = reservations.guest_display_name(res)
            checkout_today = res["checkout_date"] == today.isoformat()

        tag = f"room{number}"
        self.canvas.create_rectangle(x, y, x + CELL_W, y + CELL_H,
                                     fill=fill, outline="#555555", tags=tag)

        # striscia gialla sul lato destro: camera occupata in check-out oggi
        if checkout_today:
            self.canvas.create_rectangle(
                x + CELL_W - STRIPE_W, y, x + CELL_W, y + CELL_H,
                fill=constants.COLOR_CHECKOUT_DAY, outline="", tags=tag)

        title = str(number) + (" S" if room["is_suite"] else "")
        self.canvas.create_text(x + 6, y + 12, anchor="w", text=title,
                                font=("TkDefaultFont", 9, "bold"), tags=tag)
        if label2:
            self.canvas.create_text(x + 6, y + 30, anchor="w",
                                    text=label2[:16], tags=tag)
        if room["dirty"]:
            self.canvas.create_line(x + 4, y + CELL_H - 6,
                                    x + CELL_W - 4, y + CELL_H - 6,
                                    fill=constants.COLOR_DIRTY_LINE, width=3)
        if room["blocked"]:
            self.canvas.create_line(x + 4, y + 4, x + CELL_W - 4, y + 4,
                                    fill=constants.COLOR_BLOCKED_LINE, width=3)

        # marcatori di arrivo, disegnati per ultimi cosi restano in evidenza
        if reservations.arrival_on(number, today):
            self.canvas.create_rectangle(
                x + CELL_W - MARK - 2, y + 2, x + CELL_W - 2, y + 2 + MARK,
                fill=constants.COLOR_ARRIVAL_TODAY, outline="#555555", tags=tag)
        if reservations.arrival_on(number, tomorrow):
            self.canvas.create_rectangle(
                x + CELL_W - MARK - 2, y + CELL_H - 2 - MARK,
                x + CELL_W - 2, y + CELL_H - 2,
                fill=constants.COLOR_ARRIVAL_NEXT, outline="#555555", tags=tag)

        self.canvas.tag_bind(tag, "<Button-1>",
                             lambda _e, n=number: self.on_room_click(n))
