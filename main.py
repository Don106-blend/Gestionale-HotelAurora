"""Punto di ingresso di HotelAurora: menu iniziale, poi il gestionale."""

from gui.start_screen import StartScreen

if __name__ == "__main__":
    menu = StartScreen()
    menu.mainloop()
    if menu.play:                     # Nuova/Carica partita -> si gioca
        from gui.app import HotelApp
        HotelApp().mainloop()
