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
  Bianco = libera, verde o colore custom = occupata, linea grigia = sporca,
  linea rossa = bloccata, "S" = suite. Indicatori sul lato destro della
  cella: striscia gialla = camera occupata in check-out oggi; quadrato
  fucsia in alto = arrivo (prenotazione) previsto oggi; quadrato blu in
  basso = arrivo previsto domani. Gli indicatori possono coesistere (es.
  check-out oggi con nuovo arrivo lo stesso giorno).
  Click su una camera per aprire la scheda con le azioni: check-in,
  conto/check-out, segna pulita/sporca, blocca/sblocca.
- **Timeline**: barre delle prenotazioni per camera su circa un mese.
- **Nuova prenotazione**: date e numero di notti si sincronizzano tra loro;
  la tendina camere mostra solo quelle libere nel periodo (mai le bloccate);
  superare la capienza genera un avviso ma non blocca.
- **Fogli** (pulizie, colazione, pranzo, cena): generati per qualsiasi data
  e salvabili come file di testo.
- **Debug** (pulsante in alto a destra): genera in blocco prenotazioni di
  prova per popolare velocemente il programma. Si imposta il numero di
  prenotazioni, l'intervallo di date dei check-in, le notti minime e massime
  (durata casuale in quel range) e il prezzo per notte di ogni soluzione.
  Ogni campo della prenotazione viene riempito (nome casuale, telefono,
  email, sconto, commenti, colore). Opzioni: colori casuali e check-in
  automatico dei soggiorni attivi oggi. Include anche "Svuota database" per
  ripartire da zero e un campo "Data attuale" per simulare un giorno diverso
  (sposta l'oggi di tutto il programma finche l'app resta aperta, utile per
  vedere arrivi e check-out cambiare sulla dashboard).

## Struttura

```
main.py            punto di ingresso
hotel/             logica di dominio e dati (nessun riferimento alla GUI)
  constants.py     piani, capienze, soluzioni (BB/RO/HB/FB/RES), IVA, ore pulizie
  clock.py         data odierna con override per la simulazione (debug)
  database.py      schema SQLite e popolamento camere
  rooms.py         stato camere (pulizia, blocco)
  reservations.py  prenotazioni, disponibilita, check-in/out
  guests.py        anagrafica ospiti abituali
  billing.py       conto con sconto e IVA 22%
  cleaning.py      foglio ore pulizie e bilanciamento operatori
  meals.py         fogli colazione/pranzo/cena
  names.py         librerie di nomi, cognomi e citta per i dati di prova
  debug_seed.py    generazione di prenotazioni casuali (tool di debug)
gui/               interfaccia tkinter (una finestra per modulo)
  debug_tool.py    finestra dello strumento di debug
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
