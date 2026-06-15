"""Calcolo e formattazione del conto di una prenotazione."""

from datetime import date, timedelta

from . import constants


def bill_lines(res) -> list[tuple[str, date, float]]:
    """Una riga (soluzione, data, prezzo) per ogni notte di soggiorno."""
    checkin = date.fromisoformat(res["checkin_date"])
    checkout = date.fromisoformat(res["checkout_date"])
    price = res["price_per_night"]
    lines = []
    day = checkin
    while day < checkout:
        lines.append((res["board"], day, price))
        day += timedelta(days=1)
    return lines


def bill_totals(res) -> dict:
    lines = bill_lines(res)
    subtotal = sum(price for _, _, price in lines)
    discount_pct = res["discount"] or 0.0
    discount_amount = round(subtotal * discount_pct / 100, 2)
    net = round(subtotal - discount_amount, 2)
    vat = round(net * constants.VAT_RATE, 2)
    return {"subtotal": subtotal, "discount_pct": discount_pct,
            "discount_amount": discount_amount,
            "net": net, "vat": vat, "total": round(net + vat, 2)}


def bill_text(res, guest_name: str) -> str:
    """Conto in formato testo, pronto per la stampa."""
    out = [f"HotelAurora - Conto camera {res['room_number']}",
           f"Cliente: {guest_name}",
           f"Codice: {res['code']}", ""]
    for board, day, price in bill_lines(res):
        out.append(f"{board:<4} {day.strftime('%d/%m')}    {price:>8.2f} EUR")
    t = bill_totals(res)
    out.append("")
    out.append(f"{'Subtotale':<14} {t['subtotal']:>8.2f} EUR")
    if t["discount_amount"]:
        out.append(f"{'Sconto ' + format(t['discount_pct'], 'g') + '%':<14}"
                   f" {-t['discount_amount']:>8.2f} EUR")
    out.append(f"{'Totale + IVA ' + format(constants.VAT_RATE * 100, 'g') + '%':<14}"
               f" {t['total']:>8.2f} EUR")
    return "\n".join(out)
