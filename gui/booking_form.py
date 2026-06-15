"""Form di inserimento prenotazione."""

import tkinter as tk
from datetime import timedelta
from tkinter import colorchooser, messagebox, ttk

from hotel import clock, constants, reservations

from .utils import format_date_it, parse_date_it

BOARD_CHOICES = [f"{b.code} - {b.label}" for b in constants.BOARDS.values()]


class BookingForm(tk.Toplevel):
    def __init__(self, master, on_done, room_number: int | None = None):
        super().__init__(master)
        self.on_done = on_done
        self.title("Nuova prenotazione")
        self.resizable(False, False)
        self.transient(master)
        self.color = ""
        self._build(room_number)

    def _build(self, room_number):
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        self.vars = {}

        def add_entry(label, key, row, default="", width=24):
            ttk.Label(frame, text=label).grid(row=row, column=0,
                                              sticky="w", pady=2)
            var = tk.StringVar(value=default)
            entry = ttk.Entry(frame, textvariable=var, width=width)
            entry.grid(row=row, column=1, sticky="w", pady=2)
            self.vars[key] = var
            return entry

        add_entry("Nome", "first_name", 0)
        add_entry("Cognome", "last_name", 1)
        add_entry("Telefono", "phone", 2)
        add_entry("Email", "email", 3)

        today = clock.today()
        checkin_entry = add_entry("Check-in (gg/mm/aaaa)", "checkin", 4,
                                  format_date_it(today), width=12)
        nights_entry = add_entry("Notti", "nights", 5, "1", width=6)
        checkout_entry = add_entry("Check-out (gg/mm/aaaa)", "checkout", 6,
                                   format_date_it(today + timedelta(days=1)),
                                   width=12)
        # date e notti si sincronizzano a vicenda
        checkin_entry.bind("<FocusOut>", lambda _e: self._sync_from_nights())
        nights_entry.bind("<FocusOut>", lambda _e: self._sync_from_nights())
        checkout_entry.bind("<FocusOut>", lambda _e: self._sync_from_dates())

        ttk.Label(frame, text="Adulti").grid(row=7, column=0, sticky="w")
        self.vars["adults"] = tk.StringVar(value="2")
        ttk.Spinbox(frame, from_=1, to=10, width=5,
                    textvariable=self.vars["adults"]).grid(row=7, column=1,
                                                           sticky="w")
        ttk.Label(frame, text="Bambini").grid(row=8, column=0, sticky="w")
        self.vars["children"] = tk.StringVar(value="0")
        ttk.Spinbox(frame, from_=0, to=10, width=5,
                    textvariable=self.vars["children"]).grid(row=8, column=1,
                                                             sticky="w")

        ttk.Label(frame, text="Camera").grid(row=9, column=0, sticky="w")
        self.room_combo = ttk.Combobox(frame, width=21, state="readonly")
        self.room_combo.grid(row=9, column=1, sticky="w", pady=2)
        self._refresh_rooms(preselect=room_number)

        add_entry("Prezzo per notte", "price", 10, "0", width=10)

        ttk.Label(frame, text="Soluzione").grid(row=11, column=0, sticky="w")
        self.board_combo = ttk.Combobox(frame, width=21, values=BOARD_CHOICES)
        self.board_combo.set(BOARD_CHOICES[0])
        self.board_combo.grid(row=11, column=1, sticky="w", pady=2)

        add_entry("Sconto %", "discount", 12, "", width=6)

        ttk.Label(frame, text="Colore custom").grid(row=13, column=0,
                                                    sticky="w")
        color_frame = ttk.Frame(frame)
        color_frame.grid(row=13, column=1, sticky="w", pady=2)
        self.color_preview = tk.Label(color_frame, width=3, relief="sunken",
                                      background="white")
        self.color_preview.pack(side="left", padx=(0, 4))
        ttk.Button(color_frame, text="Scegli",
                   command=self._pick_color).pack(side="left")
        ttk.Button(color_frame, text="Nessuno",
                   command=self._clear_color).pack(side="left", padx=4)

        ttk.Label(frame, text="Commenti").grid(row=14, column=0, sticky="nw")
        self.comments = tk.Text(frame, width=30, height=3)
        self.comments.grid(row=14, column=1, sticky="w", pady=2)

        buttons = ttk.Frame(frame)
        buttons.grid(row=15, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(buttons, text="Salva",
                   command=self._save).pack(side="left", padx=4)
        ttk.Button(buttons, text="Annulla",
                   command=self.destroy).pack(side="left", padx=4)

    # -- sincronizzazione date/notti e camere disponibili ------------------

    def _dates(self):
        checkin = parse_date_it(self.vars["checkin"].get())
        checkout = parse_date_it(self.vars["checkout"].get())
        return checkin, checkout

    def _sync_from_nights(self):
        """Il numero di notti imposta il check-out."""
        try:
            checkin = parse_date_it(self.vars["checkin"].get())
            nights = max(1, int(self.vars["nights"].get()))
        except ValueError:
            return
        self.vars["nights"].set(str(nights))
        self.vars["checkout"].set(
            format_date_it(checkin + timedelta(days=nights)))
        self._refresh_rooms()

    def _sync_from_dates(self):
        """La data di check-out aggiorna il numero di notti."""
        try:
            checkin, checkout = self._dates()
        except ValueError:
            return
        nights = (checkout - checkin).days
        if nights >= 1:
            self.vars["nights"].set(str(nights))
        self._refresh_rooms()

    def _refresh_rooms(self, preselect: int | None = None):
        try:
            checkin, checkout = self._dates()
        except ValueError:
            return
        free = reservations.available_rooms(checkin, checkout)
        values = [f"{r['number']}{' (suite)' if r['is_suite'] else ''}"
                  for r in free]
        current = self.room_combo.get()
        self.room_combo["values"] = values
        wanted = str(preselect) if preselect else current
        match = next((v for v in values if v.split()[0] == wanted.split()[0]),
                     None) if wanted else None
        self.room_combo.set(match or (values[0] if values else ""))

    # -- colore -------------------------------------------------------------

    def _pick_color(self):
        result = colorchooser.askcolor(parent=self)
        if result and result[1]:
            self.color = result[1]
            self.color_preview.configure(background=self.color)

    def _clear_color(self):
        self.color = ""
        self.color_preview.configure(background="white")

    # -- salvataggio ----------------------------------------------------------

    def _save(self):
        try:
            checkin, checkout = self._dates()
        except ValueError:
            messagebox.showerror("Errore", "Date non valide (gg/mm/aaaa).",
                                 parent=self)
            return
        room_text = self.room_combo.get()
        if not room_text:
            messagebox.showerror("Errore", "Selezionare una camera.",
                                 parent=self)
            return
        room_number = int(room_text.split()[0])
        board = self.board_combo.get().split()[0].strip().upper()
        try:
            adults = int(self.vars["adults"].get())
            children = int(self.vars["children"].get())
            price = float(self.vars["price"].get().replace(",", ".") or 0)
            discount_text = self.vars["discount"].get().strip()
            discount = (float(discount_text.replace(",", "."))
                        if discount_text else None)
        except ValueError:
            messagebox.showerror("Errore", "Valori numerici non validi.",
                                 parent=self)
            return

        # pax oltre la capienza: avviso ma si puo proseguire
        warning = reservations.capacity_warning(room_number, adults, children)
        if warning and not messagebox.askyesno(
                "Avviso capienza", warning + "\nProseguire comunque?",
                parent=self):
            return

        try:
            reservations.create_reservation(
                first_name=self.vars["first_name"].get(),
                last_name=self.vars["last_name"].get(),
                room_number=room_number, checkin=checkin, checkout=checkout,
                adults=adults, children=children, price_per_night=price,
                board=board, discount=discount,
                phone=self.vars["phone"].get(),
                email=self.vars["email"].get(), color=self.color,
                comments=self.comments.get("1.0", "end").strip())
        except reservations.ValidationError as exc:
            messagebox.showerror("Errore", str(exc), parent=self)
            return
        self.on_done()
        self.destroy()
