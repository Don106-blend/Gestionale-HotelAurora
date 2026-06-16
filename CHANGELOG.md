## 2026-06-16

### Aggiunto

- **Controllo velocita (chiude la fase 1 di gameplay)** — bottoni in basso a
  destra: Pausa, Play, T (tempo reale), 1x, 2x, 5x. Sono un moltiplicatore
  live (`clock.speed`/`realtime`/`paused`) SOPRA le basi del debug (scale 24,
  mail prob 0.5): non le modificano, niente feedback loop. Tutte le frequenze
  (avanzamento tempo, mail, reception) leggono `clock.freq_factor()`.

- **Reception (check-in/check-out come gameplay)** — `hotel/reception.py` +
  tabella `reception` + finestra `gui/reception_view.py`, pulsante "Reception".
  - Gli ospiti compaiono in reception a orari casuali (sul time tick, come le
    mail): arrivi fuori dai turni Mattina/Pranzo, partenze solo di Mattina.
  - Prenotazione con piu persone: una riga per ospite, tutte insieme; check-in
    per-persona (la prima occupa la camera). Orario in rosso se attende > 1h.
  - Check-out: una riga per prenotazione, apre il conto e lo applica.
  - Avviso lampeggiante giallo/bianco in alto a sinistra quando c'e coda;
    clic apre la Reception; nascosto se la Reception e gia aperta.
  - Il check-in/out via clic sulla camera e stato rimosso (RoomDialog);
    `gui/checkin_form.py` eliminato (inserimento ora automatico).

- **Persistenza stato di gioco** — `hotel/persistence.py` + tabella KV
  `settings`. Alla chiusura della finestra (`WM_DELETE_WINDOW`) salva
  orologio simulato (data/ora, scala, on/off) e config email; all'avvio li
  ripristina. Niente piu reset al riavvio.

- **Tempo simulato (gameplay)** — `hotel/clock.py` ora gestisce un datetime
  che avanza in scala (`scale` ore di gioco per 1h reale, default 24). `tick()`
  avanza in base al tempo reale trascorso; `today()`/`now()` seguono il tempo
  di gioco, quindi i giorni progrediscono e la dashboard si aggiorna da sola.
  - Barra in basso nella dashboard con data/ora e turno color-coded
    (Mattina/Pranzo/Pomeriggio/Sera/Notte); clic = finestra "Orario"
    (`gui/time_view.py`) con orologio, data, ora e turno che si aggiornano.
  - Toggle on/off e scala personalizzabile dalla scheda Debug.
  - Il timer delle email resta su tempo reale, invariato.
- **Debug a sezioni collassabili** — le sezioni della scheda Debug si
  espandono/collassano (`[+]/[-]`) per fare posto a impostazioni future.

## 2026-06-15

### Aggiunto

- **Sezione Budget (bilancio dell'hotel)** — nuovo `hotel/budget.py` e
  `gui/budget_view.py`, pulsante "Budget" in toolbar.
  - Registro unico `ledger` (nuova tabella in `database.py`: `day`, `kind`
    income/loss, `category`, `amount`, `note`). Saldo = introiti − perdite,
    calcolato con una query (nessuna colonna saldo da sincronizzare).
  - Al **check-out** il conto alimenta il bilancio: il netto entra come
    introito "Soggiorno", l'IVA come perdita "IVA".
  - `billing.bill_totals` ora espone anche `net` e `vat` (oltre a
    subtotal/total).
  - Finestra Budget con `Treeview`: saldo, introiti, perdite e l'elenco dei
    movimenti.
  - Pensato flessibile per categorie future (bollette, stipendi): bastano
    altre `budget.record(...)`, niente modifiche allo schema.
- **Tool di debug → budget** — sezione "Aggiungi movimento al budget"
  (Tipo Introito/Perdita, Categoria libera, Importo, Nota) per iniettare
  movimenti di prova. `clear_all` ora svuota anche il `ledger`.

### Corretto

- **Doppione in timeline** — le prenotazioni in check-out restavano disegnate
  e si sovrapponevano ai nuovi soggiorni della stessa camera (sembrava una
  doppia prenotazione). `reservations.in_range` filtrava `status != 'cancelled'`
  (stato mai usato): ora filtra `status IN ('booked','checked_in')`. Rimossa la
  voce colore `checked_out` ormai irraggiungibile in `timeline.py`.

### Migliorato (QOL / UI)

- **Finestra camera unica** — cliccando le camere non si apre più una finestra
  per ognuna: una sola finestra che si aggiorna sulla camera selezionata
  (`RoomDialog.show()`, riuso dell'istanza in `app.py`). Meno clutter, niente
  chiusure manuali.

### Pulizia

- `names.random_first_name`: rimosso il parametro `child` mai usato (il corpo
  ignorava il genere/età).
- `clock.is_overridden`: rimosso, usato solo da un assert ridondante nel test.

### Test

- `smoke_test.py`: aggiunti check su budget (netto/IVA/saldo dell'esempio del
  prompt: 255 / 56.10 / 198.90) e regressione "il check-out sparisce dalla
  timeline".
