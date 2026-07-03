"""To Do: la lista dei problemi. Aperti da risolvere, risolti barrati."""

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from hotel import estate, problems, staff


class TodoWindow(tk.Toplevel):
    COLUMNS = (("desc", "Problema", 330), ("fix", "Rimedio", 150),
               ("state", "Stato", 110))

    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change or (lambda: None)
        self.title("To Do")
        self.geometry("640x420")
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(f, show="headings", height=12,
                                 columns=[c[0] for c in self.COLUMNS])
        for key, heading, width in self.COLUMNS:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, anchor="w")
        struck = tkfont.nametofont("TkDefaultFont").copy()
        struck.configure(overstrike=1)
        self.tree.tag_configure("done", font=struck, foreground="#888888")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._sync_fix())

        act = ttk.Frame(f)
        act.pack(fill="x", pady=(8, 0))
        self.fix_btn = ttk.Button(act, command=self._fix, state="disabled",
                                  text="Risolvi")
        self.fix_btn.pack(side="left")
        ttk.Label(act, text="   Operatore pulizie:").pack(side="left")
        self.op_var = tk.StringVar()
        self.op_combo = ttk.Combobox(act, textvariable=self.op_var, width=22,
                                     state="readonly")
        self.op_combo.pack(side="left", padx=4)
        self.msg = ttk.Label(f, foreground="red")
        self.msg.pack(anchor="w", pady=(6, 0))
        self._reload()
        self._auto_refresh()

    def _auto_refresh(self):
        if not self.winfo_exists():
            return
        self._reload(keep_selection=True)
        self.after(3000, self._auto_refresh)

    def _reload(self, keep_selection=False):
        selected = self.tree.selection() if keep_selection else ()
        self.tree.delete(*self.tree.get_children())
        for p in problems.todo_list():
            kind, amount = problems.PROBLEMS[p["key"]]["fix"]
            fix = (f"Ripara: € {amount:g}" if kind == "money"
                   else f"Pulizie: {amount:g}h")
            done = p["resolved_at"] is not None
            self.tree.insert("", "end", iid=str(p["id"]),
                             values=(problems.describe(p), fix,
                                     "Risolto" if done else "APERTO"),
                             tags=("done",) if done else ())
        ops = [f"{e['id']} - {e['first_name']} {e['last_name']}"
               for e in staff.all_employees()
               if e["role"] == staff.ROLE_CLEANING]
        self.op_combo["values"] = ops
        if ops and not self.op_var.get():
            self.op_var.set(ops[0])
        for iid in selected:
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
        self._sync_fix()

    def _selected(self):
        sel = self.tree.selection()
        return problems.get(int(sel[0])) if sel else None

    def _sync_fix(self):
        p = self._selected()
        if p is None or p["resolved_at"] is not None:
            self.fix_btn.config(state="disabled", text="Risolvi")
            return
        kind, amount = problems.PROBLEMS[p["key"]]["fix"]
        text = (f"Ripara — € {amount:g}" if kind == "money"
                else f"Manda le pulizie (+{amount:g}h)")
        self.fix_btn.config(state="normal", text=text)

    def _fix(self):
        p = self._selected()
        if p is None:
            return
        self.msg.config(text="")
        kind, _amount = problems.PROBLEMS[p["key"]]["fix"]
        operator_id = None
        if kind == "cleaning":
            if not self.op_var.get():
                self.msg.config(text="Serve un operatore delle pulizie.")
                return
            operator_id = int(self.op_var.get().split(" - ")[0])
        try:
            problems.resolve(p["id"], operator_id=operator_id)
        except (problems.ProblemError, estate.EstateError) as exc:
            self.msg.config(text=str(exc))
            return
        self.on_change()
        self._reload()
