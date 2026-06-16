"""Finestra dei fogli stampabili: pulizie e pasti."""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from hotel import cleaning, clock, meals

from .date_picker import choose_into
from .utils import format_date_it, parse_date_it


class ReportWindow(tk.Toplevel):
    """Mostra un foglio (pulizie, colazione, pranzo o cena) per una data."""

    def __init__(self, master, kind: str):
        super().__init__(master)
        self.kind = kind
        self.title(f"Foglio {kind}")
        self.transient(master)
        self._build()

    def _build(self):
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text="Data (gg/mm/aaaa):").pack(side="left")
        self.date_var = tk.StringVar(value=format_date_it(clock.today()))
        ttk.Entry(top, textvariable=self.date_var,
                  width=12).pack(side="left", padx=4)
        ttk.Button(top, text="Cal", width=4,
                   command=lambda: choose_into(self, self.date_var)
                   ).pack(side="left", padx=(0, 4))
        ttk.Button(top, text="Genera",
                   command=self._generate).pack(side="left")
        ttk.Button(top, text="Salva su file",
                   command=self._save).pack(side="left", padx=4)

        self.text = tk.Text(frame, width=70, height=28,
                            font=("Courier New", 10))
        self.text.pack(pady=(8, 0))
        self._generate()

    def _sheet(self) -> str | None:
        try:
            day = parse_date_it(self.date_var.get())
        except ValueError:
            messagebox.showerror("Errore", "Data non valida (gg/mm/aaaa).",
                                 parent=self)
            return None
        if self.kind == "pulizie":
            return cleaning.sheet_text(day)
        return meals.sheet_text(self.kind, day)

    def _generate(self):
        sheet = self._sheet()
        if sheet is None:
            return
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", sheet)
        self.text.configure(state="disabled")

    def _save(self):
        sheet = self._sheet()
        if sheet is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".txt",
            initialfile=f"{self.kind}_{self.date_var.get().replace('/', '-')}.txt",
            filetypes=[("File di testo", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(sheet)
