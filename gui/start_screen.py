"""Menu iniziale: Nuova Partita, Carica Partita (import/export), Istruzioni."""

import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from hotel import database, estate

BANNER = r"""
 _   _       _       _    _
| | | | ___ | |_ ___| |  / \   _   _ _ __ ___  _ __ __ _
| |_| |/ _ \| __/ _ \ | / _ \ | | | | '__/ _ \| '__/ _` |
|  _  | (_) | ||  __/ |/ ___ \| |_| | | | (_) | | | (_| |
|_| |_|\___/ \__\___|_/_/   \_\\__,_|_|  \___/|_|  \__,_|

                S I M U L A T O R
"""

SAVE_FILETYPES = [("Salvataggio HotelAurora", "*.db"), ("Tutti i file", "*.*")]

ISTRUZIONI = """\
HOTELAURORA SIMULATOR — ISTRUZIONI

OBIETTIVO
Gestisci il tuo hotel: accetta prenotazioni, accogli gli ospiti, paga
dipendenti, tasse e bollette, e fai crescere categoria (stelle) e rating.
Si parte con 10 camere (2 suite), 10.000 euro, 1 addetto pulizie, 2 operatori
di sala e 1 receptionist a scelta tra 4.

TEMPO
La barra in basso mostra data/ora simulate e il turno (Mattina, Pranzo,
Pomeriggio, Sera, Notte). Controlli: Pausa, Play, T (tempo reale), 1x/2x/5x.
Di default 1 ora reale = 48 ore di gioco (modificabile da Impostazioni).

PRENOTAZIONI
- Le richieste arrivano per email (Browser > Mail): Inserisci o Rifiuta.
  Scadono dopo 48 ore o superata la data di check-in.
- Il flusso dipende da stagione, rating (recensioni) e categoria (stelle).
- "Nuova prenotazione" inserisce a mano; il prezzo per notte e di mercato:
  listino della soluzione (BB, RO, HB, FB, RES) x upgrade delle camere.
- Nella Timeline trascini una prenotazione (non ancora arrivata) su un'altra
  camera; a parita di date.

OSPITI E RECEPTION
- Gli arrivi compaiono in Reception (Pomeriggio/Sera): fai il check-in.
  Oltre 1,5 ore di attesa l'ospite si arrabbia, annulla e ti stronca.
- Il giorno della partenza scendono per il check-out: incassi il conto
  (100% del ricavato; l'IVA si accantona e si versa a fine mese).
- Chi sfora oltre le 14:30 esce d'ufficio SENZA pagare (salvo receptionist
  "Brutto muso" di turno).
- La tab Occupazione mostra chi e in camera (rosso = presenti, blu = tutti
  assenti); pallino rosa = pulizie in corso.

PASTI E CIBO
- I pasti (colazione/pranzo/cena) dipendono dalla soluzione della camera.
- Ogni pasto consuma 1 unita di cibo: compra da Browser > AllFoods!
  (10 euro/unita); la capienza dispensa si amplia dalle Ristrutturazioni.
- La sala pasti ha tavoli e sedie (tab Sala pasti): gruppi della stessa
  camera insieme, mai con sconosciuti. Compra tavoli/sedie e sposta i tavoli
  col tasto Layout.
- Serve personale di sala: ogni operatore gestisce 24 ospiti, max 2 turni.
- Se manca cibo, posto o personale l'ospite si lamenta in Reception (tasto
  Parla, chiudi con Scusati): pesa sulla recensione.
- Room service: qualche ospite ordina in camera (1 cibo, +15 euro).

DIPENDENTI (bottone Dipendenti)
- Pulizie: turno 7-15, max 8h/giorno; puliscono rimanenze e check-out
  (0.25h / 0.5h a camera). Le camere tornano pulite da sole.
- Sala: assegnati automaticamente ai pasti in base ai fogli pasti.
- Assumi/licenzia e pianifica quanti chiamarne da domani; il foglio ore
  registra tutto; stipendi il 20 del mese (7 euro/h lordi x1.46 costo
  azienda). I dipendenti possono ammalarsi; con l'esperienza puliscono
  piu in fretta.
- Receptionist: rari, con un bonus passivo ciascuno. Si assumono dalle
  candidature (Browser > JobHotel) con contratto full-time (40h), part-time
  (20h) o in nero (2 giorni, 9 euro/h flat). Prova di 3 mesi: poi restano a
  tempo indeterminato o se ne vanno. I turni si pianificano dalla tabella
  settimanale (il giorno corrente e bloccato).

ECONOMIA
- Budget: entrate (soggiorni, room service, bar, casino, mance, prestiti)
  e uscite (stipendi, bollette, ristrutturazioni, IVA, rate).
- A fine mese si pagano: IVA accantonata, rate dei prestiti e bollette
  (150 euro + 2/camera).
- Banca (Browser): prestiti da 5.000 (TAN 5%), 15.000 (TAN 8%),
  40.000 (TAN 12%), rimborso in 12 rate mensili, max 3 prestiti aperti.

CRESCITA
- Ristrutturazioni: nuove camere (+250 euro a camera acquistata, poi +500;
  suite x2), nuovi piani (10.000), dispensa, tavoli, rinnovo camere logore
  (l'usura cresce a ogni check-out) e i servizi: Wi-Fi, ristoro, reception
  decorata, sala riunioni, piscina, casino, luci rosse, camere migliorate
  (x1.5) e luxury (x2.5).
- Categoria (1-5 stelle): dipende da camere e servizi. Piu stelle = piu
  richieste. Il pannello mostra cosa manca per la prossima.
- Rating (TrustHotel): parte da 3. Le recensioni NEGATIVE arrivano da sole
  (reclami, attese, camere logore, truffe); le POSITIVE solo se c'e
  qualcosa da lodare: servizi comprati o receptionist giusti.

IMPOSTAZIONI (ex Debug)
Velocita del tempo, data, generatore di prenotazioni, budget manuale,
frequenza email, cibo, metadati ospiti e Reset totale.

SALVATAGGIO
La partita si salva da sola alla chiusura. Da Carica Partita puoi
esportare il salvataggio su file e importarlo altrove.
"""


class StartScreen(tk.Tk):
    """Menu iniziale; chiudilo pure: il gioco parte solo con Nuova/Carica."""

    def __init__(self):
        super().__init__()
        self.title("HotelAurora Simulator")
        self.resizable(False, False)
        self.play = False        # True -> avviare il gioco dopo il menu
        f = ttk.Frame(self, padding=24)
        f.pack()
        tk.Label(f, text=BANNER, font=("Courier New", 10, "bold"),
                 justify="left").pack()
        for label, cmd in (("Nuova Partita", self._new),
                           ("Carica Partita", self._load),
                           ("Istruzioni", self._help)):
            ttk.Button(f, text=label, width=24, command=cmd).pack(pady=4)

    def _start(self):
        self.play = True
        self.destroy()

    def _new(self):
        if estate.is_setup_done():
            if not messagebox.askyesno(
                    "Nuova Partita",
                    "Esiste gia una partita: iniziarne una nuova la"
                    " CANCELLERA per sempre.\nProseguire?", parent=self):
                return
            estate.reset_all()
        self._start()

    def _load(self):
        LoadDialog(self, on_play=self._start)

    def _help(self):
        InstructionsWindow(self)


class LoadDialog(tk.Toplevel):
    """Continua la partita corrente, oppure importa/esporta il salvataggio."""

    def __init__(self, master, on_play):
        super().__init__(master)
        self.on_play = on_play
        self.title("Carica Partita")
        self.resizable(False, False)
        self.grab_set()
        f = ttk.Frame(self, padding=16)
        f.pack()
        has_save = estate.is_setup_done()
        current = (f"Partita corrente: {estate.hotel_name()}"
                   f" (di {estate.user_name()})" if has_save
                   else "Nessuna partita salvata.")
        ttk.Label(f, text=current).pack(anchor="w", pady=(0, 10))
        ttk.Button(f, text="Continua la partita", width=28,
                   command=self._continue,
                   state="normal" if has_save else "disabled").pack(pady=2)
        ttk.Button(f, text="Importa salvataggio da file...", width=28,
                   command=self._import).pack(pady=2)
        ttk.Button(f, text="Esporta salvataggio su file...", width=28,
                   command=self._export,
                   state="normal" if has_save else "disabled").pack(pady=2)

    def _continue(self):
        self.destroy()
        self.on_play()

    def _import(self):
        path = filedialog.askopenfilename(parent=self,
                                          filetypes=SAVE_FILETYPES)
        if not path:
            return
        if not messagebox.askyesno(
                "Importa", "Il salvataggio importato SOSTITUIRA la partita"
                " corrente.\nProseguire?", parent=self):
            return
        database.close_conn()
        shutil.copy2(path, database.DB_PATH)
        messagebox.showinfo("Importa", "Salvataggio importato.", parent=self)
        self.destroy()
        self.on_play()

    def _export(self):
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".db",
            initialfile="hotelaurora_salvataggio.db",
            filetypes=SAVE_FILETYPES)
        if not path:
            return
        database.close_conn()      # flush su disco prima della copia
        shutil.copy2(database.DB_PATH, path)
        messagebox.showinfo("Esporta", f"Salvataggio esportato in:\n{path}",
                            parent=self)


class InstructionsWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Istruzioni")
        txt = tk.Text(self, width=78, height=34, wrap="word")
        scroll = ttk.Scrollbar(self, command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)
        txt.insert("1.0", ISTRUZIONI)
        txt.configure(state="disabled")
        txt.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scroll.pack(side="right", fill="y", pady=8)
