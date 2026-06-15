"""Finestra Budget: saldo dell'hotel e registro dei movimenti."""

import tkinter as tk
from tkinter import ttk

from hotel import budget

COLUMNS = (("day", "Data", 80), ("kind", "Tipo", 70),
           ("category", "Categoria", 120), ("amount", "Importo", 90),
           ("note", "Nota", 240))


class BudgetWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Budget")
        self.transient(master)
        self._build()

    def _build(self):
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        t = budget.totals()
        ttk.Label(frame, font=("TkDefaultFont", 10, "bold"),
                  text=(f"Saldo: {t['balance']:.2f} EUR     "
                        f"Introiti: {t['income']:.2f} EUR     "
                        f"Perdite: {t['loss']:.2f} EUR")
                  ).pack(anchor="w", pady=(0, 8))

        tree = ttk.Treeview(frame, columns=[c[0] for c in COLUMNS],
                            show="headings", height=16)
        for key, heading, width in COLUMNS:
            tree.heading(key, text=heading)
            tree.column(key, width=width, anchor="w")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        for e in budget.entries():
            kind = "Introito" if e["kind"] == budget.INCOME else "Perdita"
            tree.insert("", "end", values=(e["day"], kind, e["category"],
                                           f"{e['amount']:.2f}", e["note"]))
