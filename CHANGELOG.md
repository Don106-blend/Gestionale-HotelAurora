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
