"""Test di verifica della logica di HotelAurora (usa un DB temporaneo)."""

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# DB temporaneo, per non toccare hotel.db
from hotel import database
database.DB_PATH = Path(tempfile.gettempdir()) / "hotel_aurora_smoke.db"
if database.DB_PATH.exists():
    os.remove(database.DB_PATH)

from hotel import billing, cleaning, constants, guests, meals, reservations, rooms

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

print()
if failures:
    print(f"{len(failures)} TEST FALLITI: {failures}")
    sys.exit(1)
print("Tutti i test sono passati.")
