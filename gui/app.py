"""Finestra principale di HotelAurora."""

import random
import tkinter as tk
from tkinter import ttk

from hotel import clock, mail, persistence, reception, reservations

from .booking_form import BookingForm
from .budget_view import BudgetWindow
from .debug_tool import DebugToolWindow
from .guest_room import GuestRoomWindow
from .mail_view import MailInbox, MailView
from .reception_view import ReceptionWindow
from .reports import ReportWindow
from .room_dialog import RoomDialog
from .room_grid import OccupancyGrid, RoomGrid
from .time_view import TimeWindow
from .timeline import Timeline


class HotelApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HotelAurora")
        self.geometry("1120x760")
        self.room_dialog = None       # finestra camera unica e riutilizzata
        self.reception_window = None  # finestra reception unica
        self.guest_window = None      # finestra ospiti unica
        self._alert_on = False
        persistence.load()       # ripristina lo stato di gioco salvato
        self._build()
        self._last_shown_day = clock.today()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(1000, self._mail_tick)
        self.after(1000, self._time_tick)
        self.after(500, self._alert_tick)

    def _on_close(self):
        try:
            persistence.save()
        finally:
            self.destroy()

    def _build(self):
        toolbar = ttk.Frame(self, padding=6)
        toolbar.pack(fill="x")
        # avviso reception (riserva il proprio slot a sinistra, non copre nulla)
        self.alert = tk.Label(toolbar, width=2, relief="raised", borderwidth=2,
                              cursor="hand2")
        self.alert.bind("<Button-1>", lambda _e: self._open_reception())
        self._newbtn = ttk.Button(toolbar, text="Nuova prenotazione",
                                  command=self._new_booking)
        self._newbtn.pack(side="left", padx=2)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y",
                                                       padx=6)
        for kind in ("pulizie", "colazione", "pranzo", "cena"):
            ttk.Button(toolbar, text=f"Foglio {kind}",
                       command=lambda k=kind: ReportWindow(self, k)
                       ).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Aggiorna",
                   command=self.refresh).pack(side="right", padx=2)
        ttk.Button(toolbar, text="Debug",
                   command=self._open_debug).pack(side="right", padx=2)
        ttk.Button(toolbar, text="Budget",
                   command=lambda: BudgetWindow(self)).pack(side="right", padx=2)
        ttk.Button(toolbar, text="Reception",
                   command=self._open_reception).pack(side="right", padx=2)
        ttk.Button(toolbar, text="Mail",
                   command=lambda: MailInbox(self, on_change=self.refresh)
                   ).pack(side="right", padx=2)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        self.grid_page = RoomGrid(notebook, on_room_click=self._open_room)
        self.timeline_page = Timeline(notebook)
        self.occupancy_page = OccupancyGrid(
            notebook, on_room_click=self._open_guest_room)
        notebook.add(self.grid_page, text="Camere")
        notebook.add(self.timeline_page, text="Timeline")
        notebook.add(self.occupancy_page, text="Occupazione")

        legend = ttk.Label(self, padding=4, justify="left", text=(
            "Legenda:  bianco = libera  |  verde/colore custom = occupata  |"
            "  striscia gialla a destra = check-out oggi  |"
            "  quadrato fucsia (alto dx) = arrivo oggi  |"
            "  quadrato blu (basso dx) = arrivo domani\n"
            "linea grigia = sporca  |  linea rossa = bloccata  |  S = suite"))
        legend.pack(fill="x")

        # barra del tempo simulato (clic = finestra Orario)
        bar = ttk.Frame(self, padding=4)
        bar.pack(fill="x", side="bottom")
        ttk.Label(bar, text="Tempo:").pack(side="left")
        self.clock_label = tk.Label(bar, relief="sunken", padx=8,
                                    cursor="hand2")
        self.clock_label.pack(side="left", padx=4)
        self.shift_label = tk.Label(bar, padx=10, cursor="hand2")
        self.shift_label.pack(side="left")
        for w in (self.clock_label, self.shift_label):
            w.bind("<Button-1>", lambda _e: TimeWindow(self))

        # controllo velocita in basso a destra
        speed_bar = ttk.Frame(bar)
        speed_bar.pack(side="right")
        controls = (
            ("Pausa", lambda: self._set_speed(paused=True)),
            ("Play", lambda: self._set_speed(paused=False)),
            ("T", lambda: self._set_speed(realtime=True)),
            ("1x", lambda: self._set_speed(speed=1)),
            ("2x", lambda: self._set_speed(speed=2)),
            ("5x", lambda: self._set_speed(speed=5)),
        )
        self._speed_btns = {}
        for label, cmd in controls:
            btn = ttk.Button(speed_bar, text=label, width=5, command=cmd)
            btn.pack(side="left", padx=1)
            self._speed_btns[label] = btn
        self._sync_speed_buttons()

        self._update_time_display()

    def refresh(self):
        self.grid_page.refresh()
        self.timeline_page.refresh()
        self.occupancy_page.refresh()

    def _new_booking(self):
        BookingForm(self, on_done=self.refresh)

    def _open_room(self, room_number: int):
        if self.room_dialog is not None and self.room_dialog.winfo_exists():
            self.room_dialog.show(room_number)
        else:
            self.room_dialog = RoomDialog(self, room_number,
                                          on_change=self.refresh)

    def _open_debug(self):
        DebugToolWindow(self, on_done=self.refresh)

    def _open_guest_room(self, room_number):
        if self.guest_window is not None and self.guest_window.winfo_exists():
            self.guest_window.show(room_number)
        else:
            self.guest_window = GuestRoomWindow(self, room_number)

    def _reception_is_open(self):
        return (self.reception_window is not None
                and self.reception_window.winfo_exists())

    def _open_reception(self):
        if self._reception_is_open():
            self.reception_window.deiconify()
            self.reception_window.lift()
        else:
            self.reception_window = ReceptionWindow(self, on_change=self.refresh)

    def _alert_tick(self):
        if not reception.pending() or self._reception_is_open():
            self.alert.pack_forget()
        elif self.state() == "iconic":
            # dashboard minimizzata: la Reception stessa fa da avviso, in alto a destra
            self.reception_window = ReceptionWindow(self, on_change=self.refresh)
            self.reception_window.geometry(
                f"360x300+{self.winfo_screenwidth() - 380}+20")
            self.reception_window.lift()
            self.reception_window.attributes("-topmost", True)
            self.reception_window.after(
                400, lambda w=self.reception_window:
                w.winfo_exists() and w.attributes("-topmost", False))
        else:
            self._alert_on = not self._alert_on
            self.alert.configure(background="#f0d000" if self._alert_on
                                 else "white")
            self.alert.pack(side="left", before=self._newbtn, padx=(0, 6))
        self.after(500, self._alert_tick)

    def spawn_mail(self):
        """Crea una nuova email e la apre come scheda separata."""
        mail_id = mail.spawn()
        self.refresh()
        MailView(self, mail_id, on_change=self.refresh)

    def _mail_tick(self):
        # tick fisso a 1s: il cambio velocita fa effetto subito (niente lag).
        # rate/sec = (probabilita per intervallo) * velocita di gioco
        cfg = mail.config
        factor = clock.freq_factor()
        if cfg.enabled and factor > 0:
            # la probabilita dipende dal turno (notte rarissima, pranzo/sera rare)
            rate = mail.shift_probability() / max(cfg.interval_seconds, 1) * factor
            if random.random() < min(rate, 1.0):
                self.spawn_mail()
        self.after(1000, self._mail_tick)

    def _set_speed(self, *, speed=None, realtime=False, paused=None):
        """Controllo velocita: moltiplicatore live, non tocca le basi del debug."""
        if paused is True:
            clock.paused = True
        else:
            clock.paused = False        # Play / T / Nx: riprende
            clock.running = True
            if realtime:
                clock.realtime = True
            elif speed is not None:     # 1x/2x/5x; Play (speed=None) tiene la corrente
                clock.realtime = False
                clock.speed = float(speed)
        self._sync_speed_buttons()

    def _sync_speed_buttons(self):
        # in pausa solo Play e attivo; fuori pausa Play e bloccato
        for label, btn in self._speed_btns.items():
            play = label == "Play"
            btn.configure(state="normal" if clock.paused == play else "disabled")

    def _update_time_display(self):
        n = clock.now()
        self.clock_label.config(text=n.strftime("%a %d/%m/%Y  %H:%M"))
        name, color = clock.shift(n)
        self.shift_label.config(text=name, background=color)

    def _time_tick(self):
        clock.tick()
        if clock.running:
            now = clock.now()
            reception.maybe_spawn()   # arrivi/partenze in base al turno
            changed = reception.handle_anger(now)         # ospiti spazientiti
            changed += reservations.auto_checkout_overstayers(now)  # uscite d'ufficio
            if changed:
                self.refresh()
        self._update_time_display()
        if clock.today() != self._last_shown_day:  # giorno avanzato: aggiorna
            self._last_shown_day = clock.today()
            self.refresh()
        self.after(1000, self._time_tick)
