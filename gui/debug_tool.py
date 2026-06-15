"""Finestra dello strumento di debug per generare prenotazioni di prova."""

import tkinter as tk
from datetime import timedelta
from tkinter import messagebox, ttk

from hotel import budget, clock, constants, debug_seed, mail

from .utils import format_date_it, parse_date_it


class DebugToolWindow(tk.Toplevel):
    def __init__(self, master, on_done):
        super().__init__(master)
        self.on_done = on_done
        self.title("Strumento di debug - genera prenotazioni")
        self.resizable(False, False)
        self.transient(master)
        self._build()

    def _build(self):
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        self.vars = {}
        row = 0

        def add_field(label, key, default, width=12):
            nonlocal row
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w",
                                              pady=2)
            var = tk.StringVar(value=str(default))
            ttk.Entry(frame, textvariable=var, width=width).grid(
                row=row, column=1, sticky="w", pady=2)
            self.vars[key] = var
            row += 1

        # data attuale simulata (override dell'orologio di sistema)
        ttk.Label(frame, text="Data attuale (gg/mm/aaaa)").grid(
            row=row, column=0, sticky="w", pady=2)
        self.current_date_var = tk.StringVar(value=format_date_it(clock.today()))
        ttk.Entry(frame, textvariable=self.current_date_var, width=12).grid(
            row=row, column=1, sticky="w", pady=2)
        row += 1
        date_buttons = ttk.Frame(frame)
        date_buttons.grid(row=row, column=0, columnspan=2, sticky="w")
        ttk.Button(date_buttons, text="Imposta data",
                   command=self._set_date).pack(side="left", padx=(0, 4))
        ttk.Button(date_buttons, text="Reset a oggi",
                   command=self._reset_date).pack(side="left")
        row += 1

        ttk.Separator(frame).grid(row=row, column=0, columnspan=2,
                                  sticky="ew", pady=8)
        row += 1

        add_field("Numero prenotazioni", "count", 30)
        # l'intervallo parte qualche giorno nel passato cosi diversi soggiorni
        # coprono oggi e popolano subito la griglia con camere occupate
        add_field("Data inizio (gg/mm/aaaa)", "start",
                  format_date_it(clock.today() - timedelta(days=5)))
        add_field("Data fine (gg/mm/aaaa)", "end",
                  format_date_it(clock.today() + timedelta(days=14)))
        add_field("Notti minime", "min_nights", 1, width=6)
        add_field("Notti massime", "max_nights", 7, width=6)

        ttk.Separator(frame).grid(row=row, column=0, columnspan=2,
                                  sticky="ew", pady=8)
        row += 1
        ttk.Label(frame, text="Prezzo per notte per soluzione:").grid(
            row=row, column=0, columnspan=2, sticky="w")
        row += 1
        for code, board in constants.BOARDS.items():
            add_field(f"  {code} - {board.label}", f"price_{code}",
                      debug_seed.DEFAULT_BOARD_PRICES[code], width=8)

        ttk.Separator(frame).grid(row=row, column=0, columnspan=2,
                                  sticky="ew", pady=8)
        row += 1
        self.random_colors = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="Assegna colori casuali",
                        variable=self.random_colors).grid(
            row=row, column=0, columnspan=2, sticky="w")
        row += 1
        self.auto_checkin = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="Check-in automatico per i soggiorni"
                                    " attivi oggi",
                        variable=self.auto_checkin).grid(
            row=row, column=0, columnspan=2, sticky="w")
        row += 1

        ttk.Separator(frame).grid(row=row, column=0, columnspan=2,
                                  sticky="ew", pady=8)
        row += 1
        ttk.Label(frame, text="Aggiungi movimento al budget:").grid(
            row=row, column=0, columnspan=2, sticky="w")
        row += 1
        ttk.Label(frame, text="Tipo").grid(row=row, column=0, sticky="w", pady=2)
        self.budget_kind = ttk.Combobox(frame, width=10, state="readonly",
                                        values=("Introito", "Perdita"))
        self.budget_kind.set("Introito")
        self.budget_kind.grid(row=row, column=1, sticky="w", pady=2)
        row += 1
        add_field("Categoria", "b_category", "Bolletta", width=16)
        add_field("Importo", "b_amount", "0", width=10)
        add_field("Nota", "b_note", "", width=22)
        ttk.Button(frame, text="Aggiungi a budget",
                   command=self._add_budget).grid(
            row=row, column=0, columnspan=2, pady=(2, 0))
        row += 1

        ttk.Separator(frame).grid(row=row, column=0, columnspan=2,
                                  sticky="ew", pady=8)
        row += 1
        ttk.Label(frame, text="Gameplay - Email:").grid(
            row=row, column=0, columnspan=2, sticky="w")
        row += 1
        self.mail_enabled = tk.BooleanVar(value=mail.config.enabled)
        ttk.Checkbutton(frame, text="Attiva arrivo email",
                        variable=self.mail_enabled).grid(
            row=row, column=0, columnspan=2, sticky="w")
        row += 1
        self.mail_auto = tk.BooleanVar(value=mail.config.auto_insert)
        ttk.Checkbutton(frame, text="Inserimento automatico",
                        variable=self.mail_auto).grid(
            row=row, column=0, columnspan=2, sticky="w")
        row += 1
        add_field("Intervallo (secondi)", "mail_interval",
                  mail.config.interval_seconds, width=8)
        add_field("Probabilita (0-1)", "mail_prob",
                  mail.config.probability, width=8)
        mail_buttons = ttk.Frame(frame)
        mail_buttons.grid(row=row, column=0, columnspan=2, sticky="w")
        ttk.Button(mail_buttons, text="Applica",
                   command=self._apply_mail).pack(side="left", padx=(0, 4))
        ttk.Button(mail_buttons, text="Crea email ora",
                   command=self.master.spawn_mail).pack(side="left")
        row += 1

        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(buttons, text="Genera",
                   command=self._generate).pack(side="left", padx=4)
        ttk.Button(buttons, text="Svuota database",
                   command=self._clear).pack(side="left", padx=4)
        ttk.Button(buttons, text="Chiudi",
                   command=self.destroy).pack(side="left", padx=4)

    def _read_config(self) -> debug_seed.SeedConfig | None:
        """Legge e valida i campi; mostra un errore e ritorna None se invalidi."""
        try:
            count = int(self.vars["count"].get())
            start = parse_date_it(self.vars["start"].get())
            end = parse_date_it(self.vars["end"].get())
            min_nights = int(self.vars["min_nights"].get())
            max_nights = int(self.vars["max_nights"].get())
            prices = {code: float(self.vars[f"price_{code}"].get()
                                  .replace(",", "."))
                      for code in constants.BOARDS}
        except ValueError:
            messagebox.showerror("Errore", "Controllare i valori inseriti"
                                           " (numeri e date gg/mm/aaaa).",
                                 parent=self)
            return None

        if count < 1:
            messagebox.showerror("Errore", "Il numero di prenotazioni"
                                           " deve essere almeno 1.", parent=self)
            return None
        if end < start:
            messagebox.showerror("Errore", "La data fine deve essere"
                                           " successiva alla data inizio.",
                                 parent=self)
            return None
        if min_nights < 1 or max_nights < min_nights:
            messagebox.showerror("Errore", "Intervallo di notti non valido.",
                                 parent=self)
            return None

        return debug_seed.SeedConfig(
            count=count, start=start, end=end, min_nights=min_nights,
            max_nights=max_nights, board_prices=prices,
            random_colors=self.random_colors.get(),
            auto_checkin=self.auto_checkin.get())

    def _refresh_date_defaults(self):
        """Riposiziona l'intervallo di generazione attorno alla data attuale."""
        today = clock.today()
        self.current_date_var.set(format_date_it(today))
        self.vars["start"].set(format_date_it(today - timedelta(days=5)))
        self.vars["end"].set(format_date_it(today + timedelta(days=14)))

    def _set_date(self):
        try:
            day = parse_date_it(self.current_date_var.get())
        except ValueError:
            messagebox.showerror("Errore", "Data non valida (gg/mm/aaaa).",
                                 parent=self)
            return
        clock.set_today(day)
        self._refresh_date_defaults()
        self.on_done()
        messagebox.showinfo("Debug", f"Data attuale impostata al"
                                     f" {format_date_it(day)}.", parent=self)

    def _reset_date(self):
        clock.set_today(None)
        self._refresh_date_defaults()
        self.on_done()
        messagebox.showinfo("Debug", "Data attuale ripristinata a oggi.",
                            parent=self)

    def _generate(self):
        cfg = self._read_config()
        if cfg is None:
            return
        result = debug_seed.seed_reservations(cfg)
        self.on_done()
        msg = (f"Create {result.created} prenotazioni"
               f" ({result.checked_in} in check-in).")
        if result.failed:
            msg += (f"\n{result.failed} non posizionate:"
                    f" nessuna camera libera nel periodo.")
        messagebox.showinfo("Debug", msg, parent=self)

    def _apply_mail(self):
        try:
            interval = int(self.vars["mail_interval"].get())
            prob = float(self.vars["mail_prob"].get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Errore", "Intervallo/probabilita non validi.",
                                 parent=self)
            return
        mail.config.enabled = self.mail_enabled.get()
        mail.config.auto_insert = self.mail_auto.get()
        mail.config.interval_seconds = max(interval, 1)
        mail.config.probability = min(max(prob, 0.0), 1.0)
        messagebox.showinfo("Debug", "Impostazioni email applicate.",
                            parent=self)

    def _add_budget(self):
        try:
            amount = float(self.vars["b_amount"].get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Errore", "Importo non valido.", parent=self)
            return
        category = self.vars["b_category"].get().strip()
        if not category:
            messagebox.showerror("Errore", "Inserire una categoria.",
                                 parent=self)
            return
        kind = (budget.INCOME if self.budget_kind.get() == "Introito"
                else budget.LOSS)
        budget.record(kind, category, amount, self.vars["b_note"].get().strip())
        self.on_done()
        messagebox.showinfo("Debug", "Movimento aggiunto al budget.",
                            parent=self)

    def _clear(self):
        if not messagebox.askyesno(
                "Svuota database",
                "Eliminare tutte le prenotazioni e gli ospiti e azzerare"
                " lo stato delle camere?", parent=self):
            return
        debug_seed.clear_all()
        self.on_done()
        messagebox.showinfo("Debug", "Database svuotato.", parent=self)
