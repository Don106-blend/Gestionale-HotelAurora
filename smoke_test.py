"""Test di verifica della logica di HotelAurora (usa un DB temporaneo)."""

import os
import random
import sys
import tempfile
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# DB temporaneo, per non toccare hotel.db
from hotel import database
database.DB_PATH = Path(tempfile.gettempdir()) / "hotel_aurora_smoke.db"
if database.DB_PATH.exists():
    os.remove(database.DB_PATH)

from hotel import (billing, budget, cleaning, clock, constants, debug_seed,
                   guests, mail, meals, reservations, rooms)

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
      reservations.current_for_room(101, today) is not None)

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
      reservations.current_for_room(101, today) is None)
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
res_room = reservations.current_for_room(room, date.fromisoformat(m["checkin"]))
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

print()
if failures:
    print(f"{len(failures)} TEST FALLITI: {failures}")
    sys.exit(1)
print("Tutti i test sono passati.")
