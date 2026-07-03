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

from hotel import (amenities, bank, billing, budget, cleaning, clock,
                   constants, debug_seed, guest_state, guests, mail, meals,
                   persistence, problems, reception, reservations, reviews,
                   rooms, staff, taxes)

staff.SICK_PROB = 0.0   # malattie testate a parte: qui tutto deterministico

failures = []


def check(name, condition):
    print(("OK  " if condition else "FAIL") + f"  {name}")
    if not condition:
        failures.append(name)


def _raises(fn):
    try:
        fn()
        return False
    except Exception:
        return True


today = date.today()
d = lambda n: today + timedelta(days=n)

# --- camere (hotel scalabile: 10 all'avvio, 2 suite) ----------------------
all_rooms = rooms.all_rooms()
check("10 camere iniziali", len(all_rooms) == 10)
check("numerazione 101..110",
      [r["number"] for r in all_rooms] == list(range(101, 111)))
check("2 suite all'avvio (109, 110)",
      [r["number"] for r in all_rooms if r["is_suite"]] == [109, 110])
check("capienza standard 2+1", rooms.get_room(101)["max_adults"] == 2
      and rooms.get_room(101)["max_children"] == 1)
check("capienza suite 4+1", rooms.get_room(110)["max_adults"] == 4)

# il resto dei test usa molte camere: ricreo un layout ampio (piani 1-3, 27/piano)
_conn = database.get_conn()
_conn.execute("DELETE FROM rooms")
for _fl in (1, 2, 3):
    for _n in range(1, 28):
        _suite = _n >= 23
        _conn.execute(
            "INSERT INTO rooms (number, floor, is_suite, max_adults, max_children)"
            " VALUES (?, ?, ?, ?, ?)",
            (_fl * 100 + _n, _fl, int(_suite), 4 if _suite else 2, 1))
database.kv_set("floors", [1, 2, 3])
_conn.commit()
check("layout ampio per i test: 81 camere", len(rooms.all_rooms()) == 81)

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

# il check-out incassa il 100% del ricavato (311.10); l'IVA si accantona
bt = budget.totals()
check("budget: introito 100% del ricavato al check-out",
      bt["income"] == 311.10)
check("budget: IVA accantonata, non a perdite",
      bt["loss"] == 0.0 and taxes.vat_due() == 56.10)
check("budget: saldo = introiti - perdite", bt["balance"] == 311.10)

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
for _ in range(3):        # rating 5: il fattore reputazione non taglia i riusi
    reviews._add("Fan Sfegatato", 5)
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

# --- spostamento camera (drag&drop timeline) ---------------------------------
debug_seed.clear_all()
rid_mv = reservations.create_reservation(
    first_name="Spo", last_name="Sta", room_number=101, checkin=d(1),
    checkout=d(3), adults=1, children=0, price_per_night=50, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.change_room(rid_mv, 102)
moved = reservations.get(rid_mv)
check("change_room: camera aggiornata", moved["room_number"] == 102)
check("change_room: date invariate",
      moved["checkin_date"] == d(1).isoformat()
      and moved["checkout_date"] == d(3).isoformat())
# camera occupata nello stesso periodo -> rifiuto
reservations.create_reservation(
    first_name="Occ", last_name="Upa", room_number=103, checkin=d(1),
    checkout=d(3), adults=1, children=0, price_per_night=50, board="RO",
    discount=None, phone="", email="", color="", comments="")
check("change_room: camera occupata rifiutata",
      _raises(lambda: reservations.change_room(rid_mv, 103)))
# una prenotazione gia in check-in non si sposta
reservations.checkin_guest(rid_mv, {"first_name": "Spo", "last_name": "Sta"})
check("change_room: checked_in non spostabile",
      _raises(lambda: reservations.change_room(rid_mv, 104)))
check("blocco prenotazioni: flag presente",
      hasattr(mail.config, "block_new_bookings"))

# --- patrimonio: setup, piani e acquisto camere ------------------------------
from hotel import estate
estate.reset_all()                       # azzera tutto -> primo avvio
database._seed_rooms(database.get_conn())  # riseed delle 5 camere iniziali
database.get_conn().commit()

check("estate: setup non fatto all'inizio", not estate.is_setup_done())
estate.complete_setup("Mario", "Grand Hotel")
check("estate: setup completato", estate.is_setup_done())
check("estate: nomi salvati",
      estate.user_name() == "Mario" and estate.hotel_name() == "Grand Hotel")

check("estate: 10 camere iniziali", len(rooms.all_rooms()) == 10)
check("estate: due suite all'avvio",
      sum(r["is_suite"] for r in rooms.all_rooms()) == 2)
check("estate: un solo piano (1)", estate.owned_floors() == [1])
check("estate: costo prima camera 1000", estate.room_cost() == 1000)
check("estate: suite costa il doppio", estate.room_cost(suite=True) == 2000)
# il costo NON deve dipendere dalle camere preesistenti (bug 23 miliardi)
for _n in range(201, 241):
    database.get_conn().execute(
        "INSERT INTO rooms (number, floor, is_suite, max_adults, max_children)"
        " VALUES (?, 2, 0, 2, 1)", (_n,))
database.get_conn().commit()
check("estate: costo indipendente dalle camere nel DB",
      estate.room_cost() == 1000)
database.get_conn().execute("DELETE FROM rooms WHERE number > 110")
database.get_conn().commit()
# incremento +250, poi +500 dopo 10 acquisti
database.kv_set("rooms_purchased", 10)
check("estate: a 10 acquisti costo 3500", estate.room_cost() == 3500)
database.kv_set("rooms_purchased", 12)
check("estate: oltre soglia incremento +500", estate.room_cost() == 4500)
database.kv_set("rooms_purchased", 0)

try:
    estate.buy_room(1)            # budget a 0: niente acquisto
    bought = True
except estate.EstateError:
    bought = False
check("estate: senza saldo non si compra", not bought)

budget.record(budget.INCOME, "Test", 100000)   # bilancio per gli acquisti
n11 = estate.buy_room(1)
check("estate: camera 111 creata sul piano 1",
      n11 == 111 and rooms.get_room(111) is not None)
check("estate: costo sale di 250 dopo l'acquisto", estate.room_cost() == 1250)
ns = estate.buy_room(1, suite=True)
check("estate: suite acquistata", rooms.get_room(ns)["is_suite"] == 1)

f2 = estate.buy_floor()
check("estate: nuovo piano 2", f2 == 2 and 2 in estate.owned_floors())
n201 = estate.buy_room(2)
check("estate: prima camera del piano 2 = 201", n201 == 201)
check("estate: comprare su piano non posseduto fallisce",
      _raises(lambda: estate.buy_room(9)))
check("estate: saldo diminuito dagli acquisti",
      budget.totals()["balance"] < 100000)

# --- dispensa cibo (AllFoods!) -----------------------------------------------
check("cibo: 50 unita al primo avvio", estate.food() == 50)
check("cibo: capienza 100 al primo avvio", estate.food_cap() == 100)
budget.record(budget.INCOME, "TestFood", 10000)   # saldo per gli acquisti
estate.set_food(0)
estate.buy_food(10)
check("cibo: buy_food aggiunge unita", estate.food() == 10)
check("cibo: buy_food oltre la capienza fallisce",
      _raises(lambda: estate.buy_food(1000)))
check("cibo: quantita non valida fallisce",
      _raises(lambda: estate.buy_food(0)))
estate.set_food(2)
check("cibo: consume_food scala le unita",
      estate.consume_food(1) and estate.food() == 1)
check("cibo: consume_food senza scorte non scala",
      not estate.consume_food(5) and estate.food() == 1)
check("cibo: costo potenziamento 2000", estate.food_cap_upgrade_cost() == 2000)
estate.upgrade_food_cap()
check("cibo: potenziamento +50 capienza", estate.food_cap() == 150)
check("cibo: costo potenziamento sale di 0,5x",
      estate.food_cap_upgrade_cost() == 3000)

# consumo pasti: ogni ospite che mangia scala 1 unita; senza cibo -> reclamo
debug_seed.clear_all()
staff.ensure_seed()          # serve personale di sala per la capienza
database._seed_dining(database.get_conn())   # ...e tavoli dopo reset_all
database.get_conn().commit()
rid_food = reservations.create_reservation(
    first_name="Fame", last_name="Affamato", room_number=105, checkin=d(-1),
    checkout=d(2), adults=1, children=0, price_per_night=80, board="BB",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_food, {"first_name": "Fame", "last_name": "Affamato"})
gfood = guests.for_reservation(rid_food)[0]["id"]
t_f = None
for off in range(0, 60):
    day0 = date(2026, 6, 2) + timedelta(days=off)
    s_f, _e = guest_state._meal_slot(gfood, day0, "Colazione")
    cand = s_f + timedelta(minutes=10)
    if guest_state.is_eating(gfood, "BB", "Colazione", cand):
        t_f = cand
        break
check("trovato uno slot colazione valido", t_f is not None)
estate.set_food(0)
check("pasti: senza cibo genera 1 reclamo", reception.serve_meals(t_f) == 1)
check("pasti: reclamo in reception (kind food)",
      any(e["kind"] == "food" for e in reception.pending()))
check("pasti: lo stesso pasto si conta una sola volta",
      reception.serve_meals(t_f) == 0)
# con reclamo in sospeso l'ospite risulta Assente / Reception
frow = guests.for_reservation(rid_food)[0]
d_food = guest_state.describe(frow, t_f)
check("pasti: durante il reclamo -> Assente / Reception",
      d_food["stato"] == "Assente" and d_food["locazione"] == "Reception")
reception.remove([e for e in reception.pending() if e["kind"] == "food"][0]["id"])
check("pasti: dopo le scuse non e piu in reception",
      guest_state.describe(frow, t_f)["locazione"] != "Reception")

t_ok = None
for off2 in range(off + 1, off + 90):
    day1 = date(2026, 6, 2) + timedelta(days=off2)
    s1, _e = guest_state._meal_slot(gfood, day1, "Colazione")
    cand = s1 + timedelta(minutes=10)
    if guest_state.is_eating(gfood, "BB", "Colazione", cand):
        t_ok = cand
        break
estate.set_food(5)
check("pasti: con cibo nessun reclamo", reception.serve_meals(t_ok) == 0)
check("pasti: consuma 1 unita di cibo", estate.food() == 4)

# --- dipendenti: seed, turni, ore, paghe ---------------------------------------
check("staff: seed 1 pulizie + 2 sala",
      staff.headcount(staff.ROLE_CLEANING) == 1
      and staff.headcount(staff.ROLE_DINING) == 2)
check("staff: roster di partenza",
      staff.roster() == {staff.ROLE_CLEANING: 1, staff.ROLE_DINING: 2})

eid = staff.hire(staff.ROLE_CLEANING)
check("staff: assunzione registrata",
      staff.headcount(staff.ROLE_CLEANING) == 2)
clock.set_now(datetime(2026, 8, 1, 10, 0))
staff.set_roster_next(staff.ROLE_CLEANING, 2)
check("staff: modifica turni NON attiva oggi",
      staff.roster()[staff.ROLE_CLEANING] == 1)
clock.set_now(datetime(2026, 8, 2, 10, 0))
check("staff: modifica turni attiva dal giorno dopo",
      staff.roster()[staff.ROLE_CLEANING] == 2)

# paghe: dal 20 del mese, ore x lordo x costo azienda (1.46)
staff.log_hours(eid, date(2026, 8, 3), 4.0)
check("staff: ore non pagate accumulate", staff.unpaid_hours(eid) == 4.0)
check("staff: prima del 20 nessuna paga",
      staff.run_payroll(date(2026, 8, 19)) == 0)
paid = staff.run_payroll(date(2026, 8, 20))
check("staff: paga = 4h x 7 x 1.46", paid == round(4 * 7 * 1.46, 2))
check("staff: niente doppio pagamento nel mese",
      staff.run_payroll(date(2026, 8, 21)) == 0)
check("staff: ore segnate come pagate", staff.unpaid_hours(eid) == 0)

# licenziamento: liquida subito le ore rimaste
staff.log_hours(eid, date(2026, 8, 22), 2.0)
sev = staff.fire(eid)
check("staff: liquidazione al licenziamento", sev == round(2 * 7 * 1.46, 2))
check("staff: licenziato rimosso",
      staff.headcount(staff.ROLE_CLEANING) == 1)
clock.set_now(None)

# --- pulizie simulate ----------------------------------------------------------
debug_seed.clear_all()
rid_hk = reservations.create_reservation(
    first_name="Sta", last_name="Yover", room_number=101, checkin=d(-1),
    checkout=d(2), adults=1, children=0, price_per_night=50, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_hk, {"first_name": "Sta", "last_name": "Yover"})
cln = staff.on_duty(staff.ROLE_CLEANING)[0]["id"]
t0 = datetime.combine(today, time(8, 0))
staff.housekeeping_tick(t0)
check("pulizie: operatore in camera (pallino rosa)",
      staff.cleaner_in_room(101))
staff.housekeeping_tick(t0 + timedelta(minutes=16))   # 0.25h = 15 min
check("pulizie: camera pulita in automatico a fine lavoro",
      rooms.get_room(101)["dirty"] == 0)
check("pulizie: 0.25h accreditate sul foglio ore",
      staff.month_hours(cln, today) == 0.25)
check("pulizie: operatore uscito dalla camera",
      not staff.cleaner_in_room(101))

# check-out: la camera non si pulisce finche l'ospite e dentro
rid_co = reservations.create_reservation(
    first_name="Che", last_name="Ckout", room_number=102, checkin=d(-1),
    checkout=today, adults=1, children=0, price_per_night=50, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_co, {"first_name": "Che", "last_name": "Ckout"})
t1 = datetime.combine(today, time(9, 0))
staff.housekeeping_tick(t1)
check("pulizie: check-out non pulibile con l'ospite dentro",
      not staff.cleaner_in_room(102))
reservations.do_checkout(rid_co)
staff.housekeeping_tick(t1 + timedelta(minutes=1))
check("pulizie: dopo il check-out dell'ospite si pulisce",
      staff.cleaner_in_room(102))
check("pulizie: fuori orario (7-15) nessun nuovo lavoro",
      not staff.housekeeping_tick(datetime.combine(today, time(18, 0)))
      or not staff.cleaner_in_room(102))

# --- sala pasti: piano turni e capienza ------------------------------------------
debug_seed.clear_all()
plan = staff.dining_plan(today)
check("sala: ogni pasto ha almeno un operatore",
      all(len(ids) >= 1 for ids in plan.values()))
n_shifts = defaultdict(int)
for ids in plan.values():
    for i in ids:
        n_shifts[i] += 1
check("sala: max 2 turni a operatore",
      all(n <= staff.DINING_MAX_SHIFTS for n in n_shifts.values()))
check("sala: capienza 24 a operatore",
      staff.dining_capacity("Colazione", today)
      == 24 * len(plan["Colazione"]))

# senza personale di sala -> reclamo 'service' anche con cibo in dispensa
database.kv_set("roster", {staff.ROLE_CLEANING: 1, staff.ROLE_DINING: 0})
rid_srv = reservations.create_reservation(
    first_name="Ser", last_name="Vizio", room_number=103, checkin=d(-1),
    checkout=d(2), adults=1, children=0, price_per_night=80, board="BB",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_srv, {"first_name": "Ser", "last_name": "Vizio"})
gsrv = guests.for_reservation(rid_srv)[0]["id"]
t_s = None
for off in range(0, 90):
    day_s = date(2026, 6, 2) + timedelta(days=off)
    s_s, _e = guest_state._meal_slot(gsrv, day_s, "Colazione")
    cand = s_s + timedelta(minutes=10)
    if guest_state.is_eating(gsrv, "BB", "Colazione", cand):
        t_s = cand
        break
estate.set_food(10)
check("sala: senza operatori il pasto genera reclamo servizio",
      reception.serve_meals(t_s) == 1
      and any(e["kind"] == "service" for e in reception.pending()))
check("sala: il pasto mancato non consuma cibo", estate.food() == 10)
database.kv_set("roster", {staff.ROLE_CLEANING: 1, staff.ROLE_DINING: 2})

# --- sala pasti: tavoli, sedie e layout ------------------------------------------
from hotel import dining
database._seed_dining(database.get_conn())   # riseed dopo estate.reset_all
database.get_conn().commit()
check("tavoli: seed 4 singoli con 4 sedie",
      len(dining.tables()) == 4
      and all(t["kind"] == "single" and t["chairs"] == 4
              for t in dining.tables()))
check("tavoli: conteggi", dining.counts() == {"tavoli": 4, "sedie": 16})

budget.record(budget.INCOME, "TestTavoli", 1000)
bal0 = budget.totals()["balance"]
tid = dining.buy_table("double")
dining.buy_chair()      # va sul tavolo con meno sedie: il doppio nuovo (0)
bal1 = budget.totals()["balance"]
check("tavoli: doppio 100 + sedia 20 addebitati", bal0 - bal1 == 120.0)
t_new = [t for t in dining.tables() if t["id"] == tid][0]
check("tavoli: la sedia va sul tavolo piu scarico", t_new["chairs"] == 1)
check("tavoli: cella libera assegnata (4,0)",
      (t_new["col"], t_new["row"]) == (4, 0))
check("tavoli: tipo sconosciuto rifiutato",
      _raises(lambda: dining.buy_table("triple")))

# sedie: quando tutti i tavoli sono al completo l'acquisto fallisce
database.get_conn().execute(
    "UPDATE dining_tables SET chairs = CASE kind WHEN 'double' THEN 6"
    " ELSE 4 END")
database.get_conn().commit()
check("sedie: tutti i tavoli pieni -> acquisto rifiutato",
      _raises(dining.buy_chair))

# layout: spostamento su cella libera; occupata/fuori griglia rifiutati
dining.move_table(tid, 2, 1)
moved = [t for t in dining.tables() if t["id"] == tid][0]
check("layout: tavolo spostato", (moved["col"], moved["row"]) == (2, 1))
check("layout: cella occupata rifiutata",
      _raises(lambda: dining.move_table(tid, 0, 0)))
check("layout: fuori griglia rifiutato",
      _raises(lambda: dining.move_table(tid, 99, 0)))

# posti: stesso gruppo insieme, gruppi separati, best-fit, senza posto in attesa
tabs = dining.tables()
g_a = [{"room_number": 101}] * 2          # gruppo da 2 (camera 101)
g_b = [{"room_number": 102}] * 6          # gruppo da 6: solo il doppio
g_c = [{"room_number": 103}] * 7          # troppo grande: nessun tavolo
placements, waiting = dining.assign_tables({1: g_a, 2: g_b, 3: g_c}, tabs)
check("posti: ogni gruppo su un tavolo diverso",
      len(placements) == 2
      and {r for r, _m in placements.values()} == {1, 2})
check("posti: il gruppo da 6 va sul tavolo doppio",
      placements.get(tid, (None,))[0] == 2)
check("posti: gruppo senza tavolo in attesa",
      waiting == [(3, g_c)])
check("posti: seating non esplode senza pasto in corso",
      dining.seating(datetime(2026, 1, 1, 17)) == (None, {}, []))

# senza tavolo libero -> reclamo 'table' (e niente cibo consumato)
debug_seed.clear_all()
database.get_conn().execute("DELETE FROM dining_tables")
database.get_conn().commit()
rid_tb = reservations.create_reservation(
    first_name="Ta", last_name="Volo", room_number=104, checkin=d(-1),
    checkout=d(2), adults=1, children=0, price_per_night=80, board="BB",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_tb, {"first_name": "Ta", "last_name": "Volo"})
gtb = guests.for_reservation(rid_tb)[0]["id"]
t_t = None
for off in range(0, 90):
    day_t = date(2026, 6, 2) + timedelta(days=off)
    s_t, _e = guest_state._meal_slot(gtb, day_t, "Colazione")
    cand = s_t + timedelta(minutes=10)
    if guest_state.is_eating(gtb, "BB", "Colazione", cand):
        t_t = cand
        break
estate.set_food(10)
check("posti: senza tavolo il pasto genera reclamo 'table'",
      reception.serve_meals(t_t) == 1
      and any(e["kind"] == "table" for e in reception.pending()))
check("posti: il pasto senza tavolo non consuma cibo", estate.food() == 10)
trow = guests.for_reservation(rid_tb)[0]
check("posti: durante il reclamo tavoli -> Assente / Reception",
      guest_state.describe(trow, t_t)["locazione"] == "Reception")
database._seed_dining(database.get_conn())   # ripristina la sala
database.get_conn().commit()

# --- recensioni e reputazione ---------------------------------------------------
debug_seed.clear_all()
check("recensioni: rating di partenza 3.0 (hotel anonimo)",
      reviews.reputation() == 3.0)
rid_r1 = reservations.create_reservation(
    first_name="Feli", last_name="Cissimo", room_number=101, checkin=d(-2),
    checkout=today, adults=1, children=0, price_per_night=80, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_r1, {"first_name": "Feli", "last_name": "Cissimo"})
reservations.do_checkout(rid_r1)
check("recensioni: senza servizi ne receptionist il felice NON recensisce",
      len(reviews.all_reviews()) == 0)

rid_r2 = reservations.create_reservation(
    first_name="Delu", last_name="So", room_number=102, checkin=d(-2),
    checkout=today, adults=1, children=0, price_per_night=80, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_r2, {"first_name": "Delu", "last_name": "So"})
reception._bump_complaints(rid_r2)
reception._bump_complaints(rid_r2)
reservations.do_checkout(rid_r2)
check("recensioni: 2 reclami -> 1 stella (le negative escono sempre)",
      reviews.all_reviews()[0]["stars"] == 1)
reviews._add("Contrappeso", 5)
check("reputazione: media delle recensioni", reviews.reputation() == 3.0)
check("reputazione: demand_factor da 0.4 a 1.0",
      reviews.demand_factor() == round(0.4 + 0.12 * 3.0, 2))
reviews.leave_angry(reservations.get(rid_r1))
check("recensioni: arrabbiato -> 0 stelle",
      reviews.all_reviews()[0]["stars"] == 0)

# stagionalita: la domanda cambia col mese (x reputazione)
clock.set_now(datetime(2026, 7, 15, 10))
check("stagione: luglio pieno (x1.5)",
      mail.demand_factor()
      == 1.5 * reviews.demand_factor() * amenities.tier_factor())
clock.set_now(datetime(2026, 11, 15, 10))
check("stagione: novembre morto (x0.6)",
      mail.demand_factor()
      == 0.6 * reviews.demand_factor() * amenities.tier_factor())
clock.set_now(None)

# --- usura camere ----------------------------------------------------------------
debug_seed.clear_all()
rid_w = reservations.create_reservation(
    first_name="U", last_name="Sura", room_number=101, checkin=d(-1),
    checkout=today, adults=1, children=0, price_per_night=50, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_w, {"first_name": "U", "last_name": "Sura"})
reservations.do_checkout(rid_w)
check("usura: +1 a ogni check-out", rooms.get_room(101)["wear"] == 1)
database.get_conn().execute("UPDATE rooms SET wear = 10 WHERE number = 102")
database.get_conn().commit()
check("usura: camera logora elencata",
      102 in [r["number"] for r in rooms.worn_rooms()])
rid_w2 = reservations.create_reservation(
    first_name="Scon", last_name="Tento", room_number=102, checkin=d(-1),
    checkout=today, adults=1, children=0, price_per_night=50, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_w2, {"first_name": "Scon", "last_name": "Tento"})
reservations.do_checkout(rid_w2)
check("usura: check-out da camera logora -> 3 stelle",
      reviews.all_reviews()[0]["stars"] == 3)
budget.record(budget.INCOME, "TestRinnovo", 1000)
estate.renovate_room(102)
check("usura: rinnovo azzera l'usura", rooms.get_room(102)["wear"] == 0)
check("usura: rinnovo su camera sana rifiutato",
      _raises(lambda: estate.renovate_room(101)))

# --- bollette --------------------------------------------------------------------
check("bollette: primo mese di gioco gratis",
      estate.run_utilities(date(2026, 9, 1)) == 0.0)
check("bollette: stesso mese non riaddebita",
      estate.run_utilities(date(2026, 9, 15)) == 0.0)
expected_util = round(estate.UTILITY_BASE
                      + estate.UTILITY_PER_ROOM * len(rooms.all_rooms()), 2)
check("bollette: al cambio mese base + quota camere",
      estate.run_utilities(date(2026, 10, 1)) == expected_util)
check("bollette: una sola volta al mese",
      estate.run_utilities(date(2026, 10, 20)) == 0.0)

# --- malattie del personale --------------------------------------------------------
staff.SICK_PROB = 1.0
check("malattia: is_sick deterministico",
      staff.is_sick(1, today) == staff.is_sick(1, today))
check("malattia: i malati non sono in servizio",
      staff.on_duty(staff.ROLE_CLEANING) == [])
staff.SICK_PROB = 0.0
check("malattia: con prob 0 tutti presenti",
      len(staff.on_duty(staff.ROLE_CLEANING))
      == staff.roster()[staff.ROLE_CLEANING])

# --- esperienza (velocita pulizie) --------------------------------------------------
eid_x = staff.hire(staff.ROLE_CLEANING)
check("esperienza: nuovo assunto a velocita base",
      staff.speed_factor(eid_x) == 1.0)
staff.log_hours(eid_x, today, 100.0)
check("esperienza: +5% ogni 50 ore", staff.speed_factor(eid_x) == 1.10)
staff.log_hours(eid_x, today, 10000.0)
check("esperienza: velocita massima x1.5", staff.speed_factor(eid_x) == 1.5)
database.get_conn().execute("DELETE FROM work_hours WHERE employee_id = ?",
                            (eid_x,))
database.get_conn().execute("DELETE FROM employees WHERE id = ?", (eid_x,))
database.get_conn().commit()

# --- room service ------------------------------------------------------------------
debug_seed.clear_all()
rid_rs = reservations.create_reservation(
    first_name="Ordi", last_name="Natore", room_number=101, checkin=d(-1),
    checkout=d(2), adults=1, children=0, price_per_night=80, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_rs, {"first_name": "Ordi", "last_name": "Natore"})
grs = guests.for_reservation(rid_rs)[0]["id"]
hits = []
for off in range(0, 500):
    day_rs = date(2026, 6, 2) + timedelta(days=off)
    r = random.Random(f"rs:{grs}:{day_rs.isoformat()}")
    wants = r.random() < reception.RS_PROB
    hour = r.randint(11, 22)
    when = datetime.combine(day_rs, time(hour, 30))
    if wants and not guest_state._is_asleep(grs, when):
        hits.append(when)
    if len(hits) == 2:
        break
check("room service: trovati ordini deterministici", len(hits) == 2)
estate.set_food(5)
bal_rs = budget.totals()["balance"]
check("room service: ordine servito senza reclami",
      reception.room_service(hits[0]) == 0)
check("room service: consuma 1 cibo e incassa 15",
      estate.food() == 4
      and budget.totals()["balance"] == round(bal_rs + reception.RS_PRICE, 2))
check("room service: al massimo un ordine al giorno",
      reception.room_service(hits[0]) == 0 and estate.food() == 4)
estate.set_food(0)
check("room service: dispensa vuota -> reclamo cibo",
      reception.room_service(hits[1]) == 1
      and any(e["kind"] == "food" for e in reception.pending()))
check("room service: il reclamo pesa sulla recensione",
      reservations.get(rid_rs)["complaints"] == 1)

# --- categoria (tier) e servizi ------------------------------------------------
debug_seed.clear_all()
database.kv_set("amenities", [])
database.kv_set("room_level", 0)
check("tier: si parte da 1 stella", amenities.tier() == 1)
check("tier: fattore domanda 0.85 a 1 stella", amenities.tier_factor() == 0.85)
budget.record(budget.INCOME, "TestTier", 500000)

check("servizi: sconosciuto rifiutato",
      _raises(lambda: amenities.buy("sauna")))
amenities.buy("wifi")
check("servizi: wifi posseduto", "wifi" in amenities.owned())
check("servizi: doppio acquisto rifiutato",
      _raises(lambda: amenities.buy("wifi")))
check("tier: 12+ camere e wifi -> 2 stelle",
      len(rooms.all_rooms()) >= 12 and amenities.tier() == 2)

amenities.buy("snackbar")
amenities.buy("lobby")
_n = 301
while len(rooms.all_rooms()) < 16:      # camere extra per la 3a stella
    database.get_conn().execute(
        "INSERT INTO rooms (number, floor, is_suite, max_adults, max_children)"
        " VALUES (?, 3, 0, 2, 1)", (_n,))
    _n += 1
database.get_conn().commit()
check("tier: 16 camere + ristoro + reception -> 3 stelle",
      amenities.tier() == 3)

check("upgrade: luxury prima di migliorate rifiutato",
      _raises(lambda: amenities.buy_room_upgrade(2)))
amenities.buy("pool")
amenities.buy("meeting")
check("upgrade: costo scala con le camere",
      amenities.room_upgrade_cost(1) == round(350.0 * len(rooms.all_rooms()), 2))
amenities.buy_room_upgrade(1)
check("upgrade: camere migliorate -> prezzi x1.5",
      amenities.price_mult() == 1.5)
while len(rooms.all_rooms()) < 22:
    database.get_conn().execute(
        "INSERT INTO rooms (number, floor, is_suite, max_adults, max_children)"
        " VALUES (?, 3, 0, 2, 1)", (_n,))
    _n += 1
database.get_conn().commit()
check("tier: 22 camere + piscina + riunioni + migliorate -> 4 stelle",
      amenities.tier() == 4)

amenities.buy("casino")
amenities.buy("redlight")
amenities.buy_room_upgrade(2)
while len(rooms.all_rooms()) < 30:
    database.get_conn().execute(
        "INSERT INTO rooms (number, floor, is_suite, max_adults, max_children)"
        " VALUES (?, 3, 0, 2, 1)", (_n,))
    _n += 1
database.get_conn().commit()
check("tier: 30 camere + casino + luxury -> 5 stelle", amenities.tier() == 5)
check("tier: fattore domanda 1.45 a 5 stelle", amenities.tier_factor() == 1.45)
check("tier: a 5 stelle niente obiettivi", amenities.missing_for_next() == [])

# il livello camere muove i costi di costruzione e i prezzi delle mail
database.kv_set("rooms_purchased", 0)
check("upgrade: costo camera 1000 x2.5 con luxury", estate.room_cost() == 2500.0)
mail.config.auto_insert = False
mid_lux = mail.spawn()
m_lux = mail.get(mid_lux)
room_lux = mail.insert(mid_lux)
res_lux = reservations.arrival_on(room_lux,
                                  date.fromisoformat(m_lux["checkin"]))
check("upgrade: prezzo per notte delle mail x2.5",
      res_lux["price_per_night"]
      == round(debug_seed.DEFAULT_BOARD_PRICES[m_lux["board"]] * 2.5, 2))

# recensioni positive SOLO se citano servizi (o receptionist)
for _i in range(40):
    reviews.leave_checkout(f"Recensore{_i}", 5)
themed = {txt for pair in amenities.REVIEW_TEXTS.values() for txt in pair}
posted = [r for r in reviews.all_reviews(100) if r["stars"] == 5]
check("recensioni: qualche positiva esce citando i servizi",
      0 < len(posted) < 40)
check("recensioni: tutte le positive citano un servizio",
      all(r["text"] in themed for r in posted))

# entrate passive: casino di giorno, + luci rosse di notte
rid_pa = reservations.create_reservation(
    first_name="Gioca", last_name="Tore", room_number=101, checkin=d(-1),
    checkout=d(2), adults=1, children=0, price_per_night=80, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_pa, {"first_name": "Gioca", "last_name": "Tore"})
database.kv_set("passive_last", None)
check("passivo: casino di giorno (2 a ospite/ora)",
      amenities.accrue_passive(datetime(2026, 7, 10, 15, 0)) == 2.0)
check("passivo: stessa ora non rimatura",
      amenities.accrue_passive(datetime(2026, 7, 10, 15, 40)) == 0.0)
check("passivo: di notte casino + luci rosse (2+4)",
      amenities.accrue_passive(datetime(2026, 7, 10, 23, 30)) == 6.0)
debug_seed.clear_all()
database.kv_set("passive_last", None)
check("passivo: senza ospiti nessun incasso",
      amenities.accrue_passive(datetime(2026, 7, 11, 15, 0)) == 0.0)

# --- receptionist: candidature, contratti, turni ------------------------------------
debug_seed.clear_all()
database.kv_set("rec_schedule", {})
database.kv_set("cand_taken", [])
database.kv_set("rec_logged", None)
budget.record(budget.INCOME, "TestRec", 100000)

c1 = staff.candidates()
check("rec: 3 candidature a settimana", len(c1) == 3)
check("rec: candidature stabili nella settimana",
      [c["key"] for c in staff.candidates()] == [c["key"] for c in c1])
check("rec: 4 scelte stabili al primo avvio",
      staff.first_candidates() == staff.first_candidates()
      and len(staff.first_candidates()) == 4)

rec1 = staff.hire_candidate(c1[0]["key"], "part")
check("rec: part-time assunto a 7/h",
      staff.get(rec1)["contract"] == "part"
      and staff.get(rec1)["hourly"] == 7.0)
check("rec: candidatura consumata",
      all(c["key"] != c1[0]["key"] for c in staff.candidates()))
check("rec: contratto in prova (non indeterminato)",
      staff.get(rec1)["permanent"] == 0)
rec2 = staff.hire_receptionist("Neri", "Nero", "brutto_muso", "nero")
check("rec: in nero pagato 9/h flat", staff.get(rec2)["hourly"] == 9.0)

# turni: oggi bloccato, limiti orari e giorni del contratto
today_wd = clock.today().weekday()
days = [dd for dd in range(7) if dd != today_wd]
check("rec: il giorno corrente non si tocca",
      _raises(lambda: staff.set_shift(rec1, today_wd, "7-11")))
staff.set_shift(rec1, days[0], "7-11")
check("rec: turno salvato",
      staff.schedule()[str(rec1)][str(days[0])] == "7-11")
check("rec: blocco 8h vietato al part-time",
      _raises(lambda: staff.set_shift(rec1, days[1], "7-15")))
for dd in days[1:5]:
    staff.set_shift(rec1, dd, "7-11")
check("rec: oltre le 20h/settimana vietato",
      _raises(lambda: staff.set_shift(rec1, days[5], "7-11")))
staff.set_shift(rec2, days[0], "7-15")
staff.set_shift(rec2, days[1], "15-23")
check("rec: in nero massimo 2 giorni",
      _raises(lambda: staff.set_shift(rec2, days[2], "7-15")))

# di turno adesso? (incluso il turno a cavallo della mezzanotte)
day0 = today + timedelta(days=(days[0] - today_wd) % 7)
day1 = today + timedelta(days=(days[1] - today_wd) % 7)
t_rec = datetime.combine(day0, time(8, 0))
check("rec: di turno alle 8", any(
    e["id"] == rec1 for e in staff.on_duty_receptionists(t_rec)))
check("rec: bonus di turno rilevato",
      staff.on_duty_bonus("brutto_muso", t_rec))
check("rec: alle 5 nessuno al banco",
      staff.on_duty_receptionists(datetime.combine(day0, time(5, 0))) == [])
rec3 = staff.hire_receptionist("Not", "Turno", "animale_notturno", "full")
staff.set_shift(rec3, days[1], "23-7")
check("rec: turno notturno prima di mezzanotte",
      staff._shift_at(rec3, datetime.combine(day1, time(23, 30))) == "23-7")
after_mid = datetime.combine(day1 + timedelta(days=1), time(3, 0))
check("rec: turno notturno dopo mezzanotte", staff._shift_at(rec3, after_mid))
check("rec: animale notturno x3 mail di notte",
      staff.mail_boost(after_mid) == 3.0)

# ore: accreditate una volta a turno; insonne paga meta di notte
staff.reception_tick(t_rec)
check("rec: ore del turno accreditate (part 4h)",
      staff.unpaid_hours(rec1) == 4.0)
staff.reception_tick(t_rec + timedelta(hours=1))
check("rec: nessun doppio accredito", staff.unpaid_hours(rec1) == 4.0)
rec4 = staff.hire_receptionist("In", "Sonne", "insonne", "part")
staff.set_shift(rec4, days[1], "23-3")
staff.reception_tick(datetime.combine(day1, time(23, 30)))
check("rec: insonne, ore notturne a meta", staff.unpaid_hours(rec4) == 2.0)
# sfruttabile: puo superare il limite ma l'extra non si paga
rec5 = staff.hire_receptionist("Sfru", "Ttato", "sfruttabile", "full")
for dd in days:      # 6 turni da 8h = 48h <= 40+8
    staff.set_shift(rec5, dd, "7-15")
check("rec: sfruttabile pianifica 48h", True)
staff.log_hours(rec5, day0, 40.0)      # limite base gia raggiunto
staff.reception_tick(t_rec + timedelta(minutes=5))
check("rec: le ore extra dello sfruttabile sono gratis",
      staff.unpaid_hours(rec5) == 40.0)

# fine contratto: deterministico, o se ne va o diventa indeterminato
database.get_conn().execute(
    "UPDATE employees SET contract_until = ? WHERE id IN (?, ?)",
    (d(-1).isoformat(), rec1, rec2))
database.get_conn().commit()
expected_quit = {e for e in (rec1, rec2)
                 if random.Random(f"quit:{e}").random() < staff.QUIT_PROB}
staff.contracts_tick(today)
ok_contract = all(
    (staff.get(e) is None) == (e in expected_quit)
    and (e in expected_quit or staff.get(e)["permanent"] == 1)
    for e in (rec1, rec2))
check("rec: a fine prova se ne va o diventa indeterminato", ok_contract)

# --- bonus al check-out --------------------------------------------------------------
def _co_res(room):
    rid = reservations.create_reservation(
        first_name="Pay", last_name=f"Er{room}", room_number=room,
        checkin=d(-2), checkout=today, adults=1, children=0,
        price_per_night=100, board="RO", discount=None, phone="", email="",
        color="", comments="")
    reservations.checkin_guest(rid, {"first_name": "Pay",
                                     "last_name": f"Er{room}"})
    return rid

def _last_stay_income():
    rows = [e for e in budget.entries()
            if e["kind"] == "income" and e["category"] == "Soggiorno"]
    return rows[-1]["amount"]

# conto base: 2 notti x 100 = 200 + IVA 44 = 244 (si incassa il totale)
reservations.do_checkout(_co_res(101), receptionist={"bonus": "persuasore"})
check("bonus: persuasore incassa 1.25x", _last_stay_income() == 305.0)
reservations.do_checkout(_co_res(102), receptionist={"bonus": "truffatore"})
check("bonus: truffatore incassa 1.5x", _last_stay_income() == 366.0)
check("bonus: truffatore -> recensione negativa",
      reviews.all_reviews()[0]["stars"] <= 2
      and reviews.all_reviews()[0]["text"] in reviews.REC_NEGATIVE)
reservations.do_checkout(_co_res(103), receptionist={"bonus": "pappamolle"})
check("bonus: pappamolle incassa 0.75x", _last_stay_income() == 183.0)
check("bonus: pappamolle -> recensione positiva",
      reviews.all_reviews()[0]["stars"] >= 4
      and reviews.all_reviews()[0]["text"] in reviews.REC_POSITIVE)

# misterioso: una notte in meno, prezzo pieno
rid_my = reservations.create_reservation(
    first_name="Mis", last_name="Tero", room_number=104, checkin=today,
    checkout=d(3), adults=1, children=0, price_per_night=90, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.shorten_stay(rid_my)
res_my = reservations.get(rid_my)
check("bonus ???: una notte in meno",
      res_my["checkout_date"] == d(2).isoformat())
check("bonus ???: totale invariato (prezzo/notte ricalibrato)",
      res_my["price_per_night"] == 135.0)

# calmo: nessuna arrabbiatura durante il suo turno
rec6 = staff.hire_receptionist("Cal", "Mo", "calmo", "full")
staff.set_shift(rec6, days[0], "15-23")
t_calm = datetime.combine(day0, time(17, 0))
rid_cal = reservations.create_reservation(
    first_name="Pa", last_name="Ziente", room_number=105, checkin=day0,
    checkout=day0 + timedelta(days=2), adults=1, children=0,
    price_per_night=50, board="RO", discount=None, phone="", email="",
    color="", comments="")
reception._spawn_checkin(reservations.get(rid_cal),
                         datetime.combine(day0, time(15, 0)))
check("bonus calmo: nessuno si arrabbia nel suo turno",
      reception.handle_anger(t_calm) == 0)
staff.set_shift(rec6, days[0], None)
check("bonus calmo: senza di lui la rabbia torna",
      reception.handle_anger(t_calm) == 1)

# brutto muso: gli overstayer pagano
rec7 = staff.hire_receptionist("Brut", "To", "brutto_muso", "full")
staff.set_shift(rec7, days[0], "7-15")
rid_ov2 = reservations.create_reservation(
    first_name="Fuggi", last_name="Tivo", room_number=106,
    checkin=day0 - timedelta(days=2), checkout=day0, adults=1, children=0,
    price_per_night=80, board="RO", discount=None, phone="", email="",
    color="", comments="")
reservations.checkin_guest(rid_ov2, {"first_name": "Fuggi",
                                     "last_name": "Tivo"})
reservations.auto_checkout_overstayers(datetime.combine(day0, time(14, 45)))
check("bonus brutto muso: l'overstayer paga il conto",
      _last_stay_income() > 0)

# barista: consumazioni al bar nel suo turno
rec8 = staff.hire_receptionist("Ba", "Rista", "barista", "full")
staff.set_shift(rec8, days[1], "7-15")
rid_bar = reservations.create_reservation(
    first_name="Beo", last_name="Ne", room_number=107, checkin=d(-1),
    checkout=d(30), adults=1, children=0, price_per_night=50, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_bar, {"first_name": "Beo", "last_name": "Ne"})
gbar = guests.for_reservation(rid_bar)[0]["id"]
t_bar = None
for k in range(60):     # cerca un giorno del turno con la voglia di bar
    day_b = day1 + timedelta(days=7 * k)
    r = random.Random(f"bar:{gbar}:{day_b.isoformat()}")
    wants = r.random() < 0.4
    hour = r.randint(8, 22)
    when = datetime.combine(day_b, time(hour, 30))
    if wants and 7 <= hour < 15 and not guest_state._is_asleep(gbar, when):
        t_bar = when
        break
check("bonus barista: trovata una consumazione", t_bar is not None)
earned = reception.bar_tick(t_bar)
check("bonus barista: incasso 5-10", 5 <= earned <= 10)
check("bonus barista: una sola volta al giorno",
      reception.bar_tick(t_bar) == 0.0)

# contabile: bollette -20%
rec9 = staff.hire_receptionist("Con", "Tabile", "contabile", "part")
database.kv_set("last_utilities", "2026-11")
exp_util = round((estate.UTILITY_BASE
                  + estate.UTILITY_PER_ROOM * len(rooms.all_rooms())) * 0.8, 2)
check("bonus contabile: bollette scontate del 20%",
      estate.run_utilities(date(2026, 12, 1)) == exp_util)

# --- banca: prestiti con interessi -------------------------------------------------
database.kv_set("loans", [])
bal_bank = budget.totals()["balance"]
check("banca: importo sconosciuto rifiutato",
      _raises(lambda: bank.take_loan(7777)))
bank.take_loan(5000)
check("banca: capitale accreditato subito",
      budget.totals()["balance"] == round(bal_bank + 5000, 2))
check("banca: debito = capitale + interessi (5% TAN)",
      bank.total_debt() == 5250.0)
check("banca: rata mensile = totale / 12",
      bank.monthly_due() == round(5250 / 12, 2))
bank.take_loan(15000)
bank.take_loan(40000)
check("banca: massimo 3 prestiti aperti",
      _raises(lambda: bank.take_loan(5000)))
debt_before = bank.total_debt()
paid_rate = bank.pay_due(today)
check("banca: la rata riduce il debito",
      paid_rate == round(5250 / 12 + 16200 / 12 + 44800 / 12, 2)
      and bank.total_debt() == round(debt_before - paid_rate, 2))

# --- tasse di fine mese: IVA accantonata + rate ------------------------------------
database.kv_set("loans", [])
bank.take_loan(5000)
database.kv_set("vat_due", 100.0)
database.kv_set("last_taxes", None)
check("tasse: il mese di avvio registra e basta",
      taxes.settle(date(2026, 9, 10)) == 0.0)
check("tasse: stesso mese niente addebiti",
      taxes.settle(date(2026, 9, 25)) == 0.0)
tot_tax = taxes.settle(date(2026, 10, 1))
check("tasse: al cambio mese IVA + rata prestito",
      tot_tax == round(100.0 + 5250 / 12, 2))
check("tasse: IVA azzerata dopo il versamento", taxes.vat_due() == 0.0)
check("tasse: una sola volta al mese",
      taxes.settle(date(2026, 10, 20)) == 0.0)
database.kv_set("loans", [])

# --- capitale iniziale e prezzo di mercato -----------------------------------------
database.kv_set("capital_granted", None)
bal_cap = budget.totals()["balance"]
estate.grant_starting_capital()
check("capitale: 10000 al primo avvio",
      budget.totals()["balance"] == round(bal_cap + 10000, 2))
estate.grant_starting_capital()
check("capitale: una tantum, non si ripete",
      budget.totals()["balance"] == round(bal_cap + 10000, 2))

database.kv_set("room_level", 0)
check("prezzo di mercato: listino base", reservations.price_for("BB") == 85.0)
database.kv_set("room_level", 2)
check("prezzo di mercato: segue gli upgrade (x2.5)",
      reservations.price_for("BB") == 212.5)
database.kv_set("room_level", 0)

# --- problemi: To Do, racconti in reception, emozioni --------------------------
debug_seed.clear_all()
database.get_conn().execute("DELETE FROM employees WHERE role = 'reception'")
database.get_conn().commit()
database.kv_set("rec_schedule", {})
database.kv_set("amenities", [])
database.kv_set("tuttofare_done", None)

check("problemi: catalogo ricco (>= 13 voci)", len(problems.PROBLEMS) >= 13)
elig = problems._eligible_keys()
check("problemi: senza piscina niente guai in piscina",
      "cacca_piscina" not in elig and "lampadina" in elig)
database.kv_set("amenities", ["pool"])
check("problemi: con la piscina i guai arrivano",
      "cacca_piscina" in problems._eligible_keys())
database.kv_set("amenities", [])

rid_pb = reservations.create_reservation(
    first_name="Guaio", last_name="Fortuna", room_number=101, checkin=d(-1),
    checkout=d(3), adults=1, children=0, price_per_night=80, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_pb, {"first_name": "Guaio",
                                    "last_name": "Fortuna"})
pid = problems.spawn("lampadina", clock.now(), room_number=101)
check("problemi: aperto nel To Do",
      any(p["id"] == pid and p["resolved_at"] is None
          for p in problems.todo_list()))
prow = [e for e in reception.pending() if e["kind"] == "problem"][0]
check("problemi: l'ospite scende a raccontarlo", "Lampadina" in prow["note"])
grow_pb = guests.for_reservation(rid_pb)[0]
check("problemi: mentre racconta e Assente/Reception",
      guest_state.describe(grow_pb, clock.now())["locazione"] == "Reception")
reception.remove(prow["id"])          # "scusati": la riga sparisce
check("problemi: dopo le scuse resta aperto",
      problems.get(pid)["resolved_at"] is None)
check("problemi: emozione assegnata agli ospiti della camera",
      problems.emotion_for_room(101) == "Ansia"
      and guest_state.describe(grow_pb, clock.now())["emozione"] == "Ansia")

budget.record(budget.INCOME, "TestProblemi", 1000)
bal_pb = budget.totals()["balance"]
problems.resolve(pid)
check("problemi: riparazione pagata (20)",
      budget.totals()["balance"] == round(bal_pb - 20, 2))
check("problemi: risolto e barrato",
      problems.get(pid)["resolved_at"] is not None)
check("problemi: doppia risoluzione rifiutata",
      _raises(lambda: problems.resolve(pid)))
check("problemi: emozione svanita col problema",
      problems.emotion_for_room(101) is None)

pid2 = problems.spawn("scarafaggio", clock.now(), room_number=101)
cln_pb = [e for e in staff.all_employees()
          if e["role"] == staff.ROLE_CLEANING][0]["id"]
h_pb = staff.month_hours(cln_pb, today)
problems.resolve(pid2, operator_id=cln_pb)
check("problemi: la pulizia va sul foglio ore (+0.5h)",
      staff.month_hours(cln_pb, today) == h_pb + 0.5)
pid3 = problems.spawn("puzza", clock.now(), room_number=101)
check("problemi: pulizia senza operatore rifiutata",
      _raises(lambda: problems.resolve(pid3)))
problems.resolve(pid3, operator_id=cln_pb)

# i risolti barrati spariscono dopo 7 giorni di gioco
database.get_conn().execute(
    "UPDATE problems SET resolved_at = ? WHERE id = ?",
    ((clock.now() - timedelta(days=8)).isoformat(), pid))
database.get_conn().commit()
problems.purge(clock.now())
ids_now = {p["id"] for p in problems.todo_list()}
check("problemi: i barrati spariscono dopo 7 giorni",
      pid not in ids_now and pid2 in ids_now)

# spawn orario: una sola possibilita per ora di gioco
database.kv_set("problems_hour", None)
problems.rng.seed(1)
_old_prob = problems.PROB_PER_HOUR
problems.PROB_PER_HOUR = 1.0
t_sp = datetime(2026, 7, 20, 10, 0)
check("problemi: nascita oraria", problems.maybe_spawn(t_sp) is True)
check("problemi: una sola chance per ora",
      problems.maybe_spawn(t_sp) is False)
problems.PROB_PER_HOUR = _old_prob
database.get_conn().execute("DELETE FROM problems")
database.get_conn().commit()

# recensione dell'emozione al check-out (dado deterministico)
problems.spawn("lampadina", clock.now(), room_number=101)
emo_exp = random.Random(f"co:{rid_pb}").random() < problems.EMOTION_REVIEW_PROB
reservations.do_checkout(rid_pb)
target = reviews.EMOTION_NEG.format(emo="ansia")
found = any(r["text"] == target for r in reviews.all_reviews(20))
check("problemi: recensione dell'emozione secondo il dado", found == emo_exp)

# --- nuovi bonus receptionist -------------------------------------------------------
check("rec: i 5 nuovi bonus esistono",
      all(b in staff.BONUSES for b in
          ("autonomo", "cucciolo", "cashback", "stagista", "tuttofare")))

sid = staff.hire_receptionist("Sta", "Gista", "stagista", "full")
e_st = staff.get(sid)
check("stagista: part-time forzato e paga zero",
      e_st["contract"] == "part" and e_st["hourly"] == 0.0)
check("stagista: contratto di un solo mese",
      e_st["contract_until"] == (today + timedelta(days=30)).isoformat())
database.get_conn().execute(
    "UPDATE employees SET contract_until = ? WHERE id = ?",
    (d(-1).isoformat(), sid))
database.get_conn().commit()
staff.contracts_tick(today)
check("stagista: a fine stage va sempre via", staff.get(sid) is None)

aid = staff.hire_receptionist("Auto", "Nomo", "autonomo", "full")
staff.set_shift(aid, days[0], "7-15")
t_auto = datetime.combine(day0, time(8, 0))
rid_ci2 = reservations.create_reservation(
    first_name="Arri", last_name="Vante", room_number=102, checkin=day0,
    checkout=day0 + timedelta(days=2), adults=1, children=0,
    price_per_night=50, board="RO", discount=None, phone="", email="",
    color="", comments="")
reception._spawn_checkin(reservations.get(rid_ci2), t_auto)
rid_co3 = reservations.create_reservation(
    first_name="Par", last_name="Tente", room_number=103,
    checkin=day0 - timedelta(days=2), checkout=day0, adults=1, children=0,
    price_per_night=50, board="RO", discount=None, phone="", email="",
    color="", comments="")
reservations.checkin_guest(rid_co3, {"first_name": "Par",
                                     "last_name": "Tente"})
reception._spawn_checkout(reservations.get(rid_co3), t_auto)
n_auto = reception.auto_desk(t_auto)
check("autonomo: sportello svuotato da solo",
      n_auto >= 2 and all(e["kind"] not in ("checkin", "checkout")
                          for e in reception.pending()))
check("autonomo: check-in registrato",
      reservations.get(rid_ci2)["status"] == "checked_in")
check("autonomo: check-out incassato",
      reservations.get(rid_co3)["status"] == "checked_out")
check("autonomo: fuori turno non tocca nulla",
      reception.auto_desk(datetime.combine(day0, time(20, 0))) == 0)

# cucciolo: la recensione negativa sparisce (e a volte si ribalta)
rid_cu = reservations.create_reservation(
    first_name="Morbi", last_name="Doso", room_number=104, checkin=d(-2),
    checkout=today, adults=1, children=0, price_per_night=100, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_cu, {"first_name": "Morbi",
                                    "last_name": "Doso"})
reception._bump_complaints(rid_cu)      # 1 reclamo -> 3 stelle (negativa)
rr = random.Random(f"co:{rid_cu}")
a_cu, b_cu = rr.random(), rr.random()
n_rev = len(reviews.all_reviews(200))
reservations.do_checkout(rid_cu, receptionist={"bonus": "cucciolo"})
after_cu = reviews.all_reviews(200)
if a_cu < 0.5 and b_cu < 0.5:
    ok_cu = (len(after_cu) == n_rev + 1 and after_cu[0]["stars"] >= 4
             and after_cu[0]["text"] in reviews.REC_POSITIVE)
elif a_cu < 0.5:
    ok_cu = len(after_cu) == n_rev
else:
    ok_cu = len(after_cu) == n_rev + 1 and after_cu[0]["stars"] == 3
check("cucciolo: negativa sparita o ribaltata (secondo il dado)", ok_cu)

# cashback: 10% delle spese del turno a fine turno
cbid = staff.hire_receptionist("Cash", "Back", "cashback", "full")
staff.set_shift(cbid, days[1], "7-15")
database.kv_set("cashback_snap", {})
staff._cashback_tick(datetime.combine(day1, time(8, 0)))    # snapshot
budget.record(budget.LOSS, "TestSpesa", 200)
staff._cashback_tick(datetime.combine(day1, time(16, 0)))   # fine turno
cb_rows = [e for e in budget.entries() if e["category"] == "Cashback"]
check("cashback: rimborso del 10% a fine turno",
      bool(cb_rows) and cb_rows[-1]["amount"] == 20.0)

# tuttofare: una riparazione gratis al giorno nel suo turno
tid = staff.hire_receptionist("Tutto", "Fare", "tuttofare", "full")
staff.set_shift(tid, days[0], "7-15")
rid_tf = reservations.create_reservation(
    first_name="Ospi", last_name="Te", room_number=105, checkin=d(-1),
    checkout=d(3), adults=1, children=0, price_per_night=50, board="RO",
    discount=None, phone="", email="", color="", comments="")
reservations.checkin_guest(rid_tf, {"first_name": "Ospi", "last_name": "Te"})
problems.spawn("tv", clock.now(), room_number=105)
database.kv_set("tuttofare_done", None)
first_open = problems.open_problems()[0]["id"]
bal_tf = budget.totals()["balance"]
check("tuttofare: ripara gratis nel suo turno",
      problems.autofix(datetime.combine(day0, time(9, 0))) is True
      and problems.get(first_open)["resolved_at"] is not None
      and budget.totals()["balance"] == bal_tf)
problems.spawn("materasso", clock.now(), room_number=105)
check("tuttofare: una sola riparazione al giorno",
      problems.autofix(datetime.combine(day0, time(10, 0))) is False)

print()
if failures:
    print(f"{len(failures)} TEST FALLITI: {failures}")
    sys.exit(1)
print("Tutti i test sono passati.")
