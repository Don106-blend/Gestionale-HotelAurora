"""Pagina timeline: barre delle prenotazioni per camera nel tempo."""

import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk

from hotel import constants, reservations, rooms

DAYS_BEFORE = 3
DAYS_AFTER = 27
LABEL_W = 56
DAY_W = 30
ROW_H = 20
HEADER_H = 28

STATUS_COLORS = {
    "booked": constants.COLOR_BOOKED_BAR,
    "checked_in": constants.COLOR_OCCUPIED,
    "checked_out": "#cccccc",
}


class Timeline(ttk.Frame):
    """Canvas scrollabile: una riga per camera, una colonna per giorno."""

    def __init__(self, master):
        super().__init__(master)
        width = LABEL_W + (DAYS_BEFORE + DAYS_AFTER + 1) * DAY_W
        self.canvas = tk.Canvas(self, width=min(width, 1100), height=640,
                                background="white", highlightthickness=0)
        vscroll = ttk.Scrollbar(self, orient="vertical",
                                command=self.canvas.yview)
        hscroll = ttk.Scrollbar(self, orient="horizontal",
                                command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vscroll.set,
                              xscrollcommand=hscroll.set)
        hscroll.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")
        self.refresh()

    def refresh(self):
        self.canvas.delete("all")
        today = date.today()
        start = today - timedelta(days=DAYS_BEFORE)
        end = today + timedelta(days=DAYS_AFTER)
        n_days = (end - start).days + 1
        all_rooms = rooms.all_rooms()
        total_h = HEADER_H + len(all_rooms) * ROW_H
        total_w = LABEL_W + n_days * DAY_W

        # intestazione date e griglia verticale
        for i in range(n_days):
            day = start + timedelta(days=i)
            x = LABEL_W + i * DAY_W
            if day == today:
                self.canvas.create_rectangle(x, 0, x + DAY_W, total_h,
                                             fill="#eef3e8", outline="")
            self.canvas.create_text(x + DAY_W / 2, HEADER_H / 2,
                                    text=day.strftime("%d/%m"),
                                    font=("TkDefaultFont", 7))
            self.canvas.create_line(x, 0, x, total_h, fill="#dddddd")

        # righe camere
        row_of = {}
        for idx, room in enumerate(all_rooms):
            y = HEADER_H + idx * ROW_H
            row_of[room["number"]] = y
            self.canvas.create_text(4, y + ROW_H / 2, anchor="w",
                                    text=str(room["number"]),
                                    font=("TkDefaultFont", 8))
            self.canvas.create_line(0, y, total_w, y, fill="#eeeeee")

        # barre prenotazioni
        for res in reservations.in_range(start, end):
            y = row_of.get(res["room_number"])
            if y is None:
                continue
            checkin = date.fromisoformat(res["checkin_date"])
            checkout = date.fromisoformat(res["checkout_date"])
            x1 = LABEL_W + max((checkin - start).days, 0) * DAY_W + 2
            x2 = LABEL_W + min((checkout - start).days, n_days) * DAY_W - 2
            color = (res["color"] or
                     STATUS_COLORS.get(res["status"], "#cccccc"))
            self.canvas.create_rectangle(x1, y + 3, x2, y + ROW_H - 3,
                                         fill=color, outline="#666666")
            name = reservations.guest_display_name(res)
            self.canvas.create_text(x1 + 4, y + ROW_H / 2, anchor="w",
                                    text=name[:14],
                                    font=("TkDefaultFont", 7))

        self.canvas.configure(scrollregion=(0, 0, total_w, total_h))
