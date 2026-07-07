"""Punto di ingresso di HotelAurora Web: server Flask multi-sessione.

Sostituisce il menu/mainloop tkinter (gui/start_screen.py, gui/app.py): ogni
browser che si collega ha la propria partita (cookie di sessione -> proprio
file .db in sessions_data/), e il tempo di gioco avanza in un thread server-
side indipendente dalle richieste HTTP (vedi hotel_web/session_state.py).
"""

from hotel_web import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, threaded=True)
