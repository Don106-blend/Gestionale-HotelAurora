"""Pagina principale: griglia delle 81 camere con i codici colore di stato."""

import tkinter as tk
from datetime import timedelta
from tkinter import ttk

from hotel import clock, constants, guest_state, guests, reservations, rooms, staff

CELL_W = 108
CELL_H = 46
PAD = 8
COLS = 9  # camere per riga (27 camere = 3 righe per piano)

STRIPE_W = 10  # larghezza della striscia di check-out sul lato destro
MARK = 12      # lato dei quadrati di arrivo


class _BaseGrid(ttk.Frame):
    """Griglia delle 81 camere per piano; le sottoclassi colorano le celle."""

    def __init__(self, master):
        super().__init__(master)
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
        self._begin_refresh()
        y = PAD
        all_rooms = rooms.all_rooms()
        for floor in rooms.floors():
            self.canvas.create_text(PAD, y + 8, anchor="w",
                                    text=f"Piano {floor}",
                                    font=("TkDefaultFont", 10, "bold"))
            y += 24
            floor_rooms = [r for r in all_rooms if r["floor"] == floor]
            for i, room in enumerate(floor_rooms):
                x = PAD + (i % COLS) * (CELL_W + PAD)
                ry = y + (i // COLS) * (CELL_H + PAD)
                self._draw_room(room, x, ry)
            y += ((len(floor_rooms) + COLS - 1) // COLS) * (CELL_H + PAD) + PAD
        self.canvas.configure(scrollregion=(0, 0, 0, y))

    def _begin_refresh(self):
        pass

    def _draw_room(self, room, x, y):
        raise NotImplementedError


class OccupancyGrid(_BaseGrid):
    """Vista occupazione: grigio = libera, rosso = ospiti presenti, blu = tutti
    assenti. Un pallino per ospite: giallo sveglio, grigio addormentato,
    invisibile assente."""

    DOT_COLORS = {"Sveglio": "#ffd600", "Addormentato": "#9e9e9e"}

    def __init__(self, master, on_room_click):
        self.on_room_click = on_room_click
        super().__init__(master)

    def _begin_refresh(self):
        self._now = clock.now()

    def _draw_room(self, room, x, y):
        number = room["number"]
        res = reservations.current_for_room(number)
        descs = [guest_state.describe(g, self._now)
                 for g in guests.for_reservation(res["id"])] if res else []

        if res is None:
            fill = "#bdbdbd"                                   # libera
        elif any(d["stato"] != "Assente" for d in descs):
            fill = "#e53935"                                  # ospiti presenti
        else:
            fill = "#1a237e"                                  # tutti assenti

        tag = f"room{number}"
        self.canvas.create_rectangle(x, y, x + CELL_W, y + CELL_H,
                                     fill=fill, outline="#555555", tags=tag)
        title = str(number) + (" S" if room["is_suite"] else "")
        self.canvas.create_text(x + 6, y + 12, anchor="w", text=title,
                                font=("TkDefaultFont", 9, "bold"), tags=tag)
        self._draw_dots(descs, x, y, tag)
        if staff.cleaner_in_room(number):    # pallino rosa: pulizie in corso
            self.canvas.create_oval(x + CELL_W - 14, y + 4,
                                    x + CELL_W - 4, y + 14,
                                    fill="#f48fb1", outline="#333333", tags=tag)
        self.canvas.tag_bind(tag, "<Button-1>",
                             lambda _e, n=number: self.on_room_click(n))

    def _draw_dots(self, descs, x, y, tag):
        # un pallino per ospite (slot fissi); l'assente resta invisibile
        n = len(descs)
        cy = y + CELL_H / 2 + 6
        start = x + CELL_W / 2 - (n - 1) * 6
        for i, d in enumerate(descs):
            color = self.DOT_COLORS.get(d["stato"])
            if color is None:
                continue
            cx = start + i * 12
            self.canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4,
                                    fill=color, outline="#333333", tags=tag)


class RoomGrid(_BaseGrid):
    """Dashboard principale: stato completo (occupata/check-out/arrivi/...)."""

    def __init__(self, master, on_room_click):
        self.on_room_click = on_room_click
        super().__init__(master)

    def _begin_refresh(self):
        self._today = clock.today()
        self._tomorrow = self._today + timedelta(days=1)

    def _draw_room(self, room, x, y):
        today, tomorrow = self._today, self._tomorrow
        number = room["number"]
        res = reservations.current_for_room(number)

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
        if room["wear"] >= constants.WEAR_LIMIT:   # logora: da rinnovare
            self.canvas.create_line(x + 4, y + 6, x + 4, y + CELL_H - 6,
                                    fill="#e07b00", width=3)

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
