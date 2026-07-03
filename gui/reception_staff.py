"""Receptionist: candidature (JobHotel), turni settimanali e scelta iniziale."""

import tkinter as tk
from tkinter import messagebox, ttk

from hotel import clock, staff

WEEKDAYS = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")


class CandidatesWindow(tk.Toplevel):
    """JobHotel: le candidature della settimana, si assume col contratto."""

    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change or (lambda: None)
        self.title("JobHotel — Candidature")
        self.geometry("560x420")
        self.contract_var = tk.StringVar(value="full")
        self._build()

    def _build(self):
        for w in self.winfo_children():
            w.destroy()
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="JobHotel", font=("TkDefaultFont", 14, "bold")).pack(
            anchor="w")
        ttk.Label(f, text="Candidature della settimana (si rinnovano ogni"
                          " lunedi).").pack(anchor="w", pady=(0, 8))

        row = ttk.Frame(f)
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text="Contratto:").pack(side="left")
        for key, c in staff.CONTRACTS.items():
            extra = (" — 9/h flat, max 2 giorni" if key == "nero"
                     else f" — {c['week_hours']}h/sett.")
            ttk.Radiobutton(row, text=c["label"] + extra,
                            variable=self.contract_var, value=key).pack(
                side="left", padx=6)

        cands = staff.candidates()
        if not cands:
            ttk.Label(f, text="Nessuna candidatura disponibile questa"
                              " settimana.").pack(anchor="w", pady=8)
        for c in cands:
            fr = ttk.LabelFrame(
                f, text=f"{c['first_name']} {c['last_name']}", padding=8)
            fr.pack(fill="x", pady=3)
            label, desc = staff.BONUSES[c["bonus"]]
            ttk.Label(fr, text=f"{label}: {desc}", wraplength=380,
                      justify="left").pack(side="left")
            ttk.Button(fr, text="Assumi",
                       command=lambda k=c["key"]: self._hire(k)).pack(
                side="right")

    def _hire(self, key):
        try:
            staff.hire_candidate(key, self.contract_var.get())
        except staff.StaffError as exc:
            messagebox.showerror("JobHotel", str(exc), parent=self)
            return
        messagebox.showinfo(
            "JobHotel", "Assunto! Contratto di prova di 3 mesi.\n"
            "Ricordati di dargli dei turni dalla tabella settimanale.",
            parent=self)
        self.on_change()
        self._build()


class ScheduleWindow(tk.Toplevel):
    """Tabella settimanale dei turni: una riga per receptionist, una colonna
    per giorno. Il giorno corrente e bloccato (preavviso di un giorno)."""

    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change or (lambda: None)
        self.title("Turni receptionist")
        self.vars = {}          # (emp_id, weekday) -> StringVar
        self._build()

    def _build(self):
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        recs = staff.receptionists()
        if not recs:
            ttk.Label(f, text="Nessun receptionist assunto: passa da"
                              " JobHotel (Browser).").pack()
            return
        today_wd = clock.today().weekday()
        ttk.Label(f, text="Turni della settimana (il giorno di oggi e"
                          " bloccato: preavviso di un giorno).").grid(
            row=0, column=0, columnspan=9, sticky="w", pady=(0, 8))
        for col, day in enumerate(WEEKDAYS):
            style = ("TkDefaultFont", 9, "bold")
            ttk.Label(f, text=day + (" (oggi)" if col == today_wd else ""),
                      font=style).grid(row=1, column=col + 1, padx=2)
        sched = staff.schedule()
        for r, e in enumerate(recs, start=2):
            limit = staff.week_limit(e)
            ttk.Label(f, anchor="w", text=(
                f"{e['first_name']} {e['last_name']}"
                f" ({staff.CONTRACTS[e['contract']]['label']},"
                f" max {limit}h)")).grid(row=r, column=0, sticky="w", padx=4)
            week = sched.get(str(e["id"]), {})
            options = ("-",) + staff.allowed_shifts(e["contract"])
            for wd in range(7):
                var = tk.StringVar(value=week.get(str(wd)) or "-")
                self.vars[(e["id"], wd)] = var
                combo = ttk.Combobox(
                    f, textvariable=var, values=options, width=6,
                    state="disabled" if wd == today_wd else "readonly")
                combo.grid(row=r, column=wd + 1, padx=1, pady=2)
        ttk.Button(f, text="Applica", command=self._apply).grid(
            row=len(recs) + 2, column=0, columnspan=8, pady=(10, 0))
        self.msg = ttk.Label(f, foreground="red")
        self.msg.grid(row=len(recs) + 3, column=0, columnspan=8, sticky="w")

    def _apply(self):
        self.msg.config(text="")
        today_wd = clock.today().weekday()
        for (emp_id, wd), var in self.vars.items():
            if wd == today_wd:
                continue
            shift = None if var.get() == "-" else var.get()
            current = staff.schedule().get(str(emp_id), {}).get(str(wd))
            if shift == current:
                continue
            try:
                staff.set_shift(emp_id, wd, shift)
            except staff.StaffError as exc:
                e = staff.get(emp_id)
                self.msg.config(text=f"{e['first_name']} {e['last_name']},"
                                     f" {WEEKDAYS[wd]}: {exc}")
                return
        self.on_change()
        messagebox.showinfo("Turni", "Turni salvati.", parent=self)


class FirstReceptionistDialog(tk.Toplevel):
    """Primo avvio: si sceglie uno tra quattro receptionist casuali."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Il tuo primo receptionist")
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)   # scelta obbligata
        self.choice = tk.StringVar()
        f = ttk.Frame(self, padding=16)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Scegli il tuo receptionist",
                  font=("TkDefaultFont", 13, "bold")).pack(anchor="w")
        ttk.Label(f, text="Uno solo: gli altri troveranno lavoro altrove."
                  ).pack(anchor="w", pady=(0, 10))
        self._cands = staff.first_candidates()
        for i, c in enumerate(self._cands):
            label, desc = staff.BONUSES[c["bonus"]]
            ttk.Radiobutton(
                f, variable=self.choice, value=str(i),
                text=f"{c['first_name']} {c['last_name']} — {label}: {desc}"
            ).pack(anchor="w", pady=3)
        self.choice.set("0")
        ttk.Button(f, text="Assumi (full-time)", command=self._ok).pack(
            pady=(12, 0))

    def _ok(self):
        c = self._cands[int(self.choice.get())]
        staff.hire_receptionist(c["first_name"], c["last_name"], c["bonus"],
                                "full")
        from hotel.database import kv_set
        kv_set("rec_chosen", True)
        self.destroy()
