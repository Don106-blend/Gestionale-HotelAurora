"""Banca: prestiti con tassi annotati, rate mensili pagate con le tasse."""

import tkinter as tk
from tkinter import ttk

from hotel import bank, budget


class BankWindow(tk.Toplevel):
    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change or (lambda: None)
        self.title("Banca di Aurora")
        self.geometry("460x420")
        self._build()
        self._reload()

    def _build(self):
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Banca di Aurora",
                  font=("TkDefaultFont", 14, "bold")).pack(anchor="w")
        self.balance_lbl = ttk.Label(f, font=("TkDefaultFont", 11, "bold"))
        self.balance_lbl.pack(anchor="w", pady=(6, 0))
        self.debt_lbl = ttk.Label(f)
        self.debt_lbl.pack(anchor="w")
        ttk.Separator(f).pack(fill="x", pady=8)

        ttk.Label(f, text="Chiedi un prestito (rimborso in 12 rate mensili,"
                          " addebitate con le tasse):",
                  wraplength=400, justify="left").pack(anchor="w")
        self.loan_btns = {}
        for principal, info in bank.LOAN_TIERS.items():
            rata = round(principal * (1 + info["rate"]) / info["months"], 2)
            btn = ttk.Button(
                f, text=f"€ {principal:,} — TAN {info['rate'] * 100:g}%"
                        f"  (12 rate da € {rata:,.2f})",
                command=lambda p=principal: self._take(p))
            btn.pack(anchor="w", pady=2, fill="x")
            self.loan_btns[principal] = btn

        ttk.Separator(f).pack(fill="x", pady=8)
        ttk.Label(f, text="Prestiti aperti",
                  font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.loans_lbl = ttk.Label(f, justify="left")
        self.loans_lbl.pack(anchor="w", pady=2)
        self.msg = ttk.Label(f, foreground="red")
        self.msg.pack(anchor="w", pady=(6, 0))

    def _reload(self):
        self.balance_lbl.config(
            text=f"Saldo: € {budget.totals()['balance']:,.2f}")
        self.debt_lbl.config(
            text=f"Debito residuo: € {bank.total_debt():,.2f} — rate del"
                 f" prossimo mese: € {bank.monthly_due():,.2f}")
        open_ok = len(bank.loans()) < bank.MAX_LOANS
        for btn in self.loan_btns.values():
            btn.config(state="normal" if open_ok else "disabled")
        if bank.loans():
            self.loans_lbl.config(text="\n".join(
                f"€ {l['principal']:,} @ {l['rate'] * 100:g}% — residuo"
                f" € {l['remaining']:,.2f} (rata € {l['installment']:,.2f})"
                for l in bank.loans()))
        else:
            self.loans_lbl.config(text="Nessun prestito aperto.")

    def _take(self, principal):
        self.msg.config(text="")
        try:
            bank.take_loan(principal)
        except bank.BankError as exc:
            self.msg.config(text=str(exc))
            return
        self.on_change()
        self._reload()
