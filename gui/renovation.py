"""Ristrutturazioni: compra piani e camere col bilancio dell'hotel."""

import tkinter as tk
from tkinter import ttk

from hotel import amenities, budget, dining, estate


class RenovationWindow(tk.Toplevel):
    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change or (lambda: None)
        self.title("Ristrutturazioni")
        self.geometry("880x560")
        self.floor_var = tk.StringVar()
        self.suite_var = tk.BooleanVar(value=False)
        self._build()
        self._reload()

    def _build(self):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        f = ttk.Frame(outer)
        f.pack(side="left", fill="both", expand=True)
        self.right = ttk.Frame(outer)
        self.right.pack(side="left", fill="both", expand=True, padx=(20, 0))
        self.balance_lbl = ttk.Label(f, font=("TkDefaultFont", 11, "bold"))
        self.balance_lbl.pack(anchor="w")
        ttk.Separator(f).pack(fill="x", pady=8)
        self._build_amenities(self.right)

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
        ttk.Separator(f).pack(fill="x", pady=8)

        ttk.Label(f, text="Sala pasti", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w")
        self.dining_lbl = ttk.Label(f)
        self.dining_lbl.pack(anchor="w", pady=2)
        drow = ttk.Frame(f)
        drow.pack(fill="x", pady=4)
        self.table_btns = {}
        for kind, label in (("single", "Tavolo singolo (4 posti)"),
                            ("double", "Tavolo doppio (6 posti)")):
            btn = ttk.Button(
                drow, text=f"{label} — € {dining.TABLE_COSTS[kind]:,.0f}",
                command=lambda k=kind: self._do(lambda: dining.buy_table(k)))
            btn.pack(side="left", padx=(0, 4))
            self.table_btns[kind] = btn
        self.chair_btn = ttk.Button(
            drow, text=f"Sedia — € {dining.CHAIR_COST:,.0f}",
            command=lambda: self._do(dining.buy_chair))
        self.chair_btn.pack(side="left")

        ttk.Separator(f).pack(fill="x", pady=8)
        ttk.Label(f, text="Rinnovo camere logore",
                  font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        wrow = ttk.Frame(f)
        wrow.pack(fill="x", pady=4)
        ttk.Label(wrow, text="Camera:").pack(side="left")
        self.worn_var = tk.StringVar()
        self.worn_combo = ttk.Combobox(wrow, textvariable=self.worn_var,
                                       width=7, state="readonly")
        self.worn_combo.pack(side="left", padx=4)
        self.renovate_btn = ttk.Button(wrow, command=self._renovate)
        self.renovate_btn.pack(side="left", padx=4)

        self.msg = ttk.Label(f, foreground="red")
        self.msg.pack(anchor="w", pady=(6, 0))

    def _build_amenities(self, r):
        ttk.Label(r, text="Categoria e servizi",
                  font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        self.tier_lbl = ttk.Label(r, font=("TkDefaultFont", 10, "bold"))
        self.tier_lbl.pack(anchor="w", pady=(4, 0))
        self.tier_next_lbl = ttk.Label(r, justify="left", wraplength=340)
        self.tier_next_lbl.pack(anchor="w", pady=(0, 6))
        ttk.Separator(r).pack(fill="x", pady=4)

        self.amenity_btns = {}
        for key in amenities.AMENITIES:
            btn = ttk.Button(r, command=lambda k=key: self._do(
                lambda: amenities.buy(k)))
            btn.pack(anchor="w", pady=2, fill="x")
            self.amenity_btns[key] = btn

        ttk.Separator(r).pack(fill="x", pady=4)
        ttk.Label(r, text="Upgrade camere (prezzi e costi di tutto l'hotel)",
                  font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.level_btns = {}
        for level in amenities.ROOM_LEVELS:
            btn = ttk.Button(r, command=lambda lv=level: self._do(
                lambda: amenities.buy_room_upgrade(lv)))
            btn.pack(anchor="w", pady=2, fill="x")
            self.level_btns[level] = btn

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

        dc = dining.counts()
        self.dining_lbl.config(
            text=f"Tavoli: {dc['tavoli']} — Sedie/posti: {dc['sedie']}")
        for kind, btn in self.table_btns.items():
            btn.config(state="normal" if bal >= dining.TABLE_COSTS[kind]
                       else "disabled")
        self.chair_btn.config(state="normal" if bal >= dining.CHAIR_COST
                              else "disabled")

        from hotel import rooms
        worn = [str(r["number"]) for r in rooms.worn_rooms()]
        self.worn_combo["values"] = worn
        if worn and self.worn_var.get() not in worn:
            self.worn_var.set(worn[0])
        if not worn:
            self.worn_var.set("")
        self.renovate_btn.config(
            text=f"Rinnova — € {estate.RENOVATE_COST:,.0f}",
            state="normal" if (worn and bal >= estate.RENOVATE_COST)
            else "disabled")

        t = amenities.tier()
        self.tier_lbl.config(text=f"Categoria: {'★' * t}{'☆' * (5 - t)}"
                                  f"  ({t} stelle)")
        missing = amenities.missing_for_next()
        self.tier_next_lbl.config(
            text=("Categoria massima raggiunta." if not missing
                  else "Per la prossima stella: " + ", ".join(missing)))
        own = amenities.owned()
        for key, btn in self.amenity_btns.items():
            a = amenities.AMENITIES[key]
            if key in own:
                btn.config(text=f"✓ {a['label']}", state="disabled")
            else:
                btn.config(text=f"{a['label']} — € {a['cost']:,.0f}",
                           state="normal" if bal >= a["cost"] else "disabled")
        lvl = amenities.room_level()
        for level, btn in self.level_btns.items():
            info = amenities.ROOM_LEVELS[level]
            if lvl >= level:
                btn.config(text=f"✓ {info['label']} (x{info['mult']:g})",
                           state="disabled")
            else:
                cost = amenities.room_upgrade_cost(level)
                btn.config(
                    text=f"{info['label']} (x{info['mult']:g}) — € {cost:,.0f}",
                    state="normal" if (bal >= cost and lvl == level - 1)
                    else "disabled")

    def _buy_floor(self):
        self._do(estate.buy_floor)

    def _buy_room(self):
        self._do(lambda: estate.buy_room(int(self.floor_var.get()),
                                         self.suite_var.get()))

    def _upgrade_food(self):
        self._do(estate.upgrade_food_cap)

    def _renovate(self):
        self._do(lambda: estate.renovate_room(int(self.worn_var.get())))

    def _do(self, action):
        self.msg.config(text="")
        try:
            action()
        except (estate.EstateError, ValueError) as exc:
            self.msg.config(text=str(exc) or "Selezione non valida.")
            return
        self.on_change()
        self._reload()
