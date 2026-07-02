"""Tabella dipendenti: assunzioni, licenziamenti, turni e foglio ore."""

import tkinter as tk
from tkinter import messagebox, ttk

from hotel import clock, staff


class StaffWindow(tk.Toplevel):
    COLUMNS = (("name", "Dipendente", 170), ("role", "Ruolo", 90),
               ("hourly", "€/h lordi", 70), ("hired", "Assunto il", 90),
               ("month", "Ore mese", 80), ("unpaid", "Da pagare (h)", 90),
               ("stat", "Serviti / Velocita", 110))

    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change or (lambda: None)
        self.title("Dipendenti")
        self.geometry("760x480")
        self._build()
        self._reload()

    def _build(self):
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(f, show="headings", height=10,
                                 columns=[c[0] for c in self.COLUMNS])
        for key, heading, width in self.COLUMNS:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)

        btns = ttk.Frame(f)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Assumi (pulizie)",
                   command=lambda: self._hire(staff.ROLE_CLEANING)).pack(
            side="left")
        ttk.Button(btns, text="Assumi (sala)",
                   command=lambda: self._hire(staff.ROLE_DINING)).pack(
            side="left", padx=4)
        ttk.Button(btns, text="Licenzia selezionato",
                   command=self._fire).pack(side="left", padx=4)
        ttk.Button(btns, text="Foglio ore",
                   command=self._sheet).pack(side="right")

        plan = ttk.LabelFrame(f, text="Turni di domani (in servizio)",
                              padding=8)
        plan.pack(fill="x", pady=(10, 0))
        self.plan_vars = {}
        for col, role in enumerate(staff.ROLES):
            ttk.Label(plan, text=staff.ROLE_LABELS[role] + ":").grid(
                row=0, column=col * 2, sticky="w", padx=(0 if col == 0 else 16, 4))
            var = tk.StringVar()
            ttk.Spinbox(plan, from_=0, to=99, width=4,
                        textvariable=var).grid(row=0, column=col * 2 + 1)
            self.plan_vars[role] = var
        ttk.Button(plan, text="Applica da domani",
                   command=self._apply_plan).grid(row=0, column=4, padx=16)
        self.today_lbl = ttk.Label(plan)
        self.today_lbl.grid(row=1, column=0, columnspan=5, sticky="w",
                            pady=(6, 0))

        self.pay_lbl = ttk.Label(f, font=("TkDefaultFont", 9, "italic"))
        self.pay_lbl.pack(anchor="w", pady=(8, 0))

    def _reload(self):
        today = clock.today()
        self.tree.delete(*self.tree.get_children())
        for e in staff.all_employees():
            name = f"{e['first_name']} {e['last_name']}"
            if staff.is_sick(e["id"], today):
                name += "  (malato oggi)"
            stat = (f"{e['served']} serviti"
                    if e["role"] == staff.ROLE_DINING
                    else f"x{staff.speed_factor(e['id']):.2f} velocita")
            self.tree.insert("", "end", iid=str(e["id"]), values=(
                name, staff.ROLE_LABELS[e["role"]], f"{e['hourly']:g}",
                e["hired_on"], f"{staff.month_hours(e['id'], today):g}",
                f"{staff.unpaid_hours(e['id']):g}", stat))
        current = staff.roster()
        nxt = staff.roster_next()
        for role, var in self.plan_vars.items():
            var.set(str(nxt[role]))
        self.today_lbl.config(text="Oggi in servizio:  " + "  |  ".join(
            f"{staff.ROLE_LABELS[r]}: {current[r]}/{staff.headcount(r)}"
            for r in staff.ROLES))
        self.pay_lbl.config(
            text=f"Stipendi il {staff.PAYDAY} del mese — prossima stima:"
                 f" € {staff.unpaid_cost():,.2f}"
                 f" (lordo x{staff.EMPLOYER_COST_MULT:g} costo azienda)")

    def _hire(self, role):
        staff.hire(role)
        self.on_change()
        self._reload()

    def _fire(self):
        sel = self.tree.selection()
        if not sel:
            return
        emp_id = int(sel[0])
        e = staff.get(emp_id)
        if not messagebox.askyesno(
                "Licenziamento",
                f"Licenziare {e['first_name']} {e['last_name']}?\n"
                "Le ore non pagate verranno liquidate subito.", parent=self):
            return
        cost = staff.fire(emp_id)
        if cost:
            messagebox.showinfo("Licenziamento",
                                f"Liquidazione pagata: € {cost:,.2f}.",
                                parent=self)
        self.on_change()
        self._reload()

    def _apply_plan(self):
        for role, var in self.plan_vars.items():
            try:
                staff.set_roster_next(role, int(var.get()))
            except ValueError:
                messagebox.showerror("Errore", "Numero non valido.",
                                     parent=self)
                return
        self._reload()

    def _sheet(self):
        win = tk.Toplevel(self)
        win.title("Foglio ore")
        txt = tk.Text(win, width=70, height=28, wrap="none")
        txt.insert("1.0", staff.hours_sheet(clock.today()))
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True, padx=8, pady=8)
