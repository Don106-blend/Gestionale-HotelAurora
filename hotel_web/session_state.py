"""Isolamento multi-sessione e game loop server-side per HotelAurora Web.

hotel/* e scritto per un solo processo desktop e tiene lo stato di gioco in
variabili globali di modulo: la connessione SQLite (hotel.database._conn),
l'orologio simulato (hotel.clock), la config email (hotel.mail.config) e la
cache delle pulizie in corso (hotel.staff._hk). Riscrivere hotel/ per
accettare un oggetto di stato esplicito e vietato dal task (deve restare
invariato), quindi qui si fa un "cambio di contesto": si monta lo stato di
UNA sessione su quei moduli globali, la si usa in esclusiva, la si smonta.
Un lock globale (_game_lock) serializza l'accesso: e la stessa cosa che
succedeva nell'app desktop (single-thread), solo condivisa fra piu partite.
ponytail: lock unico per tutte le sessioni, non uno a testa -> le richieste
di utenti diversi si accodano invece di girare in parallelo. Se il traffico
lo richiedesse, l'upgrade e dare a hotel/ uno stato esplicito iniettabile
(niente piu globali) invece di un lock per sessione, che qui non basterebbe
comunque (i moduli restano condivisi).
"""

import logging
import random
import threading
import time
from pathlib import Path

from hotel import (amenities, budget, clock, database, estate, mail,
                    persistence, problems, reception, reservations, staff,
                    taxes)

DATA_DIR = Path(__file__).resolve().parent.parent / "sessions_data"
DATA_DIR.mkdir(exist_ok=True)

# idle = l'utente non sta giocando attivamente (nessuna azione reale da un po';
# i poll dell'auto-refresh non contano). In idle il tempo scorre a 1x e gli
# input umani ripetitivi (check-in/out, gestione mail) vengono automatizzati.
IDLE_SECONDS = 60        # dopo tot secondi senza azioni reali -> idle
WELCOME_MIN_IDLE = 300   # sotto questa durata di idle niente "Bentornato"
IDLE_MAIL_FACTOR = 0.7      # 30% di mail in meno in idle
IDLE_PROBLEM_FACTOR = 0.5   # in idle, meta dei problemi (gia dimezzati di base)
IDLE_SCALE = 48.0        # "1x": 48 ore di gioco per 1 ora reale

# stato "di fabbrica" dei moduli hotel.*, catturato prima che qualunque
# sessione venga montata: serve a non far trapelare lo stato di una partita
# in un'altra quando persistence.load() non trova ancora nulla nel DB nuovo.
_CLOCK_DEFAULTS = {"sim": clock._sim, "scale": clock.scale, "running": clock.running}

_registry_lock = threading.Lock()   # protegge la creazione di nuove sessioni
_game_lock = threading.RLock()      # una sola sessione monta hotel.* alla volta
_sessions: dict[str, dict] = {}


def _blank_state() -> dict:
    return {
        "speed": 1.0, "paused": False, "realtime": False, "last_mono": None,
        "hk": {"day": None, "busy": {}, "hours": {}, "done": set()},
        "last_activity": time.time(), "idle": False, "idle_start": None,
        "idle_snap": None, "welcome": None,
    }


def known_ids() -> list:
    with _registry_lock:
        return list(_sessions)


class use:
    """with use(session_id): ... monta la partita di quella sessione sui
    moduli hotel.* e la ripristina/salva all'uscita. Rientrante sullo
    stesso thread (RLock) cosi una view puo chiamarlo anche se il tick di
    fondo lo tiene gia per un'altra sessione: si mette in coda, non deadlocka.

    ponytail: apre e chiude la connessione sqlite a ogni mount (schema e
    migrazioni comprese) invece di tenerne una aperta per sessione, perche
    sqlite3 vieta di riusare una connessione da un thread diverso da quello
    che l'ha creata (qui il thread del tick di fondo e quello della singola
    richiesta HTTP sono diversi). Costo accettabile per poche sessioni; se
    diventasse un collo di bottiglia l'upgrade e una cache di connessioni
    thread-local per sessione invece che una connessione condivisa.
    """

    def __init__(self, session_id: str):
        self.sid = session_id

    def __enter__(self):
        _game_lock.acquire()
        with _registry_lock:
            st = _sessions.setdefault(self.sid, _blank_state())
        database.DB_PATH = DATA_DIR / f"{self.sid}.db"
        database._conn = None
        database.get_conn()   # apre/crea/migra/semina nel thread corrente
        # reset ai valori di fabbrica prima del load: se il .db di questa
        # sessione non ha ancora un valore salvato, il fallback deve essere
        # quello "di sistema", non quello lasciato dalla sessione precedente.
        clock._sim, clock.scale, clock.running = (
            _CLOCK_DEFAULTS["sim"], _CLOCK_DEFAULTS["scale"], _CLOCK_DEFAULTS["running"])
        mail.reset_config()
        persistence.load()
        clock.speed, clock.paused, clock.realtime, clock._last_mono = (
            st["speed"], st["paused"], st["realtime"], st["last_mono"])
        staff._hk = st["hk"]
        self._st = st
        return self

    def __exit__(self, exc_type, exc, tb):
        st = self._st
        persistence.save()
        st["speed"], st["paused"], st["realtime"], st["last_mono"] = (
            clock.speed, clock.paused, clock.realtime, clock._last_mono)
        database.close_conn()
        _game_lock.release()
        return False


def tick_session(session_id: str) -> None:
    """Un secondo di gioco per una sessione: lo stesso corpo di
    HotelApp._time_tick/_mail_tick (gui/app.py), spostato qui perche giri
    da solo lato server invece che nel loop eventi di tkinter. In idle il
    tempo e forzato a 1x e alcune azioni umane vengono automatizzate."""
    with use(session_id) as ctx:
        st = ctx._st
        idle = _is_idle(st)
        if idle and not st["idle"]:      # transizione attivo -> idle: fotografa
            st["idle"] = True
            st["idle_start"] = time.time()
            st["idle_snap"] = _snapshot()
        saved = None
        if idle:
            # in idle il tempo scorre a 1x qualunque sia l'impostazione utente,
            # ma senza sovrascriverla in modo permanente (ripristino nel finally)
            saved = (clock.speed, clock.paused, clock.realtime, clock.running,
                     clock.scale)
            (clock.speed, clock.paused, clock.realtime, clock.running,
             clock.scale) = 1.0, False, False, True, IDLE_SCALE
        try:
            clock.tick()
            if clock.running:
                now = clock.now()
                reception.maybe_spawn()
                reception.handle_anger(now)
                reception.serve_meals(now)
                reservations.auto_checkout_overstayers(now)
                reception.room_service(now)
                reception.bar_tick(now)
                reception.auto_desk(now)     # 'autonomo': anche in gioco attivo
                if idle:
                    _idle_auto_desk(now)     # in idle: un receptionist qualsiasi
                problems.tick(now, factor=IDLE_PROBLEM_FACTOR if idle else 1.0)
                staff.tick(now)
                estate.run_utilities(now.date())
                estate.restock_tick(now.date())
                taxes.settle(now.date())
                amenities.accrue_passive(now)

            # come il _mail_tick desktop: indipendente da `running`, azzerato
            # solo dalla pausa (freq_factor() = 0)
            cfg = mail.config
            factor = clock.freq_factor()
            if cfg.enabled and not cfg.block_new_bookings and factor > 0:
                rate = (mail.shift_probability() * mail.demand_factor()
                        * staff.mail_boost(clock.now())
                        / max(cfg.interval_seconds, 1) * factor)
                if idle:
                    rate *= IDLE_MAIL_FACTOR
                if random.random() < min(rate, 1.0):
                    mail.spawn()
            if idle:
                _idle_handle_mail(clock.now())
        finally:
            if saved is not None:
                (clock.speed, clock.paused, clock.realtime, clock.running,
                 clock.scale) = saved


def _is_idle(st: dict) -> bool:
    # in pausa esplicita l'utente ha gia detto "non avanzare": mai forzarlo
    # in idle (niente 1x automatico, niente automazione di check-in/mail).
    if st["paused"]:
        return False
    return time.time() - st["last_activity"] > IDLE_SECONDS


def _rooms_sold() -> int:
    return budget.rooms_sold()


def _snapshot() -> dict:
    t = budget.totals()
    return {"sim": clock.now(), "income": t["income"], "loss": t["loss"],
            "sold": _rooms_sold()}


def _welcome(snap: dict | None):
    if snap is None:
        return None
    t = budget.totals()
    total_h = max(0.0, (clock.now() - snap["sim"]).total_seconds() / 3600)
    earned = round(t["income"] - snap["income"], 2)
    spent = round(t["loss"] - snap["loss"], 2)
    return {"days": int(total_h // 24), "hours": int(total_h % 24),
            "rooms_sold": _rooms_sold() - snap["sold"], "earned": earned,
            "spent": spent, "profit": round(earned - spent, 2)}


def _idle_auto_desk(now) -> None:
    """In idle un receptionist qualsiasi di turno sbriga check-in e check-out
    (come il bonus 'autonomo' ma per tutti). Reclami e To Do NON si toccano:
    restano all'utente al rientro."""
    handler = staff.receptionist_on_duty(now)
    if handler is None:
        return
    for e in reception.pending():
        if e["kind"] == "checkin":
            reception.checkin_entry(e["id"])
        elif e["kind"] == "checkout":
            res = reservations.get(e["reservation_id"])
            if res is not None and res["status"] == "checked_in":
                try:
                    reservations.do_checkout(res["id"], receptionist=handler)
                except reservations.ValidationError:
                    pass
            reception.remove(e["id"])


def _idle_handle_mail(now) -> None:
    """In idle il receptionist di turno gestisce (inserisce) le richieste via
    mail; senza receptionist restano da gestire e scadono (ignorate)."""
    if staff.receptionist_on_duty(now) is None:
        return
    for m in mail.search_mails():
        if mail.status(m) == "Da gestire":
            try:
                mail.insert(m["id"])
            except reservations.ValidationError:
                pass   # hotel pieno: la richiesta scade


def on_request(session_id: str, is_poll: bool) -> None:
    """Da chiamare su ogni richiesta HTTP (dentro il contesto montato).

    Presenza: OGNI richiesta (anche i poll dell'auto-refresh) tiene viva la
    sessione. Il poll pero parte solo con la scheda in primo piano (vedi
    document.hidden nel JS): quindi la sessione va in idle solo quando la
    scheda e chiusa o in background, non mentre l'utente sta guardando.
    Il 'Bentornato Direttore' si calcola solo su una richiesta reale (rientro).
    """
    st = _sessions.get(session_id)
    if st is None:
        return
    st["last_activity"] = time.time()
    if is_poll:
        return
    if st["idle"]:
        if st["idle_start"] and time.time() - st["idle_start"] >= WELCOME_MIN_IDLE:
            st["welcome"] = _welcome(st["idle_snap"])
        st["idle"] = False
        st["idle_start"] = None
        st["idle_snap"] = None


def take_welcome(session_id: str):
    """Ritorna (una sola volta) il riepilogo 'Bentornato' se presente."""
    st = _sessions.get(session_id)
    return st.pop("welcome", None) if st else None


def _loop() -> None:
    while True:
        for sid in known_ids():
            try:
                tick_session(sid)
            except Exception:
                logging.exception("tick di gioco fallito per la sessione %s", sid)
        time.sleep(1)


_started = False


def start_background_loop() -> None:
    """Avvia il thread del game loop (una volta sola per processo) e
    recensisce le sessioni salvate da un eventuale riavvio del server."""
    global _started
    if _started:
        return
    _started = True
    for f in DATA_DIR.glob("*.db"):
        _sessions.setdefault(f.stem, _blank_state())
    threading.Thread(target=_loop, daemon=True, name="hotel-game-loop").start()
