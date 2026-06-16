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
        if m["inserted"]:
            ttk.Label(btns, text="Prenotazione gia inserita.").pack(side="left")
        else:
            ttk.Button(btns, text="Inserisci automaticamente",
                       command=self._insert).pack(side="left")
        ttk.Button(btns, text="Chiudi", command=self.destroy).pack(side="right")

    def _insert(self):
        try:
            room = mail.insert(self.mail_id)
        except reservations.ValidationError as exc:
            messagebox.showerror("Email", str(exc), parent=self)
            return
        self.on_change()
        messagebox.showinfo("Email", f"Prenotazione inserita in camera {room}.",
                            parent=self)
        self._build()


class MailInbox(tk.Toplevel):
    """Casella di posta: elenco delle email, doppio click per riaprirle."""

    COLUMNS = (("received_at", "Ricevuta", 90), ("sender", "Mittente", 200),
               ("subject", "Oggetto", 220), ("inserted", "Stato", 90))

    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change or (lambda: None)
        self.title("Mail")
        self.transient(master)
        self._build()

    def _build(self):
        for c in self.winfo_children():
            c.destroy()
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, show="headings", height=14,
                                 columns=[c[0] for c in self.COLUMNS])
        for key, heading, width in self.COLUMNS:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, anchor="w")
        for m in mail.all_mails():
            self.tree.insert("", "end", iid=str(m["id"]),
                             values=(m["received_at"], m["sender"], m["subject"],
                                     "Inserita" if m["inserted"] else "Da gestire"))
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self._open)
        ttk.Button(frame, text="Apri", command=self._open).pack(pady=(8, 0))

    def _open(self, _event=None):
        sel = self.tree.focus()
        if sel:
            MailView(self, int(sel),
                     on_change=lambda: (self.on_change(), self._build()))
