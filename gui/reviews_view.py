"""TrustHotel: il sito delle recensioni dell'hotel (reputazione e domanda)."""

import tkinter as tk
from tkinter import ttk

from hotel import amenities, estate, mail, reviews


class ReviewsWindow(tk.Toplevel):
    COLUMNS = (("day", "Data", 90), ("guest", "Ospite", 160),
               ("stars", "Stelle", 70), ("text", "Recensione", 330))

    def __init__(self, master):
        super().__init__(master)
        self.title("TrustHotel")
        self.geometry("720x420")
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        rep = reviews.reputation()
        t = amenities.tier()
        ttk.Label(f, text=f"TrustHotel — {estate.hotel_name()}"
                          f"  {'★' * t} ({t} stelle)",
                  font=("TkDefaultFont", 14, "bold")).pack(anchor="w")
        ttk.Label(f, text=f"Rating ospiti: {'★' * round(rep)}"
                          f"{'☆' * (5 - round(rep))}  {rep}/5   |"
                          f"   Domanda attuale: x{mail.demand_factor():.2f}"
                          " (stagione x rating x categoria)").pack(
            anchor="w", pady=(2, 8))
        tree = ttk.Treeview(f, show="headings",
                            columns=[c[0] for c in self.COLUMNS])
        for key, heading, width in self.COLUMNS:
            tree.heading(key, text=heading)
            tree.column(key, width=width, anchor="w")
        tree.pack(fill="both", expand=True)
        for r in reviews.all_reviews():
            tree.insert("", "end", values=(r["day"], r["guest"],
                                           "★" * r["stars"] or "0", r["text"]))
        if not reviews.all_reviews(1):
            ttk.Label(f, text="Ancora nessuna recensione.").pack(anchor="w",
                                                                 pady=4)
