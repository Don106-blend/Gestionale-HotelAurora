"""Finestra di debug: sezioni collassabili per le impostazioni di gioco."""

import tkinter as tk
from datetime import timedelta
from tkinter import messagebox, ttk

from hotel import budget, clock, constants, debug_seed, estate, mail

from .date_picker import choose_into
from .dining_room import DiningRoomWindow
from .guest_room import GuestMetadataWindow
from .utils import format_date_it, parse_date_it


class _Section(ttk.Frame):
    """Sezione con intestazione che la espande o collassa."""

    def __init__(self, master, title, expanded=False):
        super().__init__(master)
        self._open = expanded
        self._title = title
        self._btn = ttk.Button(self, command=self._toggle)
        self._btn.pack(fill="x")
        self.body = ttk.Frame(self, padding=(12, 4))
        self._sync()

    def _toggle(self):
        self._open = not self._open
        self._sync()
        self.winfo_toplevel().geometry("")  # rifit alla dimensione naturale

    def _sync(self):
        self._btn.config(text=("[-] " if self._open else "[+] ") + self._title)
        if self._open:
            self.body.pack(fill="x")
        else:
            self.body.pack_forget()


class DebugToolWindow(tk.Toplevel):
    def __init__(self, master, on_done):
        super().__init__(master)
        self.on_done = on_done
        self.title("Strumento di debug")
        self.resizable(False, False)
        self.transient(master)
        self._build()

    # -- helper di layout -----------------------------------------------------

    @staticmethod
    def _next(parent) -> int:
        return parent.grid_size()[1]

    def _field(self, parent, label, key, default, width=12, with_calendar=False):
        r = self._next(parent)
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", pady=2)
        var = tk.StringVar(value=str(default))
        ttk.Entry(parent, textvariable=var, width=width).grid(
            row=r, column=1, sticky="w", pady=2)
        self.vars[key] = var
        if with_calendar:
            ttk.Button(parent, text="Cal", width=4,
                       command=lambda: choose_into(self, var)).grid(
                row=r, column=2, sticky="w", padx=4)

    def _section(self, title, expanded=False) -> ttk.Frame:
        sec = _Section(self.outer, title, expanded=expanded)
        sec.pack(fill="x", pady=2)
        return sec.body

    # -- costruzione ----------------------------------------------------------

    def _build(self):
        self.vars = {}
        self.outer = ttk.Frame(self, padding=8)
        self.outer.pack(fill="both", expand=True)

        self._build_time()
        self._build_date()
        self._build_generate()
        self._build_budget()
        self._build_mail()
        self._build_guests()
        self._build_food()
        self._build_system()
        ttk.Button(self.outer, text="Chiudi",
                   command=self.destroy).pack(pady=(8, 0))

    def _build_system(self):
        b = self._section("Sistema")
        ttk.Button(b, text="Reset totale e riavvio",
                   command=self._reset_all).grid(
            row=self._next(b), column=0, columnspan=2, sticky="w")

    def _reset_all(self):
        if messagebox.askyesno(
                "Reset totale",
                "Cancellare TUTTO e tornare al primo avvio?\n"
                "Il gestionale si chiudera.", parent=self):
            estate.reset_all()
            self.master.destroy()   # chiude senza salvare lo stato

    def _build_food(self):
        b = self._section("Cibo")
        self._field(b, "Unita di cibo possedute", "food", estate.food(), width=8)
        ttk.Label(b, text=f"(capienza max: {estate.food_cap()})").grid(
            row=self._next(b), column=0, columnspan=2, sticky="w")
        ttk.Button(b, text="Applica", command=self._apply_food).grid(
            row=self._next(b), column=0, columnspan=2, sticky="w", pady=(2, 0))

    def _apply_food(self):
        try:
            n = int(self.vars["food"].get())
        except ValueError:
            messagebox.showerror("Errore", "Quantita non valida.", parent=self)
            return
        estate.set_food(n)
        self.on_done()
        messagebox.showinfo("Debug", f"Cibo impostato a {estate.food()} unita"
                                     f" (max {estate.food_cap()}).", parent=self)

    def _build_guests(self):
        b = self._section("Ospiti")
        ttk.Button(b, text="Vedi metadati ospiti",
                   command=lambda: GuestMetadataWindow(self)).grid(
            row=self._next(b), column=0, columnspan=2, sticky="w")
        ttk.Button(b, text="Sala Pranzo",
                   command=lambda: DiningRoomWindow(self)).grid(
            row=self._next(b), column=0, columnspan=2, sticky="w", pady=(2, 0))

    def _build_time(self):
        b = self._section("Tempo simulato", expanded=True)
        self.time_running = tk.BooleanVar(value=clock.running)
        ttk.Checkbutton(b, text="Avanzamento tempo attivo",
                        variable=self.time_running).grid(
            row=self._next(b), column=0, columnspan=2, sticky="w")
        self._field(b, "Scala (ore gioco / 1h reale)", "time_scale",
                    clock.scale, width=8)
        ttk.Button(b, text="Applica", command=self._apply_time).grid(
            row=self._next(b), column=0, columnspan=2, pady=(2, 0), sticky="w")

    def _build_date(self):
        b = self._section("Data attuale")
        r = self._next(b)
        ttk.Label(b, text="Data (gg/mm/aaaa)").grid(row=r, column=0,
                                                    sticky="w", pady=2)
        self.current_date_var = tk.StringVar(value=format_date_it(clock.today()))
        ttk.Entry(b, textvariable=self.current_date_var, width=12).grid(
            row=r, column=1, sticky="w", pady=2)
        ttk.Button(b, text="Cal", width=4,
                   command=lambda: choose_into(self, self.current_date_var)).grid(
            row=r, column=2, sticky="w", padx=4)
        btns = ttk.Frame(b)
        btns.grid(row=self._next(b), column=0, columnspan=2, sticky="w")
        ttk.Button(btns, text="Imposta data",
                   command=self._set_date).pack(side="left", padx=(0, 4))
        ttk.Button(btns, text="Reset a oggi",
                   command=self._reset_date).pack(side="left")

    def _build_generate(self):
        b = self._section("Genera prenotazioni", expanded=True)
        self._field(b, "Numero prenotazioni", "count", 30)
        self._field(b, "Data inizio (gg/mm/aaaa)", "start",
                    format_date_it(clock.today()), with_calendar=True)
        self._field(b, "Data fine (gg/mm/aaaa)", "end",
                    format_date_it(clock.today() + timedelta(days=14)),
                    with_calendar=True)
        self._field(b, "Notti minime", "min_nights", 1, width=6)
        self._field(b, "Notti massime", "max_nights", 7, width=6)
        ttk.Label(b, text="Prezzo per notte per soluzione:").grid(
            row=self._next(b), column=0, columnspan=2, sticky="w")
        for code, board in constants.BOARDS.items():
            self._field(b, f"  {code} - {board.label}", f"price_{code}",
                        debug_seed.DEFAULT_BOARD_PRICES[code], width=8)
        self.random_colors = tk.BooleanVar(value=True)
        ttk.Checkbutton(b, text="Assegna colori casuali",
                        variable=self.random_colors).grid(
            row=self._next(b), column=0, columnspan=2, sticky="w")
        self.auto_checkin = tk.BooleanVar(value=True)
        ttk.Checkbutton(b, text="Check-in automatico per i soggiorni attivi"
                               " oggi", variable=self.auto_checkin).grid(
            row=self._next(b), column=0, columnspan=2, sticky="w")
        btns = ttk.Frame(b)
        btns.grid(row=self._next(b), column=0, columnspan=2, pady=(6, 0),
                  sticky="w")
        ttk.Button(btns, text="Genera",
                   command=self._generate).pack(side="left", padx=(0, 4))
        ttk.Button(btns, text="Svuota database",
                   command=self._clear).pack(side="left")

    def _build_budget(self):
        b = self._section("Budget")
        r = self._next(b)
        ttk.Label(b, text="Tipo").grid(row=r, column=0, sticky="w", pady=2)
        self.budget_kind = ttk.Combobox(b, width=10, state="readonly",
                                        values=("Introito", "Perdita"))
        self.budget_kind.set("Introito")
        self.budget_kind.grid(row=r, column=1, sticky="w", pady=2)
        self._field(b, "Categoria", "b_category", "Bolletta", width=16)
        self._field(b, "Importo", "b_amount", "0", width=10)
        self._field(b, "Nota", "b_note", "", width=22)
        ttk.Button(b, text="Aggiungi a budget", command=self._add_budget).grid(
            row=self._next(b), column=0, columnspan=2, pady=(2, 0), sticky="w")

    def _build_mail(self):
        b = self._section("Gameplay - Email")
        self.mail_enabled = tk.BooleanVar(value=mail.config.enabled)
        ttk.Checkbutton(b, text="Attiva arrivo email",
                        variable=self.mail_enabled).grid(
            row=self._next(b), column=0, columnspan=2, sticky="w")
        self.mail_auto = tk.BooleanVar(value=mail.config.auto_insert)
        ttk.Checkbutton(b, text="Inserimento automatico",
                        variable=self.mail_auto).grid(
            row=self._next(b), column=0, columnspan=2, sticky="w")
        self._field(b, "Intervallo (secondi)", "mail_interval",
                    mail.config.interval_seconds, width=8)
        self._field(b, "Prob. standard (matt./pom.)", "mail_prob",
                    mail.config.probability, width=8)
        self._field(b, "  Prob. pranzo", "mail_p_pranzo",
                    mail.config.shift_probability.get("Pranzo", 0.2), width=8)
        self._field(b, "  Prob. sera", "mail_p_sera",
                    mail.config.shift_probability.get("Sera", 0.2), width=8)
        self._field(b, "  Prob. notte", "mail_p_notte",
                    mail.config.shift_probability.get("Notte", 0.05), width=8)
        self._field(b, "Prob. ospiti abituali (0-1)", "mail_returning",
                    mail.config.returning_probability, width=8)
        self._field(b, "Finestra prenotazioni (giorni)", "mail_window",
                    mail.config.window_days, width=8)
        btns = ttk.Frame(b)
        btns.grid(row=self._next(b), column=0, columnspan=2, sticky="w")
        ttk.Button(btns, text="Applica",
                   command=self._apply_mail).pack(side="left", padx=(0, 4))
        ttk.Button(btns, text="Crea email ora",
                   command=self.master.spawn_mail).pack(side="left")

    # -- azioni ---------------------------------------------------------------

    def _apply_time(self):
        try:
            scale = float(self.vars["time_scale"].get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Errore", "Scala non valida.", parent=self)
            return
        if scale <= 0:
            messagebox.showerror("Errore", "La scala deve essere positiva.",
                                 parent=self)
            return
        clock.scale = scale
        clock.running = self.time_running.get()
        messagebox.showinfo("Debug", "Impostazioni tempo applicate.",
                            parent=self)

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
        self.vars["start"].set(format_date_it(today))
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
            returning = float(self.vars["mail_returning"].get().replace(",", "."))
            window = int(self.vars["mail_window"].get())
            clamp = lambda key: min(max(float(self.vars[key].get()
                                              .replace(",", ".")), 0.0), 1.0)
            shift_probs = {"Pranzo": clamp("mail_p_pranzo"),
                           "Sera": clamp("mail_p_sera"),
                           "Notte": clamp("mail_p_notte")}
        except ValueError:
            messagebox.showerror("Errore", "Intervallo/probabilita non validi.",
                                 parent=self)
            return
        mail.config.enabled = self.mail_enabled.get()
        mail.config.auto_insert = self.mail_auto.get()
        mail.config.interval_seconds = max(interval, 1)
        mail.config.probability = min(max(prob, 0.0), 1.0)
        mail.config.returning_probability = min(max(returning, 0.0), 1.0)
        mail.config.window_days = max(window, 0)
        mail.config.shift_probability = shift_probs
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
