"""Scheda di check-in: registrazione degli ospiti della camera."""

import tkinter as tk
from tkinter import messagebox, ttk

from hotel import constants, guests, reservations

GUEST_FIELDS = (
    ("first_name", "Nome"),
    ("last_name", "Cognome"),
    ("birth_date", "Data di nascita"),
    ("birth_place", "Luogo di nascita"),
    ("document_type", "Tipo documento"),
    ("document_number", "Numero documento"),
)


class CheckinForm(tk.Toplevel):
    def __init__(self, master, res, on_done):
        super().__init__(master)
        self.res = res
        self.on_done = on_done
        self.added: list[dict] = []
        self.title(f"Check-in camera {res['room_number']}")
        self.resizable(False, False)
        self.transient(master)
        self._build()

    def _build(self):
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        res = self.res
        ttk.Label(frame, text=f"Prenotazione: {res['code']}").grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text=f"Ospiti previsti: {res['adults']} adulti,"
                              f" {res['children']} bambini").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))

        # ricerca ospiti abituali
        search_frame = ttk.Frame(frame)
        search_frame.grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(search_frame, text="Ospite abituale:").pack(side="left")
        self.search_var = tk.StringVar()
        entry = ttk.Entry(search_frame, textvariable=self.search_var, width=18)
        entry.pack(side="left", padx=4)
        entry.bind("<Return>", lambda _e: self._search())
        ttk.Button(search_frame, text="Cerca",
                   command=self._search).pack(side="left")
        self.results = ttk.Combobox(frame, width=40, state="readonly")
        self.results.grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
        self.results.bind("<<ComboboxSelected>>", lambda _e: self._fill_from_result())
        self._found: list = []

        # campi del singolo ospite
        self.vars = {}
        row = 4
        for key, label in GUEST_FIELDS:
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w",
                                              pady=2)
            if key == "document_type":
                widget = ttk.Combobox(frame, width=22,
                                      values=constants.DOCUMENT_TYPES)
                self.vars[key] = widget
            else:
                var = tk.StringVar()
                widget = ttk.Entry(frame, textvariable=var, width=24)
                self.vars[key] = var
            widget.grid(row=row, column=1, sticky="w", pady=2)
            row += 1
        # precompila con l'intestatario della prenotazione
        self.vars["first_name"].set(res["first_name"])
        self.vars["last_name"].set(res["last_name"])

        self.is_child = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Bambino",
                        variable=self.is_child).grid(row=row, column=1,
                                                     sticky="w")
        row += 1

        ttk.Button(frame, text="Aggiungi ospite",
                   command=self._add_guest).grid(row=row, column=0,
                                                 columnspan=2, pady=6)
        row += 1

        ttk.Label(frame, text="Ospiti inseriti:").grid(row=row, column=0,
                                                       sticky="w")
        row += 1
        self.listbox = tk.Listbox(frame, width=46, height=5)
        self.listbox.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1

        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(buttons, text="Rimuovi selezionato",
                   command=self._remove_selected).pack(side="left", padx=4)
        ttk.Button(buttons, text="Conferma check-in",
                   command=self._confirm).pack(side="left", padx=4)
        ttk.Button(buttons, text="Annulla",
                   command=self.destroy).pack(side="left", padx=4)

    # -- ospiti abituali ------------------------------------------------------

    def _search(self):
        term = self.search_var.get()
        self._found = guests.search(term) if term.strip() else []
        self.results["values"] = [
            f"{g['last_name']} {g['first_name']} - {g['birth_date'] or 'n.d.'}"
            f" - {g['document_type']} {g['document_number']}".strip()
            for g in self._found]
        if self._found:
            self.results.current(0)
            self._fill_from_result()
        else:
            self.results.set("Nessun risultato")

    def _fill_from_result(self):
        idx = self.results.current()
        if idx < 0 or idx >= len(self._found):
            return
        g = self._found[idx]
        for key, _label in GUEST_FIELDS:
            self.vars[key].set(g[key])

    # -- gestione lista -------------------------------------------------------

    def _current_guest(self) -> dict:
        guest = {key: self.vars[key].get().strip()
                 for key, _label in GUEST_FIELDS}
        guest["is_child"] = self.is_child.get()
        return guest

    def _add_guest(self):
        guest = self._current_guest()
        if not guest["first_name"] and not guest["last_name"]:
            messagebox.showwarning("Dati mancanti",
                                   "Inserire almeno nome o cognome.",
                                   parent=self)
            return
        self.added.append(guest)
        label = (f"{guest['last_name']} {guest['first_name']}"
                 + (" (bambino)" if guest["is_child"] else ""))
        self.listbox.insert("end", label)
        for key, _label in GUEST_FIELDS:
            self.vars[key].set("")
        self.is_child.set(False)

    def _remove_selected(self):
        selection = self.listbox.curselection()
        if selection:
            self.listbox.delete(selection[0])
            del self.added[selection[0]]

    # -- conferma -------------------------------------------------------------

    def _confirm(self):
        # se i campi sono compilati ma non ancora aggiunti, aggiungili
        pending = self._current_guest()
        if pending["first_name"] or pending["last_name"]:
            self.added.append(pending)
        try:
            reservations.do_checkin(self.res["id"], self.added)
        except reservations.ValidationError as exc:
            # rimuove l'eventuale ospite aggiunto automaticamente
            if pending in self.added:
                self.added.remove(pending)
            messagebox.showerror("Errore", str(exc), parent=self)
            return
        self.on_done()
        self.destroy()
