"""Finestre delle email: singola email (popup) e casella di posta."""

import tkinter as tk
from tkinter import messagebox, ttk

from hotel import mail, reservations


class MailView(tk.Toplevel):
    """Popup di una singola email, anche se la finestra principale e minimizzata."""

    def __init__(self, master, mail_id, on_change=None):
        super().__init__(master)
        self.mail_id = mail_id
        self.on_change = on_change or (lambda: None)
        # niente transient: deve comparire anche se il gestionale e minimizzato
        self._build()
        self._pop_to_front()

    def _pop_to_front(self):
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))
        self.focus_force()
        self.bell()

    def _build(self):
        for c in self.winfo_children():
            c.destroy()
        m = mail.get(self.mail_id)
        self.title(m["subject"])
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Da: {m['sender']}").pack(anchor="w")
        ttk.Label(frame, text=f"Ricevuta: {m['received_at']}").pack(anchor="w")

        txt = tk.Text(frame, width=64, height=15, wrap="word")
        txt.insert("1.0", m["body"])
        txt.configure(state="disabled")
        txt.pack(pady=8)

        btns = ttk.Frame(frame)
        btns.pack(fill="x")
        st = mail.status(m)
        if st == "Da gestire":     # solo le richieste aperte sono azionabili
            ttk.Button(btns, text="Inserisci automaticamente",
                       command=self._insert).pack(side="left")
            reject = ttk.Button(btns, text="Rifiuta", command=self._reject)
            reject.pack(side="left", padx=4)
            if not self._has_rooms(m):   # hotel pieno: rifiuto come scelta di default
                reject.focus_set()
        else:
            ttk.Label(btns, text=f"Stato: {st}").pack(side="left")
        ttk.Button(btns, text="Chiudi", command=self.destroy).pack(side="right")

    @staticmethod
    def _has_rooms(m) -> bool:
        from datetime import date
        return bool(reservations.available_rooms(
            date.fromisoformat(m["checkin"]), date.fromisoformat(m["checkout"])))

    def _insert(self):
        try:
            room = mail.insert(self.mail_id)
        except reservations.ValidationError as exc:
            messagebox.showerror("Email", str(exc), parent=self)
            return
        self.on_change()
        messagebox.showinfo("Email", f"Prenotazione inserita in camera {room}.",
                            parent=self)
        self.destroy()             # scelta fatta: si chiude da sola

    def _reject(self):
        mail.reject(self.mail_id)
        self.on_change()
        self.destroy()


class MailInbox(tk.Toplevel):
    """Casella di posta: ricerca, archiviazione, eliminazione delle email."""

    COLUMNS = (("received_at", "Ricevuta", 130), ("sender", "Mittente", 180),
               ("subject", "Oggetto", 220), ("status", "Stato", 90))

    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change or (lambda: None)
        self.title("Mail")
        self.transient(master)
        self.search_var = tk.StringVar()
        self.show_archived = tk.BooleanVar(value=False)
        self._build()
        self._reload()

    def _build(self):
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text="Cerca:").pack(side="left")
        ent = ttk.Entry(top, textvariable=self.search_var)
        ent.pack(side="left", fill="x", expand=True, padx=4)
        self.search_var.trace_add("write", lambda *_: self._reload())
        ttk.Checkbutton(top, text="Archiviate", variable=self.show_archived,
                        command=self._reload).pack(side="left")

        self.tree = ttk.Treeview(frame, show="headings", height=14,
                                 selectmode="extended",
                                 columns=[c[0] for c in self.COLUMNS])
        for key, heading, width in self.COLUMNS:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=(8, 0))
        self.tree.bind("<Double-1>", self._open)

        btns = ttk.Frame(frame)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Apri", command=self._open).pack(side="left")
        ttk.Button(btns, text="Archivia", command=self._archive).pack(
            side="left", padx=4)
        ttk.Button(btns, text="Elimina", command=self._delete).pack(side="left")

    def _reload(self):
        self.tree.delete(*self.tree.get_children())
        for m in mail.search_mails(self.search_var.get(),
                                   self.show_archived.get()):
            received = m["received_at"][:16].replace("T", " ")
            self.tree.insert("", "end", iid=str(m["id"]),
                             values=(received, m["sender"], m["subject"],
                                     mail.status(m)))

    def _selected(self):
        return [int(i) for i in self.tree.selection()]

    def _open(self, _event=None):
        sel = self.tree.focus() or (self.tree.selection() or [None])[0]
        if sel:
            MailView(self, int(sel),
                     on_change=lambda: (self.on_change(), self._reload()))

    def _archive(self):
        for mid in self._selected():
            mail.archive(mid)
        self._reload()

    def _delete(self):
        ids = self._selected()
        if ids and messagebox.askyesno(
                "Mail", f"Eliminare {len(ids)} mail?", parent=self):
            for mid in ids:
                mail.delete(mid)
            self._reload()
