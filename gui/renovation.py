"""Ristrutturazioni: compra piani e camere col bilancio dell'hotel."""

import tkinter as tk
from tkinter import ttk

from hotel import budget, estate


class RenovationWindow(tk.Toplevel):
    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change or (lambda: None)
        self.title("Ristrutturazioni")
        self.geometry("440x440")
        self.floor_var = tk.StringVar()
        self.suite_var = tk.BooleanVar(value=False)
        self._build()
        self._reload()

    def _build(self):
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        self.balance_lbl = ttk.Label(f, font=("TkDefaultFont", 11, "bold"))
        self.balance_lbl.pack(anchor="w")
        ttk.Separator(f).pack(fill="x", pady=8)

        ttk.Label(f, text="Piani", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w")
        self.floors_lbl = ttk.Label(f, justify="left")
        self.floors_lbl.pack(anchor="w", pady=2)
        self.floor_btn = ttk.Button(f, command=self._buy_floor)
        self.floor_btn.pack(anchor="w", pady=4)
        ttk.Separator(f).pack(fill="x", pady=8)

        ttk.Label(f, text="Acquista camera",
                  font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Piano:").pack(side="left")
        self.floor_combo = ttk.Combobox(row, textvariable=self.floor_var,
                                        width=5, state="readonly")
        self.floor_combo.pack(side="left", padx=4)
        ttk.Radiobutton(row, text="Normale", variable=self.suite_var,
                        value=False, command=self._reload).pack(side="left", padx=6)
        ttk.Radiobutton(row, text="Suite", variable=self.suite_var,
                        value=True, command=self._reload).pack(side="left")
        self.room_btn = ttk.Button(f, command=self._buy_room)
        self.room_btn.pack(anchor="w", pady=4)
        ttk.Separator(f).pack(fill="x", pady=8)

        ttk.Label(f, text="Dispensa", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w")
        self.food_lbl = ttk.Label(f)
        self.food_lbl.pack(anchor="w", pady=2)
        self.foodcap_btn = ttk.Button(f, command=self._upgrade_food)
        self.foodcap_btn.pack(anchor="w", pady=4)

        self.msg = ttk.Label(f, foreground="red")
        self.msg.pack(anchor="w", pady=(6, 0))

    def _reload(self):
        bal = budget.totals()["balance"]
        self.balance_lbl.config(text=f"Saldo: € {bal:,.2f}")
        floors = estate.owned_floors()
        self.floors_lbl.config(text="\n".join(
            f"Piano {fl}: {estate.floor_room_count(fl)}/{estate.MAX_ROOMS_PER_FLOOR}"
            for fl in floors))
        self.floor_btn.config(
            text=f"Compra piano {estate.next_floor_number()} —"
                 f" € {estate.FLOOR_COST:,.0f}",
            state="normal" if bal >= estate.FLOOR_COST else "disabled")

        free = [fl for fl in floors
                if estate.floor_room_count(fl) < estate.MAX_ROOMS_PER_FLOOR]
        self.floor_combo["values"] = [str(fl) for fl in free]
        if free and self.floor_var.get() not in {str(fl) for fl in free}:
            self.floor_var.set(str(free[0]))
        cost = estate.room_cost(self.suite_var.get())
        kind = "Suite" if self.suite_var.get() else "Normale"
        self.room_btn.config(
            text=f"Compra camera ({kind}) — € {cost:,.2f}",
            state="normal" if (free and bal >= cost) else "disabled")

        self.food_lbl.config(text=f"Capienza: {estate.food_cap()} unita"
                                  f" (cibo: {estate.food()})")
        up_cost = estate.food_cap_upgrade_cost()
        self.foodcap_btn.config(
            text=f"Aumenta capienza (+{estate.FOOD_CAP_STEP}) — € {up_cost:,.2f}",
            state="normal" if bal >= up_cost else "disabled")

    def _buy_floor(self):
        self._do(estate.buy_floor)

    def _buy_room(self):
        self._do(lambda: estate.buy_room(int(self.floor_var.get()),
                                         self.suite_var.get()))

    def _upgrade_food(self):
        self._do(estate.upgrade_food_cap)

    def _do(self, action):
        self.msg.config(text="")
        try:
            action()
        except (estate.EstateError, ValueError) as exc:
            self.msg.config(text=str(exc) or "Selezione non valida.")
            return
        self.on_change()
        self._reload()
