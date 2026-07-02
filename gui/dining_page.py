"""Tab 'Sala pasti': tavoli con sedie e ospiti seduti, stile Occupazione.

Ogni tavolo sta in una cella della griglia; le sedie gli stanno attorno e si
riempiono (gialle) con gli ospiti del gruppo seduto. Il tasto Layout apre un
editor drag&drop per spostare i tavoli.
"""

import tkinter as tk
from tkinter import ttk

from hotel import clock, dining

CELL_W, CELL_H, PAD = 150, 105, 14
TABLE_H = 44
TABLE_W = {"single": 64, "double": 108}
CHAIR_R = 8


def _chair_slots(cx, cy, w, n):
    """Posizioni delle sedie: meta sopra e meta sotto il tavolo."""
    top = (n + 1) // 2
    pts = []
    for count, sy in ((top, cy - TABLE_H / 2 - 12),
                      (n - top, cy + TABLE_H / 2 + 12)):
        for i in range(count):
            pts.append((cx - w / 2 + (i + 0.5) * (w / max(count, 1)), sy))
    return pts


def _draw_table(canvas, t, occupied=0, room=None, tag=None):
    """Disegna tavolo + sedie nella sua cella; ritorna il tag usato."""
    tag = tag or f"t{t['id']}"
    w = TABLE_W[t["kind"]]
    cx = PAD + t["col"] * CELL_W + CELL_W / 2
    cy = PAD + t["row"] * CELL_H + CELL_H / 2
    canvas.create_rectangle(cx - w / 2, cy - TABLE_H / 2,
                            cx + w / 2, cy + TABLE_H / 2,
                            fill="white", outline="#333333", width=2, tags=tag)
    if room is not None:
        canvas.create_text(cx, cy, text=str(room),
                           font=("TkDefaultFont", 9, "bold"), tags=tag)
    for i, (sx, sy) in enumerate(_chair_slots(cx, cy, w, t["chairs"])):
        fill = "#ffd600" if i < occupied else "#f0f0f0"
        canvas.create_oval(sx - CHAIR_R, sy - CHAIR_R, sx + CHAIR_R,
                           sy + CHAIR_R, fill=fill, outline="#333333",
                           tags=tag)
    return tag


class DiningPage(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        top = ttk.Frame(self, padding=(6, 4))
        top.pack(fill="x")
        self.header = ttk.Label(top, font=("TkDefaultFont", 10, "bold"))
        self.header.pack(side="left")
        ttk.Button(top, text="Layout", command=self._layout).pack(side="right")
        self.canvas = tk.Canvas(self, background="#f0f0f0",
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.refresh()

    def refresh(self):
        meal, placements, waiting = dining.seating(clock.now())
        if meal is None:
            self.header.config(text="Nessun pasto in corso")
        else:
            seated = sum(len(m) for _r, m in placements.values())
            text = f"{meal} — a tavola: {seated}"
            if waiting:
                rooms_w = ", ".join(str(m[0]["room_number"])
                                    for _r, m in waiting)
                text += f"  |  in attesa (senza tavolo): camere {rooms_w}"
            self.header.config(text=text)
        self.canvas.delete("all")
        for t in dining.tables():
            placed = placements.get(t["id"])
            _draw_table(self.canvas, t,
                        occupied=len(placed[1]) if placed else 0,
                        room=placed[1][0]["room_number"] if placed else None)

    def _layout(self):
        DiningLayoutEditor(self, on_change=self.refresh)


class DiningLayoutEditor(tk.Toplevel):
    """Drag&drop dei tavoli sulla griglia della sala (come la timeline)."""

    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change or (lambda: None)
        self.title("Layout sala pasti")
        self._drag = None       # (table_id, dx, dy)
        w = PAD * 2 + dining.GRID_COLS * CELL_W
        h = PAD * 2 + dining.GRID_ROWS * CELL_H
        self.canvas = tk.Canvas(self, width=w, height=h, background="#fafafa",
                                highlightthickness=0)
        self.canvas.pack(padx=8, pady=8)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        ttk.Label(self, text="Trascina un tavolo su una cella libera."
                  ).pack(pady=(0, 8))
        self._redraw()

    def _redraw(self):
        self.canvas.delete("all")
        for c in range(dining.GRID_COLS + 1):        # griglia leggera
            x = PAD + c * CELL_W
            self.canvas.create_line(x, PAD, x,
                                    PAD + dining.GRID_ROWS * CELL_H,
                                    fill="#dddddd")
        for r in range(dining.GRID_ROWS + 1):
            y = PAD + r * CELL_H
            self.canvas.create_line(PAD, y,
                                    PAD + dining.GRID_COLS * CELL_W, y,
                                    fill="#dddddd")
        for t in dining.tables():
            tag = _draw_table(self.canvas, t)
            self.canvas.tag_bind(
                tag, "<Button-1>",
                lambda e, tid=t["id"]: self._start_drag(tid, e))

    def _start_drag(self, table_id, event):
        self._drag = (table_id, event.x, event.y)

    def _on_motion(self, event):
        if self._drag is None:
            return
        tid, px, py = self._drag
        self.canvas.move(f"t{tid}", event.x - px, event.y - py)
        self._drag = (tid, event.x, event.y)

    def _on_release(self, event):
        if self._drag is None:
            return
        tid = self._drag[0]
        self._drag = None
        col = int((event.x - PAD) // CELL_W)
        row = int((event.y - PAD) // CELL_H)
        try:
            dining.move_table(tid, col, row)
        except dining.DiningError:
            pass                      # cella occupata/fuori sala: annulla
        self._redraw()
        self.on_change()
