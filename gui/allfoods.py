"""AllFoods!: negozio per rifornire la dispensa di cibo (1 unita = 1 pasto)."""

import tkinter as tk
from tkinter import ttk

from hotel import budget, estate


class AllFoodsWindow(tk.Toplevel):
    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change or (lambda: None)
        self.title("AllFoods!")
        self.geometry("360x300")
        self.qty_var = tk.StringVar(value="10")
        self.qty_var.trace_add("write", lambda *_: self._reload())
        self._build()
        self._reload()

    def _build(self):
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="AllFoods!", font=("TkDefaultFont", 14, "bold")).pack(
            anchor="w")
        self.food_lbl = ttk.Label(f, font=("TkDefaultFont", 11, "bold"))
        self.food_lbl.pack(anchor="w", pady=(8, 0))
        self.balance_lbl = ttk.Label(f)
        self.balance_lbl.pack(anchor="w")
        ttk.Separator(f).pack(fill="x", pady=8)

        ttk.Label(f, text=f"Acquista unita (€ {estate.FOOD_UNIT_COST:,.0f}"
                          " l'una)").pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Unita:").pack(side="left")
        ttk.Entry(row, textvariable=self.qty_var, width=8).pack(side="left",
                                                                padx=4)
        self.buy_btn = ttk.Button(f, command=self._buy)
        self.buy_btn.pack(anchor="w", pady=4)
        self.msg = ttk.Label(f, foreground="red")
        self.msg.pack(anchor="w", pady=(6, 0))

    def _qty(self) -> int:
        try:
            return int(self.qty_var.get())
        except ValueError:
            return 0

    def _reload(self):
        self.food_lbl.config(text=f"Dispensa: {estate.food()} / {estate.food_cap()}")
        self.balance_lbl.config(text=f"Saldo: € {budget.totals()['balance']:,.2f}")
        units = self._qty()
        self.buy_btn.config(
            text=f"Compra — € {estate.FOOD_UNIT_COST * max(units, 0):,.2f}",
            state="normal" if units > 0 else "disabled")

    def _buy(self):
        self.msg.config(text="")
        try:
            estate.buy_food(self._qty())
        except estate.EstateError as exc:
            self.msg.config(text=str(exc))
            return
        self.on_change()
        self._reload()
