"""Test di verifica della logica di HotelAurora (usa un DB temporaneo)."""

import os
import random
import sys
import tempfile
import time as _time
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# DB temporaneo, per non toccare hotel.db
from hotel import database
database.DB_PATH = Path(tempfile.gettempdir()) / "hotel_aurora_smoke.db"
if database.DB_PATH.exists():
    os.remove(database.DB_PATH)

from hotel import (billing, budget, cleaning, clock, constants, debug_seed,
                   guest_state, guests, mail, meals, persistence, reception,
                   reservations, rooms)

failures = []


def check(name, condition):
    print(("OK  " if condition else "FAIL") + f"  {name}")
    if not condition:
        failures.append(name)


today = date.today()
d = lambda n: today + timedelta(days=n)

# --- camere ---------------------------------------------------------------
all_rooms = rooms.all_rooms()
check("81 camere create", len(all_rooms) == 81)
check("numerazione 101..327", all_rooms[0]["number"] == 101
      and all_rooms[-1]["number"] == 327)
suites = [r["number"] for r in all_rooms if r["is_suite"]]
check("suite = 23-27 di ogni piano",
      suites == [123, 124, 125, 126, 127, 223, 224, 225, 226, 227,
                 323, 324, 325, 326, 327])
check("capienza standard 2+1", rooms.get_room(101)["max_adults"] == 2
      and rooms.get_room(101)["max_children"] == 1)
check("capienza suite 4+1", rooms.get_room(123)["max_adults"] == 4)

# --- prenotazioni e validazioni --------------------------------------------
res_id = reservations.create_reservation(
    first_name="Mario", last_name="Rossi", room_number=101,
    checkin=today, checkout=d(3), adults=2, children=0,
    price_per_night=85, board="BB", discount=None,
    phone="", email="", color="", comments="")
res = reservations.get(res_id)
check("codice prenotazione",
      res["code"] == f"2pax | @{today.strftime('%d/%m')} | BB | Pagdir")

# il @ del codice e la data di prenotazione (oggi), non il check-in futuro
future_id = reservations.create_reservation(
    first_name="Futuro", last_name="Ospite", room_number=105, checkin=d(5),
    checkout=d(7), adults=1, children=0, price_per_night=50, board="RO",
    discount=None, phone="", email="", color="", comments="")
check("codice @ = data prenotazione, non check-in",
      f"@{today.strftime('%d/%m')}" in reservations.get(future_id)["code"])

check("camera occupata nel periodo non disponibile",
      not reservations.is_room_available(101, d(1), d(2)))
check("back-to-back consentito (arrivo il giorno del check-out)",
      reservations.is_room_available(101, d(3), d(5)))
check("camera libera disponibile",
      reservations.is_room_available(102, today, d(3)))

try:
    reservations.create_reservation(
        first_name="", last_name="", room_number=102,
        checkin=today, checkout=d(1), adults=1, children=0,
        price_per_night=50, board="RO", discount=None,
        phone="", email="", color="", comments="")
    check("errore se nome e cognome entrambi vuoti", False)
except reservations.ValidationError:
    check("errore se nome e cognome entrambi vuoti", True)

ok_one_name = reservations.create_reservation(
    first_name="", last_name="Verdi", room_number=102,
    checkin=today, checkout=d(1), adults=1, children=0,
    price_per_night=50, board="RO", discount=None,
    phone="", email="", color="", comments="")
check("solo cognome accettato", ok_one_name is not None)

try:
    reservations.create_reservation(
        first_name="X", last_name="Y", room_number=999,
        checkin=today, checkout=d(1), adults=1, children=0,
        price_per_night=10, board="RO", discount=None,
        phone="", email="", color="", comments="")
    check("errore camera inesistente", False)
except reservations.ValidationError:
    check("errore camera inesistente", True)

rooms.set_blocked(103, True)
try:
    reservations.create_reservation(
        first_name="X", last_name="Y", room_number=103,
        checkin=today, checkout=d(1), adults=1, children=0,
        price_per_night=10, board="RO", discount=None,
        phone="", email="", color="", comments="")
    check("errore camera bloccata", False)
except reservations.ValidationError:
    check("errore camera bloccata", True)
rooms.set_blocked(103, False)

check("avviso capienza superata (3 adulti in standard)",
      reservations.capacity_warning(101, 3, 0) is not None)
check("nessun avviso entro la capienza",
      reservations.capacity_warning(123, 4, 1) is None)

# --- check-in ----------------------------------------------------------------
try:
    reservations.do_checkin(res_id, [{"first_name": "", "last_name": "",
                                      "birth_date": ""}])
    check("check-in rifiutato senza nome+cognome completi", False)
except reservations.ValidationError:
    check("check-in rifiutato senza nome+cognome completi", True)

reservations.do_checkin(res_id, [
    {"first_name": "Mario", "last_name": "Rossi", "birth_date": "01/01/1980",
     "birth_place": "Milano", "document_type": "Carta d'identita",
     "document_number": "AB123", "is_child": False},
    {"first_name": "Anna", "last_name": "", "birth_date": "",
     "birth_place": "", "document_type": "", "document_number": "",
     "is_child": False},
])
res = reservations.get(res_id)
check("stato checked_in", res["status"] == "checked_in")
check("camera sporca dopo il check-in", rooms.get_room(101)["dirty"] == 1)
check("camera risulta occupata",
      reservations.current_for_room(101) is not None)

# ospite abituale: stesso nome+data nascita -> riusato, non duplicato
gid1 = guests.upsert({"first_name": "Mario", "last_name": "Rossi",
                      "birth_date": "01/01/1980", "birth_place": "Milano",
                      "document_type": "Passaporto", "document_number": "P9"})
n_rossi = len([g for g in guests.search("Rossi")])
check("ospite abituale riusato (no duplicati)", n_rossi == 1)

# --- conto -------------------------------------------------------------------
t = billing.bill_totals(res)
check("subtotale 3 notti x 85 = 255", t["subtotal"] == 255)
check("totale con IVA 22% = 311.10 (esempio del prompt)",
      t["total"] == 311.10)
text = billing.bill_text(res, "Mario Rossi")
check("riga conto formato 'BB gg/mm prezzo'",
      f"BB   {today.strftime('%d/%m')}       85.00 EUR" in text)

# sconto
disc_id = reservations.create_reservation(
    first_name="Luigi", last_name="Bianchi", room_number=104,
    checkin=today, checkout=d(2), adults=1, children=0,
    price_per_night=100, board="HB", discount=10,
    phone="", email="", color="", comments="")
t2 = billing.bill_totals(reservations.get(disc_id))
check("sconto 10% su 200 -> totale 219.60",
      t2["discount_amount"] == 20 and t2["total"] == 219.60)

# --- pasti ---------------------------------------------------------------
# oggi: BB (colazione domani, non oggi), HB (cena oggi)
rows_breakfast_today = meals.meal_rows("colazione", today)
rows_breakfast_tomorrow = meals.meal_rows("colazione", d(1))
rows_dinner_today = meals.meal_rows("cena", today)
check("colazione: non il giorno di arrivo",
      101 not in [r[0] for r in rows_breakfast_today])
check("colazione: dal mattino successivo",
      101 in [r[0] for r in rows_breakfast_tomorrow])
check("cena HB il giorno di arrivo",
      104 in [r[0] for r in rows_dinner_today])
check("RO senza pasti", 102 not in [r[0] for r in rows_dinner_today])
sheet = meals.sheet_text("colazione", d(1))
check("totale ospiti nel foglio pasti", "Totale ospiti" in sheet)

# --- pulizie -----------------------------------------------------------------
# camera 101: oggi e arrivo (niente), domani rimanenza 0.25, d(3) check-out 0.5
tasks_today = {t.room_number: t.hours for t in cleaning.tasks_for_day(today)}
tasks_t1 = {t.room_number: t.hours for t in cleaning.tasks_for_day(d(1))}
tasks_t3 = {t.room_number: t.hours for t in cleaning.tasks_for_day(d(3))}
check("nessuna pulizia il giorno di arrivo", 101 not in tasks_today)
check("rimanenza 0.25h", tasks_t1.get(101) == 0.25)
check("check-out 0.5h", tasks_t3.get(101) == 0.5)

# suite RES: solo venerdi (1h) e 3h al check-out
res_suite = reservations.create_reservation(
    first_name="Sig", last_name="Residence", room_number=123,
    checkin=today, checkout=d(14), adults=2, children=0,
    price_per_night=120, board="RES", discount=None,
    phone="", email="", color="", comments="")
friday = next(d(i) for i in range(1, 8) if d(i).weekday() == 4)
non_friday = next(d(i) for i in range(1, 8)
                  if d(i).weekday() != 4 and d(i) != d(14))
check("suite RES: nessuna pulizia nei giorni feriali",
      123 not in {t.room_number for t in cleaning.tasks_for_day(non_friday)})
check("suite RES: 1h il venerdi",
      {t.room_number: t.hours for t in
       cleaning.tasks_for_day(friday)}.get(123) == 1.0)
check("suite RES: 3h al check-out",
      {t.room_number: t.hours for t in
       cleaning.tasks_for_day(d(14))}.get(123) == 3.0)

# camere gia in checked_out compaiono comunque nel foglio del giorno
reservations.do_checkout(res_id)
check("dopo il check-out la camera e libera",
      reservations.current_for_room(101) is None)
check("dopo il check-out resta sporca", rooms.get_room(101)["dirty"] == 1)
check("camera partita resta nel foglio pulizie del giorno di check-out",
      101 in {t.room_number for t in cleaning.tasks_for_day(d(3))})
check("prenotazione checked_out sparisce dalla timeline",
      res_id not in {r["id"] for r in reservations.in_range(today, d(5))})

# il check-out alimenta il budget: 3 notti x 85 = 255 netto, IVA 56.10
bt = budget.totals()
check("budget: introito netto al check-out", bt["income"] == 255.0)
check("budget: perdita IVA al check-out", bt["loss"] == 56.10)
check("budget: saldo = introiti - perdite", bt["balance"] == 198.90)

# bilanciamento operatori: 30 camere in check-out = 15h -> 2 operatori
for i in range(5, 27):
    reservations.create_reservation(
        first_name="Test", last_name=f"Op{i}", room_number=200 + i,
        checkin=d(5), checkout=d(6), adults=1, children=0,
        price_per_night=50, board="RO", discount=None,
        phone="", email="", color="", comments="")
ops = cleaning.assign_operators(cleaning.tasks_for_day(d(6)))
loads = [sum(t.hours for t in op) for op in ops]
check("nessun operatore oltre 8h", all(load <= 8 for load in loads))
check("carichi bilanciati (scarto max 1h)",
      max(loads) - min(loads) <= 1.0)

# --- tool di debug (seeding) -------------------------------------------------
debug_seed.clear_all()
check("clear_all azzera le prenotazioni",
      len(reservations.in_range(today, d(90))) == 0)
check("clear_all azzera lo stato camere", rooms.get_room(101)["dirty"] == 0)

cfg = debug_seed.SeedConfig(
    count=40, start=today, end=d(20), min_nights=2, max_nights=5,
    board_prices=dict(debug_seed.DEFAULT_BOARD_PRICES),
    random_colors=True, auto_checkin=True)
seed_res = debug_seed.seed_reservations(cfg, rng=random.Random(42))
check("seeding crea prenotazioni", seed_res.created > 0)
check("seeding rispetta il count richiesto",
      seed_res.created + seed_res.failed == 40)
check("seeding esegue qualche check-in oggi", seed_res.checked_in > 0)

seeded = reservations.in_range(today - timedelta(days=1), d(90))
fields_ok = True
for r in seeded:
    ci = date.fromisoformat(r["checkin_date"])
    co = date.fromisoformat(r["checkout_date"])
    nights = (co - ci).days
    if not (2 <= nights <= 5):
        fields_ok = False
    if not (today <= ci <= d(20)):
        fields_ok = False
    if not (r["first_name"] or r["last_name"]):
        fields_ok = False
    if not r["phone"] or not r["email"] or r["price_per_night"] <= 0:
        fields_ok = False
check("notti, date, nome, telefono, email, prezzo riempiti", fields_ok)

price_ok = all(
    abs(r["price_per_night"] - debug_seed.DEFAULT_BOARD_PRICES[r["board"]]) < 1e-6
    for r in seeded)
check("prezzo coerente con la soluzione", price_ok)

by_room = defaultdict(list)
for r in seeded:
    by_room[r["room_number"]].append(
        (date.fromisoformat(r["checkin_date"]),
         date.fromisoformat(r["checkout_date"])))
no_overlap = True
for stays in by_room.values():
    stays.sort()
    for (_s1, e1), (s2, _e2) in zip(stays, stays[1:]):
        if s2 < e1:
            no_overlap = False
check("nessuna sovrapposizione di camere", no_overlap)

# --- indicatori dashboard (arrival_on) e orologio override -------------------
debug_seed.clear_all()
reservations.create_reservation(
    first_name="Arrivo", last_name="Oggi", room_number=101,
    checkin=d(2), checkout=d(5), adults=1, children=0,
    price_per_night=80, board="BB", discount=None,
    phone="", email="", color="", comments="")
check("arrival_on trova l'arrivo nel giorno di check-in",
      reservations.arrival_on(101, d(2)) is not None)
check("arrival_on None nei giorni di rimanenza",
      reservations.arrival_on(101, d(3)) is None)
check("arrival_on None su un'altra camera",
      reservations.arrival_on(102, d(2)) is None)

clock.set_today(d(10))
check("clock override attivo", clock.today() == d(10))
clock.set_today(None)
check("clock reset alla data reale", clock.today() == date.today())

# turni della giornata
check("turno mattina", clock.shift(datetime(2026, 1, 1, 9))[0] == "Mattina")
check("turno pranzo", clock.shift(datetime(2026, 1, 1, 13))[0] == "Pranzo")
check("turno pomeriggio",
      clock.shift(datetime(2026, 1, 1, 16))[0] == "Pomeriggio")
check("turno sera", clock.shift(datetime(2026, 1, 1, 20))[0] == "Sera")
check("turno notte dopo mezzanotte",
      clock.shift(datetime(2026, 1, 1, 2))[0] == "Notte")
check("turno notte prima delle 7",
      clock.shift(datetime(2026, 1, 1, 23, 30))[0] == "Notte")

# avanzamento del tempo in scala
clock.set_now(datetime(2026, 1, 1, 12))
clock.scale = 3600          # 1s reale -> 3600s gioco = 1h gioco
clock.running = True
clock._last_mono = _time.monotonic() - 2.0   # finge 2s reali trascorsi
clock.tick()
delta_h = (clock.now() - datetime(2026, 1, 1, 12)).total_seconds() / 3600
check("tempo avanza in scala (~2h gioco per 2s reali a 3600x)",
      1.9 <= delta_h <= 2.6)
clock.running = False
clock.set_now(None)
clock.scale = 24.0
clock._last_mono = None

# controllo velocita: moltiplicatore live che NON tocca le basi del debug
clock.scale = 24.0
clock.speed = 1.0
clock.paused = False
clock.realtime = False
check("velocita 1x = base (freq_factor 1)", clock.freq_factor() == 1.0)
clock.speed = 5.0
check("5x: freq_factor segue la velocita", clock.freq_factor() == 5.0)
check("5x NON cambia la scala base (debug)", clock.scale == 24.0)
clock.realtime = True
check("T (tempo reale): freq_factor 1", clock.freq_factor() == 1.0)
clock.paused = True
check("pausa: freq_factor 0", clock.freq_factor() == 0.0)

# il tick scala per speed; in pausa congela
clock.realtime = False
clock.paused = False
clock.set_now(datetime(2026, 1, 1, 12))
clock.scale = 10.0
clock.speed = 3.0
clock.running = True
clock._last_mono = _time.monotonic() - 1.0
clock.tick()
adv = (clock.now() - datetime(2026, 1, 1, 12)).total_seconds()
check("tick avanza scale*speed (~10*3 game-sec/sec)", 25 <= adv <= 45)
clock.paused = True
clock._last_mono = _time.monotonic() - 1.0
frozen = clock.now()
clock.tick()
check("pausa congela il tempo", clock.now() == frozen)

clock.paused = False
clock.realtime = False
clock.speed = 1.0
clock.running = False
clock.scale = 24.0
clock.set_now(None)
clock._last_mono = None

# --- gameplay email ----------------------------------------------------------
debug_seed.clear_all()
mail.rng.seed(7)
mail.config.auto_insert = False
mid = mail.spawn()
m = mail.get(mid)
check("email mittente nome.cognome@email.com",
      m["sender"].endswith("@email.com") and "." in m["sender"].split("@")[0])
check("email body riempito dal template", len(m["body"]) > 40)
check("email non ancora inserita", m["inserted"] == 0)

room = mail.insert(mid)
check("insert email crea prenotazione in una camera valida",
      rooms.get_room(room) is not None)
check("email segnata come inserita", mail.get(mid)["inserted"] == 1)
booked = reservations.arrival_on(room, date.fromisoformat(m["checkin"]))
check("prenotazione creata coi nomi della mail",
      booked is not None and booked["last_name"] == m["last_name"])

try:
    mail.insert(mid)
    check("doppio insert email bloccato", False)
except reservations.ValidationError:
    check("doppio insert email bloccato", True)

mail.config.auto_insert = True
mid2 = mail.spawn()
check("auto-insert: email inserita allo spawn", mail.get(mid2)["inserted"] == 1)
mail.config.auto_insert = False

# mittente senza spazi anche con cognomi composti (es. "De Luca")
check("email mittente senza spazi (cognomi composti)",
      all(" " not in mail.get(mail.spawn())["sender"] for _ in range(40)))

# ospiti abituali: riuso del DB ospiti, niente doppioni
debug_seed.clear_all()
mail.config.auto_insert = False
guests.upsert({"first_name": "Anna", "last_name": "Bianchi",
               "birth_date": "01/01/1990"})
mail.config.returning_probability = 1.0
pick = mail._pick_returning_guest()
check("ospite abituale riusato dalla mail",
      pick is not None and pick["last_name"] == "Bianchi")
m_ret = mail.get(mail.spawn())
check("email usa nome ed email dell'ospite abituale",
      m_ret["last_name"] == "Bianchi"
      and m_ret["sender"] == "anna.bianchi@email.com")

reservations.create_reservation(
    first_name="Anna", last_name="Bianchi", room_number=101,
    checkin=today, checkout=d(2), adults=1, children=0, price_per_night=80,
    board="BB", discount=None, phone="", email="", color="", comments="")
check("abituale con prenotazione attiva escluso (no doppioni)",
      mail._pick_returning_guest() is None)

mail.config.returning_probability = 0.0
check("prob abituali 0 -> nessun riuso", mail._pick_returning_guest() is None)
mail.config.returning_probability = 0.5

# finestra prenotazioni mail: check-in entro window_days dal tempo simulato
debug_seed.clear_all()
mail.config.auto_insert = False
mail.config.window_days = 3
clock.set_now(datetime(2026, 7, 1, 16))
base = clock.today()
offsets = [(date.fromisoformat(mail.get(mail.spawn())["checkin"]) - base).days
           for _ in range(30)]
check("mail: check-in entro la finestra configurata (window_days)",
      all(0 <= o <= 3 for o in offsets) and max(offsets) >= 1)
clock.set_now(None)
mail.config.window_days = 5

# frequenza mail variabile per turno
mail.config.probability = 0.5
mail.config.shift_probability = {"Pranzo": 0.2, "Sera": 0.2, "Notte": 0.05}
p_at = lambda hour: (clock.set_now(datetime(2026, 1, 1, hour)),
                     mail.shift_probability())[1]
check("mail standard di mattina", p_at(9) == 0.5)
check("mail standard di pomeriggio", p_at(16) == 0.5)
check("mail rara a pranzo", p_at(13) == 0.2)
check("mail rara di sera", p_at(20) == 0.2)
check("mail rarissima di notte ma non zero", 0 < p_at(2) <= 0.05)
clock.set_now(None)

# --- reception (arrivi e partenze) -------------------------------------------
debug_seed.clear_all()
afternoon = datetime(today.year, today.month, today.day, 16)
morning = datetime(today.year, today.month, today.day, 9)

rid = reservations.create_reservation(
    first_name="Carlo", last_name="Neri", room_number=101,
    checkin=today, checkout=d(3), adults=2, children=1, price_per_night=80,
    board="BB", discount=None, phone="", email="", color="", comments="")

# tutti gli ospiti spawnano insieme, una riga ciascuno
reception._spawn_checkin(reservations.get(rid), afternoon)
check("reception: una riga per persona (2 adulti + 1 bambino)",
      len(reception.pending()) == 3)

# check-in per-persona: la prima occupa la camera, la riga sparisce
reception.checkin_entry(reception.pending()[0]["id"])
check("reception: primo check-in occupa la camera",
      reservations.current_for_room(101) is not None)
check("reception: la riga sparisce dopo il check-in",
      len(reception.pending()) == 2)
for e in list(reception.pending()):
    reception.checkin_entry(e["id"])
check("reception: check-in di tutti svuota la coda",
      not reception.pending())
n_guests = database.get_conn().execute(
    "SELECT COUNT(*) FROM reservation_guests WHERE reservation_id = ?",
    (rid,)).fetchone()[0]
check("reception: registrati tutti e 3 gli ospiti", n_guests == 3)

# arrivi distribuiti nella finestra 15-23, mai negli altri turni
debug_seed.clear_all()
arr_ids = [reservations.create_reservation(
    first_name="A", last_name=str(room), room_number=room, checkin=today,
    checkout=d(2), adults=1, children=0, price_per_night=50, board="RO",
    discount=None, phone="", email="", color="", comments="")
    for room in range(101, 109)]
for hour in (9, 13, 1):   # Mattina, Pranzo, Notte
    clock.set_now(datetime(today.year, today.month, today.day, hour))
    for _ in range(20):
        reception.maybe_spawn()
check("reception: nessun arrivo fuori da Pomeriggio/Sera", not reception.pending())
hours = [reception._scheduled_time("arr", rid, today,
                                   reception.ARRIVAL_WINDOW).hour for rid in arr_ids]
check("orari di arrivo dentro 15-23", all(15 <= h < 23 for h in hours))
check("orari di arrivo distribuiti (non tutti uguali)", len(set(hours)) >= 2)
clock.set_now(datetime(today.year, today.month, today.day, 22, 59))
for _ in range(3):
    reception.maybe_spawn()
check("entro fine sera arrivano tutti", len(reception.pending()) == len(arr_ids))
clock.set_now(None)

# partenze: dovute solo per checked_in con check-out oggi
debug_seed.clear_all()
rid3 = reservations.create_reservation(
    first_name="C", last_name="D", room_number=103, checkin=d(-2),
    checkout=today, adults=1, children=0, price_per_night=50, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid3, {"first_name": "C", "last_name": "D"})
check("reception: partenza dovuta trovata",
      len(reception._due_departures(today)) == 1)
reception._spawn_checkout(reservations.get(rid3), morning)
check("reception: spawn check-out una sola riga",
      len(reception.pending()) == 1 and reception.pending()[0]["kind"] == "checkout")

# --- genoma / stato dinamico degli ospiti ------------------------------------
check("genoma stabile per guest_id",
      guest_state.metadata(42) == guest_state.metadata(42))
g42 = guest_state.metadata(42)
check("ora di sonno nel turno notturno (offset 60-540 da 22:00)",
      60 <= g42["sleep_offset"] <= 540)
check("durata sonno 4-9 ore", 4 <= g42["wake_hours"] <= 9)

onset, wake = guest_state.sleep_window(7, date(2026, 1, 1))
mid = onset + (wake - onset) / 2
check("addormentato dentro la finestra di sonno",
      guest_state.stato(7, mid) == "Addormentato")
check("sveglio fuori dalla finestra",
      guest_state.stato(7, wake + timedelta(hours=3)) == "Sveglio")
check("addormentato -> locazione Letto",
      guest_state.locazione("Addormentato", 7, mid) == "Letto")
check("sveglio -> locazione dalla libreria",
      guest_state.locazione("Sveglio", 7, onset) in guest_state.LOCATIONS)

# stato Assente
debug_seed.clear_all()
afternoon = datetime(today.year, today.month, today.day, 14, 0)

# appena arrivato (entro settle_minutes) -> Assente / locazione esterna
settle = guest_state.settle_minutes(9999)
check("settle 1-30 min", 1 <= settle <= 30)
row = {"id": 1000, "first_name": "Tan", "last_name": "Tan", "board": "RO",
       "reservation_id": 8888, "rg_id": 9999, "checked_in_at": afternoon.isoformat()}
d0 = guest_state.describe(row, afternoon)
check("appena arrivato -> Assente", d0["stato"] == "Assente")
check("Assente -> colore grigio", d0["color"] == guest_state.COLORS["Assente"])
check("Assente -> locazione esterna",
      d0["locazione"] in guest_state.EXTERNAL_LOCATIONS)

# in reception per il check-out -> Assente / Reception
rid_a = reservations.create_reservation(
    first_name="Out", last_name="Going", room_number=104, checkin=d(-1),
    checkout=today, adults=1, children=0, price_per_night=50, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_a, {"first_name": "Out", "last_name": "Going"})
reception._spawn_checkout(reservations.get(rid_a),
                          datetime(today.year, today.month, today.day, 8))
grow = guests.for_reservation(rid_a)[0]
d_rec = guest_state.describe(grow, datetime(today.year, today.month, today.day, 8, 30))
check("in reception check-out -> Assente",
      d_rec["stato"] == "Assente" and d_rec["locazione"] == "Reception")

# uscita di giorno -> Assente / esterna (cerca un ospite con un'uscita)
found = False
for gid in range(1, 300):
    for hh in range(9, 20):
        t = datetime(2026, 6, 1, hh, 30)
        if guest_state._on_outing(gid, t) and not guest_state._is_asleep(gid, t):
            orow = {"id": gid, "first_name": "P", "last_name": "Q", "board": "RO",
                    "reservation_id": 77777, "rg_id": 77777,
                    "checked_in_at": (t - timedelta(hours=5)).isoformat()}
            dd = guest_state.describe(orow, t)
            check("uscita di giorno -> Assente/esterna",
                  dd["stato"] == "Assente"
                  and dd["locazione"] in guest_state.EXTERNAL_LOCATIONS)
            found = True
            break
    if found:
        break
check("almeno un'uscita generata tra gli ospiti", found)

# --- pasti per board (assenza in sala) ---------------------------------------
check("BB -> solo colazione",
      guest_state.BOARD_MEALS["BB"] == ("Colazione",))
check("HB -> colazione e cena",
      set(guest_state.BOARD_MEALS["HB"]) == {"Colazione", "Cena"})
check("FB -> tre pasti",
      set(guest_state.BOARD_MEALS["FB"]) == {"Colazione", "Pranzo", "Cena"})
check("RO/RES -> nessun pasto",
      guest_state.BOARD_MEALS["RO"] == () and guest_state.BOARD_MEALS["RES"] == ())

check("pasto corrente: colazione alle 7",
      guest_state.current_meal(datetime(2026, 1, 1, 7)) == "Colazione")
check("pasto corrente: pranzo alle 13",
      guest_state.current_meal(datetime(2026, 1, 1, 13)) == "Pranzo")
check("pasto corrente: cena alle 20",
      guest_state.current_meal(datetime(2026, 1, 1, 20)) == "Cena")
check("nessun pasto alle 16",
      guest_state.current_meal(datetime(2026, 1, 1, 16)) is None)

s_c, e_c = guest_state._meal_slot(123, date(2026, 1, 1), "Colazione")
check("colazione dentro la finestra 6-10",
      time(6) <= s_c.time() and e_c.time() <= time(10, 0, 1))
check("attivita pasto dura 1h", e_c - s_c == timedelta(hours=1))
check("colazione fatta dopo lo slot",
      guest_state.has_done_meal(123, "BB", "Colazione", e_c + timedelta(minutes=1)))
check("colazione non fatta prima",
      not guest_state.has_done_meal(123, "BB", "Colazione",
                                    s_c - timedelta(minutes=1)))
check("reset il giorno dopo",
      not guest_state.has_done_meal(123, "BB", "Colazione",
                                    datetime(2026, 1, 2, 5)))

# un ospite (sveglio) a colazione -> Assente / Sala colazione
eat_gid = None
for gid in range(1, 500):
    s, _e = guest_state._meal_slot(gid, date(2026, 6, 1), "Colazione")
    t = s + timedelta(minutes=20)
    if not guest_state._is_asleep(gid, t):
        eat_gid, eat_t = gid, t
        break
check("BB a colazione -> is_eating",
      guest_state.is_eating(eat_gid, "BB", "Colazione", eat_t))
check("RO a colazione -> niente",
      not guest_state.is_eating(eat_gid, "RO", "Colazione", eat_t))
meal_row = {"id": eat_gid, "first_name": "A", "last_name": "B",
            "reservation_id": 0, "rg_id": 0, "board": "BB",
            "checked_in_at": (eat_t - timedelta(hours=3)).isoformat()}
dm = guest_state.describe(meal_row, eat_t)
check("a colazione -> Assente / Sala colazione",
      dm["stato"] == "Assente" and dm["locazione"] == "Sala colazione")

# check-out bloccato mentre un ospite e a un pasto
debug_seed.clear_all()
rid_bb = reservations.create_reservation(
    first_name="Bee", last_name="Bee", room_number=105, checkin=d(-1),
    checkout=today, adults=1, children=0, price_per_night=50, board="BB",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_bb, {"first_name": "Bee", "last_name": "Bee"})
gid_bb = guests.for_reservation(rid_bb)[0]["id"]
s_bb, e_bb = guest_state._meal_slot(gid_bb, today, "Colazione")
t_bb = s_bb + timedelta(minutes=5)
if not guest_state._is_asleep(gid_bb, t_bb):
    check("a colazione -> reservation_at_meal True",
          guest_state.reservation_at_meal(rid_bb, t_bb))
check("fuori pasto -> reservation_at_meal False",
      not guest_state.reservation_at_meal(rid_bb, e_bb + timedelta(hours=2)))

# --- persistenza stato di gioco ----------------------------------------------
clock.set_now(datetime(2026, 3, 1, 8, 30))
clock.scale = 50.0
clock.running = True
mail.config.enabled = True
mail.config.interval_seconds = 17
mail.config.probability = 0.3
persistence.save()

clock.set_now(None)
clock.scale = 24.0
clock.running = False
mail.config.enabled = False
mail.config.interval_seconds = 60
mail.config.probability = 0.5
persistence.load()

check("persistenza: ora simulata ripristinata",
      clock.now() == datetime(2026, 3, 1, 8, 30))
check("persistenza: scala ripristinata", clock.scale == 50.0)
check("persistenza: running ripristinato", clock.running is True)
check("persistenza: config email ripristinata",
      mail.config.enabled is True and mail.config.interval_seconds == 17
      and mail.config.probability == 0.3)
clock.set_now(None)
clock.running = False
mail.config.enabled = False

# --- sicurezza check-out: uscita d'ufficio dopo le 14:30, senza addebito -----
debug_seed.clear_all()
clock.set_now(datetime(today.year, today.month, today.day, 10, 0))
rid_ov = reservations.create_reservation(
    first_name="Over", last_name="Stay", room_number=110, checkin=d(-2),
    checkout=today, adults=1, children=0, price_per_night=100, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_ov, {"first_name": "Over", "last_name": "Stay"})
check("overstay: prima delle 14:30 nessuna uscita d'ufficio",
      reservations.auto_checkout_overstayers(clock.now()) == 0)
check("overstay: ancora in camera",
      reservations.get(rid_ov)["status"] == "checked_in")
clock.set_now(datetime(today.year, today.month, today.day, 14, 31))
check("overstay: uscita d'ufficio dopo le 14:30",
      reservations.auto_checkout_overstayers(clock.now()) == 1)
check("overstay: ora checked_out",
      reservations.get(rid_ov)["status"] == "checked_out")
unpaid = [e for e in budget.entries() if e["note"] == "L'ospite non ha pagato."]
check("overstay: a bilancio importo 0",
      len(unpaid) == 1 and unpaid[0]["amount"] == 0)
clock.set_now(None)

# --- ospite arrabbiato al check-in (attesa > 1,5h) ---------------------------
debug_seed.clear_all()
clock.set_now(datetime(today.year, today.month, today.day, 16, 0))
rid_ang = reservations.create_reservation(
    first_name="Furio", last_name="Iroso", room_number=111, checkin=today,
    checkout=d(2), adults=1, children=0, price_per_night=80, board="RO",
    discount=None, phone="", email="furio@email.com", color="", comments="")
reception._spawn_checkin(reservations.get(rid_ang), clock.now())
check("anger: prima di 1,5h non scatta", reception.handle_anger(clock.now()) == 0)
clock.set_now(datetime(today.year, today.month, today.day, 17, 31))
check("anger: scatta dopo 1,5h", reception.handle_anger(clock.now()) == 1)
check("anger: prenotazione annullata",
      reservations.get(rid_ang)["status"] == "cancelled")
check("anger: sparito dalla reception", not reception.pending())
check("anger: mail di reclamo (spam)",
      len([m for m in mail.all_mails() if m["kind"] == "spam"]) == 1)
check("anger: finito in blacklist", database.get_conn().execute(
    "SELECT COUNT(*) FROM blacklist WHERE last_name = 'Iroso'").fetchone()[0] == 1)
clock.set_now(None)

# --- stato/scadenza/rifiuto delle mail ---------------------------------------
debug_seed.clear_all()
clock.set_now(datetime(2026, 6, 1, 12, 0))
mid = mail.spawn()
check("mail nuova: Da gestire", mail.status(mail.get(mid)) == "Da gestire")
mail.reject(mid)
check("mail rifiutata: stato Rifiutata", mail.status(mail.get(mid)) == "Rifiutata")
try:
    mail.insert(mid)
    blocked = False
except reservations.ValidationError:
    blocked = True
check("mail rifiutata non inseribile", blocked)
mid2 = mail.spawn()
check("mail fresca non scaduta",
      not mail.is_expired(mail.get(mid2), clock.now()))
check("mail scaduta dopo 48h",
      mail.is_expired(mail.get(mid2), clock.now() + timedelta(hours=49)))
rid_sp = reservations.create_reservation(
    first_name="Spa", last_name="Mmer", room_number=113, checkin=d(1),
    checkout=d(3), adults=1, children=0, price_per_night=50, board="RO",
    discount=None, phone="", email="", color="", comments="")
check("mail spam: stato Spam", mail.status(
    mail.get(mail.spawn_complaint(reservations.get(rid_sp)))) == "Spam")
clock.set_now(None)

# --- marcatore di arrivo solo prima del check-in -----------------------------
debug_seed.clear_all()
rid_arr = reservations.create_reservation(
    first_name="Pre", last_name="Arrivo", room_number=112, checkin=today,
    checkout=d(2), adults=1, children=0, price_per_night=50, board="RO",
    discount=None, phone="", email="", color="", comments="")
check("arrivo oggi: marcatore presente (booked)",
      reservations.arrival_on(112, today) is not None)
reservations.checkin_guest(rid_arr, {"first_name": "Pre", "last_name": "Arrivo"})
check("dopo il check-in: marcatore sparito",
      reservations.arrival_on(112, today) is None)

print()
if failures:
    print(f"{len(failures)} TEST FALLITI: {failures}")
    sys.exit(1)
print("Tutti i test sono passati.")
