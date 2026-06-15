# HotelAurora

Gestionale per hotel da 81 camere: prenotazioni, check-in, check-out, conti,
fogli pulizie e fogli pasti. Interfaccia tkinter, dati su SQLite.
Nessuna dipendenza esterna: basta Python 3 (testato con 3.14).

## Avvio

Doppio click su `Avvia_HotelAurora.bat`, oppure da terminale:

```
cd C:\Users\matteo.piana\Desktop\GestionaleHotel
python main.py
```

Al primo avvio viene creato `hotel.db` con le 81 camere
(piani 1-3, camere 01-27; le 23-27 di ogni piano sono suite).

## Uso

- **Camere** (pagina principale): un rettangolo per camera.
  Bianco = libera, verde o colore custom = occupata, giallo = check-out oggi,
  linea grigia = sporca, linea rossa = bloccata, "S" = suite.
  Click su una camera per aprire la scheda con le azioni: check-in,
  conto/check-out, segna pulita/sporca, blocca/sblocca.
- **Timeline**: barre delle prenotazioni per camera su circa un mese.
- **Nuova prenotazione**: date e numero di notti si sincronizzano tra loro;
  la tendina camere mostra solo quelle libere nel periodo (mai le bloccate);
  superare la capienza genera un avviso ma non blocca.
- **Fogli** (pulizie, colazione, pranzo, cena): generati per qualsiasi data
  e salvabili come file di testo.

## Struttura

```
main.py            punto di ingresso
hotel/             logica di dominio e dati (nessun riferimento alla GUI)
  constants.py     piani, capienze, soluzioni (BB/RO/HB/FB/RES), IVA, ore pulizie
  database.py      schema SQLite e popolamento camere
  rooms.py         stato camere (pulizia, blocco)
  reservations.py  prenotazioni, disponibilita, check-in/out
  guests.py        anagrafica ospiti abituali
  billing.py       conto con sconto e IVA 22%
  cleaning.py      foglio ore pulizie e bilanciamento operatori
  meals.py         fogli colazione/pranzo/cena
gui/               interfaccia tkinter (una finestra per modulo)
smoke_test.py      test di regressione della logica (python smoke_test.py)
```

## Regole principali

- Disponibilita su intervallo [check-in, check-out): il giorno del check-out
  la camera e prenotabile da un nuovo arrivo.
- Il check-in richiede almeno un ospite con nome e cognome e marca la camera
  occupata e sporca; lo stato "sporca" resta finche non viene tolto a mano.
- Conto: una riga per notte (soluzione, data, prezzo), sconto opzionale,
  totale + IVA 22%.
- Pulizie: 0.5h al check-out, 0.25h in rimanenza; suite RES solo il venerdi
  (1h) e 3h al check-out. Operatori max 8h, carichi bilanciati.
# Gestionale-HotelAurora
