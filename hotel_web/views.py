"""Rotte Flask di HotelAurora Web: chiamano hotel/ cosi com'e, la GUI e solo
qui (HTML minimale via templates.page). Nessuna logica di gioco vive nelle
view: quella gira nel game loop di session_state, questa e solo lettura +
azioni dirette dell'utente (check-in, prenota, sposta, risolvi, ...)."""

import uuid
from datetime import date, datetime, timedelta

from flask import (Blueprint, g, redirect, request, send_file, session,
                    url_for)

from hotel import (amenities, bank, billing, budget, cleaning, clock,
                    constants, debug_seed, dining, estate, guest_state, guests,
                    mail, meals, problems, reception, reservations, reviews,
                    rooms, staff, taxes)
from hotel.database import kv_get, kv_set

from . import session_state, templates

bp = Blueprint("web", __name__)

WEEKDAYS = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")
BOARD_CHOICES = [(b.code, f"{b.code} - {b.label}") for b in constants.BOARDS.values()]
_SETUP_ENDPOINTS = {"web.setup", "web.setup_receptionist"}


# --- montaggio della sessione di gioco su ogni richiesta --------------------

@bp.before_request
def _mount():
    sid = session.get("sid")
    if not sid:
        sid = uuid.uuid4().hex
        session["sid"] = sid
        session.permanent = True
    cm = session_state.use(sid)
    cm.__enter__()
    g._cm = cm
    session_state.on_request(sid, request.headers.get("X-Poll") == "1")
    if request.endpoint in _SETUP_ENDPOINTS:
        return None
    if not estate.is_setup_done():
        return redirect(url_for("web.setup"))
    estate.grant_starting_capital()
    staff.ensure_seed()
    if not kv_get("rec_chosen", False):
        return redirect(url_for("web.setup_receptionist"))
    return None


@bp.teardown_request
def _unmount(exc):
    cm = g.pop("_cm", None)
    if cm is not None:
        cm.__exit__(None, None, None)


def common_ctx() -> dict:
    now = clock.now()
    shift_name, shift_color = clock.shift(now)
    ready = estate.is_setup_done()
    return {
        "hotel_name": estate.hotel_name(),
        "now_str": now.strftime("%a %d/%m/%Y %H:%M"),
        "shift_name": shift_name, "shift_color": shift_color,
        "balance": budget.totals()["balance"],
        "paused": clock.paused, "speed": clock.speed, "realtime": clock.realtime,
        "pending_count": len(reception.pending()) if ready else 0,
        "mail_new": (sum(1 for m in mail.search_mails() if mail.status(m) == "Da gestire")
                     if ready else 0),
        # il "Bentornato" si consuma solo su una richiesta reale (non i poll)
        "welcome": (None if request.headers.get("X-Poll") == "1"
                    else session_state.take_welcome(session.get("sid"))),
    }


def render_page(title, active, body_tpl, *, live=True, **extra) -> str:
    return templates.page(title, active, body_tpl, {**common_ctx(), **extra},
                          live=live)


# --- primo avvio -------------------------------------------------------------

SETUP_TPL = """
<div class="card">
<h2>Benvenuto in HotelAurora</h2>
<form method="post">
  <p><label>Il tuo nome:<br><input name="user_name" required></label></p>
  <p><label>Nome dell'hotel:<br><input name="hotel_name" required></label></p>
  <button>Inizia</button>
</form>
</div>
"""


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if estate.is_setup_done():
        return redirect(url_for("web.dashboard"))
    if request.method == "POST":
        estate.complete_setup(request.form.get("user_name", ""),
                              request.form.get("hotel_name", ""))
        return redirect(url_for("web.setup_receptionist"))
    return render_page("Benvenuto", "web.setup", SETUP_TPL, live=False)


SETUP_REC_TPL = """
<div class="card">
<h2>Scegli il tuo receptionist</h2>
<p>Uno solo: gli altri troveranno lavoro altrove.</p>
<form method="post">
{% for c in candidates %}
<p><label><input type="radio" name="choice" value="{{ loop.index0 }}" {{ 'checked' if loop.first }}>
 {{ c.first_name }} {{ c.last_name }} &mdash; {{ c.bonus_label }}: {{ c.bonus_desc }}</label></p>
{% endfor %}
<button>Assumi (full-time)</button>
</form>
</div>
"""


@bp.route("/setup/receptionist", methods=["GET", "POST"])
def setup_receptionist():
    if not estate.is_setup_done():
        return redirect(url_for("web.setup"))
    if kv_get("rec_chosen", False):
        return redirect(url_for("web.dashboard"))
    cands = staff.first_candidates()
    if request.method == "POST":
        c = cands[int(request.form.get("choice", 0))]
        staff.hire_receptionist(c["first_name"], c["last_name"], c["bonus"], "full")
        kv_set("rec_chosen", True)
        return redirect(url_for("web.dashboard"))
    ctx_cands = [{**c, "bonus_label": staff.BONUSES[c["bonus"]][0],
                 "bonus_desc": staff.BONUSES[c["bonus"]][1]} for c in cands]
    return render_page("Il tuo primo receptionist", "web.setup_receptionist",
                       SETUP_REC_TPL, live=False, candidates=ctx_cands)


# --- velocita di gioco ---------------------------------------------------------

@bp.route("/speed", methods=["POST"])
def speed():
    mode = request.form.get("mode")
    if mode == "pause":
        clock.paused = True
    else:
        clock.paused = False
        clock.running = True
        if mode == "realtime":
            clock.realtime = True
        elif mode in ("1", "2", "5"):
            clock.realtime = False
            clock.speed = float(mode)
    return redirect(request.form.get("back") or url_for("web.dashboard"))


# --- dashboard: griglia camere -------------------------------------------------

DASHBOARD_TPL = """
<div class="card" style="display:flex;justify-content:space-between;align-items:center">
  <a class="btn" href="{{ url_for('web.booking_page') }}">+ Nuova prenotazione</a>
  <span style="font-size:12px;color:#555">Clicca una camera per la scheda.
    Striscia gialla = check-out oggi | quadrato fucsia = arrivo oggi |
    quadrato blu = arrivo domani | linea grigia = sporca | rossa = bloccata |
    arancione = logora</span>
</div>
{% for floor, floor_rooms in floors %}
<h3>Piano {{ floor }}</h3>
<div class="grid">
  {% for r in floor_rooms %}
  <a class="room" style="background: {{ r.fill }}" href="{{ url_for('web.room_page', number=r.number) }}">
    <span class="num">{{ r.number }}{{ ' S' if r.is_suite else '' }}</span>
    {% if r.guest %}<div>{{ r.guest[:16] }}</div>{% endif %}
    {% if r.checkout_today %}<span class="m-checkout"></span>{% endif %}
    {% if r.dirty %}<span class="m-dirty"></span>{% endif %}
    {% if r.blocked %}<span class="m-blocked"></span>{% endif %}
    {% if r.worn %}<span class="m-wear"></span>{% endif %}
    {% if r.arrival_today %}<span class="m-arr-today"></span>{% endif %}
    {% if r.arrival_next %}<span class="m-arr-next"></span>{% endif %}
  </a>
  {% endfor %}
</div>
{% endfor %}
"""


@bp.route("/")
def dashboard():
    today = clock.today()
    tomorrow = today + timedelta(days=1)
    by_floor = []
    all_rooms = rooms.all_rooms()
    for floor in rooms.floors():
        floor_rooms = []
        for r in (x for x in all_rooms if x["floor"] == floor):
            res = reservations.current_for_room(r["number"])
            floor_rooms.append({
                "number": r["number"], "is_suite": r["is_suite"],
                "fill": (res["color"] or constants.COLOR_OCCUPIED) if res else constants.COLOR_FREE,
                "guest": reservations.guest_display_name(res) if res else "",
                "checkout_today": bool(res) and res["checkout_date"] == today.isoformat(),
                "dirty": r["dirty"], "blocked": r["blocked"],
                "worn": r["wear"] >= constants.WEAR_LIMIT,
                "arrival_today": bool(reservations.arrival_on(r["number"], today)),
                "arrival_next": bool(reservations.arrival_on(r["number"], tomorrow)),
            })
        by_floor.append((floor, floor_rooms))
    return render_page("Camere", "web.dashboard", DASHBOARD_TPL, floors=by_floor)


# --- scheda camera (RoomDialog) ------------------------------------------------

ROOM_TPL = """
<div class="card">
<h2>Camera {{ number }}{{ ' (suite)' if room.is_suite else '' }}</h2>
<p>{{ 'Suite' if room.is_suite else 'Camera standard' }} &mdash;
   max {{ room.max_adults }} adulti + {{ room.max_children }} bambino</p>
<p>Stato: <b>{{ 'Occupata' if current else 'Libera' }}</b> |
   {{ 'Sporca' if room.dirty else 'Pulita' }} |
   {{ 'Bloccata' if room.blocked else 'Sbloccata' }} |
   Usura: {{ room.wear }}{{ ' (logora)' if worn else '' }}</p>
<form method="post" action="{{ url_for('web.room_toggle', number=number, what='clean') }}" style="display:inline">
  <button>{{ 'Segna pulita' if room.dirty else 'Segna sporca' }}</button></form>
<form method="post" action="{{ url_for('web.room_toggle', number=number, what='block') }}" style="display:inline">
  <button>{{ 'Sblocca' if room.blocked else 'Blocca' }}</button></form>
<a class="btn" href="{{ url_for('web.booking_page', room=number) }}">Nuova prenotazione</a>
{% if current %}<a class="btn" href="{{ url_for('web.room_guests', number=number) }}">Ospiti in camera</a>{% endif %}
{% if room_msg %}<p class="msg">{{ room_msg }}</p>{% endif %}
</div>
<div class="card">
<h3>Prenotazioni</h3>
{% if not upcoming %}<p>Nessuna.</p>{% endif %}
{% if upcoming %}
<table>
<tr><th>Codice</th><th>Check-in</th><th>Check-out</th><th>Ospite</th><th>Stato</th></tr>
{% for res in upcoming %}
<tr><td>{{ res.code }}</td><td>{{ res.ci }}</td><td>{{ res.co }}</td>
    <td>{{ res.name }}</td><td>{{ res.status }}</td></tr>
{% endfor %}
</table>
{% endif %}
</div>
"""


def _room_page(number, msg=None):
    room = rooms.get_room(number)
    if room is None:
        return redirect(url_for("web.dashboard"))
    today = clock.today()
    upcoming = [{"code": r["code"], "name": reservations.guest_display_name(r),
                 "status": r["status"],
                 "ci": date.fromisoformat(r["checkin_date"]).strftime("%d/%m"),
                 "co": date.fromisoformat(r["checkout_date"]).strftime("%d/%m")}
                for r in reservations.upcoming_for_room(number, today)[:8]]
    return render_page(f"Camera {number}", "web.dashboard", ROOM_TPL,
                       number=number, room=room,
                       current=reservations.current_for_room(number),
                       worn=room["wear"] >= constants.WEAR_LIMIT,
                       upcoming=upcoming, room_msg=msg)


@bp.route("/room/<int:number>")
def room_page(number):
    return _room_page(number)


@bp.route("/room/<int:number>/<what>", methods=["POST"])
def room_toggle(number, what):
    room = rooms.get_room(number)
    if room is None:
        return redirect(url_for("web.dashboard"))
    if what == "clean":
        rooms.set_dirty(number, not room["dirty"])
    elif what == "block":
        if not room["blocked"] and reservations.current_for_room(number):
            return _room_page(number, msg="Non si puo bloccare una camera occupata.")
        rooms.set_blocked(number, not room["blocked"])
    return redirect(url_for("web.room_page", number=number))


ROOM_GUESTS_TPL = """
<div class="card">
<h2>Camera {{ number }} &mdash; ospiti</h2>
{% if not rows %}<p>Nessun ospite in camera.</p>{% endif %}
{% if rows %}
<table>
<tr><th>Nome</th><th>Stato</th><th>Locazione</th><th>Emozione</th></tr>
{% for r in rows %}
<tr><td><span class="dot" style="background:{{ r.color }}"></span> {{ r.name }}</td>
    <td>{{ r.stato }}</td><td>{{ r.locazione }}</td><td>{{ r.emozione }}</td></tr>
{% endfor %}
</table>
{% endif %}
<a class="btn" href="{{ url_for('web.room_page', number=number) }}">Scheda camera</a>
<a class="btn" href="{{ url_for('web.occupancy') }}">Occupazione</a>
</div>
"""


@bp.route("/room/<int:number>/guests")
def room_guests(number):
    now = clock.now()
    res = reservations.current_for_room(number)
    rows = [guest_state.describe(gu, now)
            for gu in guests.for_reservation(res["id"])] if res else []
    return render_page(f"Camera {number} ospiti", "web.occupancy",
                       ROOM_GUESTS_TPL, number=number, rows=rows)


# --- occupazione: "visione termica" con pallini per ospite ---------------------

OCCUPANCY_TPL = """
<div class="thermal">
  <div class="legend"></div>
  <div class="legkey">Pallino per ospite &mdash; rosso/arancio = sveglio,
    blu = addormentato, grigio = assente. Cella rossa = ospiti presenti,
    blu = tutti assenti, grigia = libera. Clicca per le info.</div>
  <div class="grid">
    {% for r in rooms %}
    <a class="room" style="background: {{ r.fill }}"
       href="{{ url_for('web.room_guests', number=r.number) }}">
      <span class="num">{{ r.number }}{{ ' S' if r.is_suite else '' }}</span>
      <div class="dots">
        {% for d in r.dots %}<span class="dot" style="background:{{ d }}"></span>{% endfor %}
      </div>
      {% if r.cleaning %}<span class="m-arr-today" style="background:#f48fb1"></span>{% endif %}
    </a>
    {% endfor %}
  </div>
</div>
"""


@bp.route("/occupancy")
def occupancy():
    now = clock.now()
    room_rows = []
    for r in rooms.all_rooms():
        number = r["number"]
        res = reservations.current_for_room(number)
        descs = ([guest_state.describe(gu, now) for gu in guests.for_reservation(res["id"])]
                 if res else [])
        if res is None:
            fill = "#101418"                                   # libera (fredda)
        elif any(d["stato"] != "Assente" for d in descs):
            fill = "#5a1f1f"                                   # ospiti presenti
        else:
            fill = "#12204a"                                  # tutti assenti
        # un pallino per ospite; l'assente resta un pallino grigio
        dots = [guest_state.COLORS.get(d["stato"], "#757575") for d in descs]
        room_rows.append({
            "number": number, "is_suite": r["is_suite"], "fill": fill,
            "dots": dots, "cleaning": staff.cleaner_in_room(number)})
    return render_page("Occupazione", "web.occupancy", OCCUPANCY_TPL, rooms=room_rows)


# --- timeline: barre prenotazioni + spostamento camera -------------------------

TIMELINE_TPL = """
<div class="card">
<h2>Timeline</h2>
<p style="font-size:12px;color:#555">Trascina una prenotazione non ancora arrivata
  su un'altra riga-camera per spostarla (stesse date). Le prenotazioni gia in
  check-in non si trascinano.</p>
<div class="tl">
<table>
<tr><th class="room">Cam.</th>{% for d in days %}<th class="{{ 'today' if d.today }}">{{ d.label }}</th>{% endfor %}</tr>
{% for row in grid %}
<tr data-room="{{ row.number }}">
  <td class="room">{{ row.number }}</td>
  {% for c in row.cells %}
  <td class="{{ 'today' if c.today }}">
    {% if c.res %}<div class="bar{{ ' movable' if c.movable }}" style="background:{{ c.color }}"
      title="{{ c.name }}"{% if c.movable %} draggable="true" data-res="{{ c.res_id }}"{% endif %}>{{ c.name if c.first else '' }}</div>{% endif %}
  </td>
  {% endfor %}
</tr>
{% endfor %}
</table>
</div>
</div>
<script>
(function(){
  let dragged = null;
  document.addEventListener("dragstart", e => {
    const bar = e.target.closest(".bar.movable");
    if (!bar) return;
    dragged = bar.dataset.res;
    e.dataTransfer.effectAllowed = "move";
  });
  document.addEventListener("dragend", () => {
    dragged = null;
    document.querySelectorAll("tr.drop").forEach(t => t.classList.remove("drop"));
  });
  document.querySelectorAll("tr[data-room]").forEach(tr => {
    tr.addEventListener("dragover", e => { if (dragged) { e.preventDefault(); tr.classList.add("drop"); } });
    tr.addEventListener("dragleave", () => tr.classList.remove("drop"));
    tr.addEventListener("drop", e => {
      e.preventDefault();
      tr.classList.remove("drop");
      if (!dragged || tr.dataset.room === undefined) return;
      const body = new FormData();
      body.append("res_id", dragged);
      body.append("room", tr.dataset.room);
      fetch("{{ url_for('web.timeline_move') }}", { method: "POST", body })
        .then(r => r.json())
        .then(d => { if (d && d.error) alert(d.error); location.reload(); })
        .catch(() => location.reload());
      dragged = null;
    });
  });
})();
</script>
"""

TL_STATUS_COLOR = {"booked": constants.COLOR_BOOKED_BAR,
                   "checked_in": constants.COLOR_OCCUPIED}


def _timeline_page():
    today = clock.today()
    start = today - timedelta(days=3)
    n_days = 31
    days = [{"label": (start + timedelta(days=i)).strftime("%d/%m"),
             "today": start + timedelta(days=i) == today} for i in range(n_days)]
    span = [start + timedelta(days=i) for i in range(n_days)]
    # copertura per (camera, giorno): prenotazione attiva che copre quel giorno
    cover = {}
    for res in reservations.in_range(start, span[-1]):
        ci = date.fromisoformat(res["checkin_date"])
        co = date.fromisoformat(res["checkout_date"])
        for d in span:
            if ci <= d < co:
                cover[(res["room_number"], d)] = res
    grid = []
    for r in rooms.all_rooms():
        cells = []
        for d in span:
            res = cover.get((r["number"], d))
            cells.append({
                "today": d == today,
                "res": res is not None,
                "res_id": res["id"] if res else None,
                "movable": bool(res) and res["status"] == "booked",
                "first": bool(res) and date.fromisoformat(res["checkin_date"]) == d,
                "name": reservations.guest_display_name(res) if res else "",
                "color": (res["color"] or TL_STATUS_COLOR.get(res["status"], "#ccc")) if res else ""})
        grid.append({"number": r["number"], "cells": cells})
    return render_page("Timeline", "web.timeline_page", TIMELINE_TPL,
                       live=False, days=days, grid=grid)


@bp.route("/timeline")
def timeline_page():
    return _timeline_page()


@bp.route("/timeline/move", methods=["POST"])
def timeline_move():
    """Spostamento via drag&drop: cambia solo la camera (stesse date).
    Ritorna JSON (chiamato in fetch dalla timeline)."""
    try:
        reservations.change_room(int(request.form["res_id"]),
                                 int(request.form["room"]))
    except (reservations.ValidationError, ValueError, KeyError) as exc:
        return {"error": str(exc) or "Spostamento non valido."}, 400
    return {"ok": True}


# --- nuova prenotazione (BookingForm) ------------------------------------------

BOOKING_TPL = """
<div class="card">
<h2>Nuova prenotazione</h2>
<form method="post">
  <table style="width:auto">
  <tr><td>Nome</td><td><input name="first_name" value="{{ f.first_name }}"></td>
      <td>Cognome</td><td><input name="last_name" value="{{ f.last_name }}"></td></tr>
  <tr><td>Telefono</td><td><input name="phone" value="{{ f.phone }}"></td>
      <td>Email</td><td><input name="email" value="{{ f.email }}"></td></tr>
  <tr><td>Check-in</td><td><input type="date" name="checkin" value="{{ f.checkin }}"></td>
      <td>Notti</td><td><input type="number" name="nights" min="1" value="{{ f.nights }}" style="width:70px"></td></tr>
  <tr><td>Adulti</td><td><input type="number" name="adults" min="1" value="{{ f.adults }}" style="width:70px"></td>
      <td>Bambini</td><td><input type="number" name="children" min="0" value="{{ f.children }}" style="width:70px"></td></tr>
  <tr><td>Soluzione</td><td>
      <select name="board">
        {% for code, label in boards %}<option value="{{ code }}" {{ 'selected' if code == f.board }}>{{ label }}</option>{% endfor %}
      </select></td>
      <td>Prezzo/notte</td><td>&euro; {{ '%.2f'|format(price) }} <small>(mercato)</small></td></tr>
  <tr><td>Camera</td><td>
      <select name="room">
        {% for n, lab in room_choices %}<option value="{{ n }}" {{ 'selected' if n|string == f.room }}>{{ lab }}</option>{% endfor %}
      </select></td>
      <td>Sconto %</td><td><input name="discount" value="{{ f.discount }}" style="width:70px"></td></tr>
  <tr><td>Colore</td><td>
      <label><input type="checkbox" name="use_color" {{ 'checked' if f.use_color }}> usa</label>
      <input type="color" name="color" value="{{ f.color or '#cfe2f3' }}"></td>
      <td>Commenti</td><td><input name="comments" value="{{ f.comments }}"></td></tr>
  </table>
  <p>
    <button name="action" value="update">Aggiorna camere/prezzo</button>
    <button name="action" value="save">Salva prenotazione</button>
    {% if confirm %}<button name="action" value="confirm">Salva comunque</button>{% endif %}
  </p>
</form>
{% if warn %}<p class="msg">{{ warn }}</p>{% endif %}
{% if book_msg %}<p class="msg">{{ book_msg }}</p>{% endif %}
</div>
"""


def _booking_defaults(room=None):
    today = clock.today()
    return {"first_name": "", "last_name": "", "phone": "", "email": "",
            "checkin": today.isoformat(), "nights": "1", "adults": "2",
            "children": "0", "board": "BB", "room": str(room or ""),
            "discount": "", "use_color": False, "color": "", "comments": ""}


def _booking_dates(f):
    ci = date.fromisoformat(f["checkin"])
    return ci, ci + timedelta(days=max(1, int(f["nights"] or 1)))


def _render_booking(f, warn=None, msg=None, confirm=False):
    try:
        ci, co = _booking_dates(f)
        free = reservations.available_rooms(ci, co)
    except (ValueError, TypeError):
        free = []
    room_choices = [(r["number"], f"{r['number']}{' (suite)' if r['is_suite'] else ''}")
                    for r in free]
    if f["room"] and f["room"] not in {str(n) for n, _ in room_choices}:
        room_choices.insert(0, (int(f["room"]), f"{f['room']} (attuale)"))
    price = reservations.price_for(f["board"]) if f["board"] in constants.BOARDS else 0.0
    return render_page("Nuova prenotazione", "web.dashboard", BOOKING_TPL,
                       live=False, f=f, boards=BOARD_CHOICES,
                       room_choices=room_choices, price=price, warn=warn,
                       book_msg=msg, confirm=confirm)


@bp.route("/booking", methods=["GET", "POST"])
def booking_page():
    if request.method == "GET":
        return _render_booking(_booking_defaults(request.args.get("room")))
    f = {k: request.form.get(k, "").strip() for k in _booking_defaults()}
    f["use_color"] = request.form.get("use_color") == "on"
    action = request.form.get("action")
    if action == "update":
        return _render_booking(f)
    try:
        ci, co = _booking_dates(f)
        adults, children = int(f["adults"] or 1), int(f["children"] or 0)
        room_number = int(f["room"])
        discount = float(f["discount"].replace(",", ".")) if f["discount"] else None
    except (ValueError, TypeError):
        return _render_booking(f, msg="Valori non validi (controlla date, numeri, camera).")
    warn = reservations.capacity_warning(room_number, adults, children)
    if warn and action != "confirm":
        return _render_booking(f, warn=warn + " Confermi?", confirm=True)
    try:
        reservations.create_reservation(
            first_name=f["first_name"], last_name=f["last_name"],
            room_number=room_number, checkin=ci, checkout=co, adults=adults,
            children=children, price_per_night=reservations.price_for(f["board"]),
            board=f["board"], discount=discount, phone=f["phone"],
            email=f["email"], color=(f["color"] if f["use_color"] else ""),
            comments=f["comments"])
    except reservations.ValidationError as exc:
        return _render_booking(f, msg=str(exc))
    return redirect(url_for("web.dashboard"))


# --- reception: arrivi/partenze/reclami ----------------------------------------

RECEPTION_TPL = """
<div class="card">
<h2>Reception</h2>
<p style="font-style:italic">{{ desk }}</p>
{% if not entries %}<p>Nessuno in attesa.</p>{% endif %}
{% if entries %}
<table>
<tr><th>Camera</th><th>Ospite</th><th>Tipo</th><th>Dalle</th><th></th></tr>
{% for e in entries %}
<tr {{ 'style="color:#b71c1c"' if e.late }}>
  <td>{{ e.room_number }}</td>
  <td>{{ e.first_name }} {{ e.last_name }}{{ ' (bambino)' if e.is_child else '' }}</td>
  <td>{{ e.label }}</td>
  <td>{{ e.arrived_at[11:16] }}</td>
  <td>
    {% if e.kind == 'checkin' %}
    <form method="post" action="{{ url_for('web.reception_checkin', entry_id=e.id) }}"><button>Check-in</button></form>
    {% elif e.kind == 'checkout' %}
    <a class="btn" href="{{ url_for('web.reception_checkout', entry_id=e.id) }}">Conto / check-out</a>
    {% else %}
    <a class="btn" href="{{ url_for('web.reception_talk', entry_id=e.id) }}">Parla</a>
    {% endif %}
  </td>
</tr>
{% endfor %}
</table>
{% endif %}
</div>
"""

RECEPTION_LABELS = {"checkout": "Check-out", "checkin": "Check-in",
                    "food": "Reclamo cibo", "service": "Reclamo servizio",
                    "table": "Reclamo tavoli", "problem": "Problema"}


@bp.route("/reception")
def reception_page():
    now = clock.now()
    rec = staff.receptionist_on_duty(now)
    desk = ("Al banco: nessun receptionist" if rec is None else
            f"Al banco: {rec['first_name']} {rec['last_name']} ({staff.BONUSES[rec['bonus']][0]})")
    entries = []
    for e in reception.pending():
        late = (now - datetime.fromisoformat(e["arrived_at"])).total_seconds() > 3600
        entries.append({**dict(e), "label": RECEPTION_LABELS.get(e["kind"], "Check-in"),
                        "late": late})
    return render_page("Reception", "web.reception_page", RECEPTION_TPL,
                       desk=desk, entries=entries)


@bp.route("/reception/<int:entry_id>/checkin", methods=["POST"])
def reception_checkin(entry_id):
    if reception.get(entry_id) is not None:
        reception.checkin_entry(entry_id)
    return redirect(url_for("web.reception_page"))


CHECKOUT_TPL = """
<div class="card">
<h2>Conto camera {{ room }}</h2>
<pre>{{ bill }}</pre>
<form method="post">
  <button>Conferma check-out</button>
  <a class="btn" href="{{ url_for('web.reception_page') }}">Annulla</a>
</form>
</div>
"""


@bp.route("/reception/checkout/<int:entry_id>", methods=["GET", "POST"])
def reception_checkout(entry_id):
    entry = reception.get(entry_id)
    if entry is None:
        return redirect(url_for("web.reception_page"))
    res = reservations.get(entry["reservation_id"])
    if request.method == "POST":
        if res is not None and res["status"] == "checked_in":
            try:
                reservations.do_checkout(
                    res["id"], receptionist=staff.receptionist_on_duty(clock.now()))
            except reservations.ValidationError:
                pass
        reception.remove(entry_id)
        return redirect(url_for("web.reception_page"))
    bill = billing.bill_text(res, reservations.guest_display_name(res)) if res else "—"
    room = res["room_number"] if res else "?"
    return render_page(f"Conto {room}", "web.reception_page",
                       CHECKOUT_TPL, live=False, room=room, bill=bill)


TALK_TPL = """
<div class="card">
<h2>{{ talk_title }}</h2>
<p><b>{{ entry.first_name }} {{ entry.last_name }} (Camera {{ room }})</b></p>
{% for m in messages %}<p>&laquo; {{ m }} &raquo;</p>{% endfor %}
<form method="post"><button>Scusati</button></form>
</div>
"""

TALK_MESSAGES = {
    "food": ("Ero sceso per il pasto ma non c'e niente da mangiare!",
             "Ho prenotato coi pasti inclusi, e una vergogna.",
             "Rifornite la cucina al piu presto."),
    "service": ("Sono in sala da un'ora e nessuno viene a servirci!",
                "Non c'e abbastanza personale, i tavoli sono abbandonati.",
                "Assumete piu camerieri."),
    "table": ("Non c'e un tavolo libero per noi!",
              "Non possiamo mangiare in piedi.",
              "Comprate piu tavoli e sedie."),
}
TALK_TITLES = {"food": "Reclamo: manca il cibo", "service": "Reclamo: servizio in sala",
               "table": "Reclamo: nessun tavolo libero", "problem": "Problema segnalato"}


@bp.route("/reception/talk/<int:entry_id>", methods=["GET", "POST"])
def reception_talk(entry_id):
    entry = reception.get(entry_id)
    if entry is None:
        return redirect(url_for("web.reception_page"))
    if request.method == "POST":
        reception.remove(entry_id)
        return redirect(url_for("web.reception_page"))
    if entry["kind"] == "problem":
        messages = [entry["note"] or "C'e un problema, venite a vedere!",
                    "Vi prego di sistemarlo al piu presto."]
    else:
        messages = list(TALK_MESSAGES.get(entry["kind"], TALK_MESSAGES["food"]))
    res = reservations.get(entry["reservation_id"])
    return render_page("Reclamo", "web.reception_page", TALK_TPL, live=False,
                       entry=entry, messages=messages,
                       room=res["room_number"] if res else "?",
                       talk_title=TALK_TITLES.get(entry["kind"], "Reclamo"))


# --- dipendenti ----------------------------------------------------------------

STAFF_TPL = """
<div class="card">
<h2>Dipendenti</h2>
<a class="btn" href="{{ url_for('web.staff_hours') }}">Foglio ore</a>
<table>
<tr><th>Nome</th><th>Ruolo</th><th>&euro;/h</th><th>Assunto</th><th>Ore mese</th>
    <th>Da pagare (h)</th><th>Stato</th><th></th></tr>
{% for e in employees %}
<tr>
  <td>{{ e.first_name }} {{ e.last_name }}{{ ' (malato oggi)' if e.sick else '' }}</td>
  <td>{{ e.role_label }}</td><td>{{ '%.2f'|format(e.hourly) }}</td>
  <td>{{ e.hired_on }}</td><td>{{ e.month_hours }}</td><td>{{ e.unpaid }}</td>
  <td>{{ e.stat }}</td>
  <td><form method="post" action="{{ url_for('web.staff_fire', emp_id=e.id) }}"
      onsubmit="return confirm('Licenziare {{ e.first_name }}?')"><button>Licenzia</button></form></td>
</tr>
{% endfor %}
</table>
<p>Oggi in servizio: {{ roster_text }}</p>
<p>Stipendi il {{ payday }} del mese &mdash; stima prossima: &euro; {{ '%.2f'|format(unpaid_cost) }}
   (lordo x{{ '%g'|format(cost_mult) }})</p>
</div>

<div class="card">
<h3>Assumi</h3>
<form method="post" action="{{ url_for('web.staff_hire', role='pulizie') }}" style="display:inline"><button>+ Pulizie</button></form>
<form method="post" action="{{ url_for('web.staff_hire', role='sala') }}" style="display:inline"><button>+ Sala</button></form>
</div>

<div class="card">
<h3>Turni di domani (in servizio)</h3>
<form method="post" action="{{ url_for('web.staff_roster') }}">
  {% for role, label in roles %}
  <label>{{ label }}: <input type="number" min="0" name="roster_{{ role }}"
    value="{{ roster_next[role] }}" style="width:60px"></label>
  {% endfor %}
  <button>Applica da domani</button>
</form>
</div>

<div class="card">
<h3>JobHotel &mdash; candidature della settimana</h3>
{% if not candidates %}<p>Nessuna candidatura questa settimana.</p>{% endif %}
{% for c in candidates %}
<form method="post" action="{{ url_for('web.staff_hire_candidate') }}" style="margin:3px 0">
  <input type="hidden" name="key" value="{{ c.key }}">
  <b>{{ c.first_name }} {{ c.last_name }}</b> &mdash; {{ c.bonus_label }}: {{ c.bonus_desc }}
  <select name="contract"><option value="full">Full-time</option>
    <option value="part">Part-time</option><option value="nero">In nero</option></select>
  <button>Assumi</button>
</form>
{% endfor %}
</div>

<div class="card">
<h3>Turni receptionist (settimana)</h3>
{% if not receptionists %}<p>Nessun receptionist assunto.</p>{% endif %}
{% if receptionists %}
<form method="post" action="{{ url_for('web.staff_shift') }}">
<table>
<tr><th>Receptionist</th>{% for d in weekdays %}<th>{{ d }}{{ ' (oggi)' if loop.index0 == today_wd }}</th>{% endfor %}</tr>
{% for e in receptionists %}
<tr>
  <td>{{ e.first_name }} {{ e.last_name }} ({{ e.contract_label }}, max {{ e.limit }}h){{ '' if e.permanent else ' - prova' }}</td>
  {% for wd in range(7) %}
  <td>{% if wd == today_wd %}{{ e.week.get(wd|string) or '-' }}
    {% else %}<select name="shift_{{ e.id }}_{{ wd }}">
      <option value="-">-</option>
      {% for s in e.allowed %}<option value="{{ s }}" {{ 'selected' if e.week.get(wd|string) == s else '' }}>{{ s }}</option>{% endfor %}
    </select>{% endif %}</td>
  {% endfor %}
</tr>
{% endfor %}
</table>
<button>Applica turni</button>
</form>
{% endif %}
{% if staff_msg %}<p class="msg">{{ staff_msg }}</p>{% endif %}
</div>
"""


def _staff_page(msg=None):
    today = clock.today()
    employees = []
    for e in staff.all_employees():
        if e["role"] == staff.ROLE_RECEPTION:
            role_label = f"{staff.ROLE_LABELS[e['role']]} ({staff.CONTRACTS[e['contract']]['label']})"
            stat = staff.BONUSES[e["bonus"]][0]
            if not e["permanent"]:
                stat += f" - prova fino al {e['contract_until']}"
        elif e["role"] == staff.ROLE_DINING:
            role_label, stat = staff.ROLE_LABELS[e["role"]], f"{e['served']} serviti"
        else:
            role_label = staff.ROLE_LABELS[e["role"]]
            stat = f"x{staff.speed_factor(e['id']):.2f} velocita"
        employees.append({**dict(e), "role_label": role_label, "stat": stat,
                          "sick": staff.is_sick(e["id"], today),
                          "month_hours": staff.month_hours(e["id"], today),
                          "unpaid": staff.unpaid_hours(e["id"])})
    current = staff.roster()
    roster_text = "  |  ".join(
        f"{staff.ROLE_LABELS[r]}: {current[r]}/{staff.headcount(r)}" for r in staff.ROLES)
    candidates = [{**c, "bonus_label": staff.BONUSES[c["bonus"]][0],
                  "bonus_desc": staff.BONUSES[c["bonus"]][1]} for c in staff.candidates()]
    sched = staff.schedule()
    receptionists = [
        {**dict(e), "contract_label": staff.CONTRACTS[e["contract"]]["label"],
         "week": sched.get(str(e["id"]), {}), "limit": staff.week_limit(e),
         "allowed": staff.allowed_shifts(e["contract"])}
        for e in staff.receptionists()]
    return render_page(
        "Dipendenti", "web.staff_page", STAFF_TPL, employees=employees,
        roster_text=roster_text, payday=staff.PAYDAY, unpaid_cost=staff.unpaid_cost(),
        cost_mult=staff.EMPLOYER_COST_MULT,
        roles=[(r, staff.ROLE_LABELS[r]) for r in staff.ROLES],
        roster_next=staff.roster_next(), candidates=candidates,
        receptionists=receptionists, weekdays=WEEKDAYS, today_wd=today.weekday(),
        staff_msg=msg)


@bp.route("/staff")
def staff_page():
    return _staff_page()


@bp.route("/staff/hire/<role>", methods=["POST"])
def staff_hire(role):
    try:
        staff.hire(role)
    except staff.StaffError:
        pass
    return redirect(url_for("web.staff_page"))


@bp.route("/staff/fire/<int:emp_id>", methods=["POST"])
def staff_fire(emp_id):
    try:
        staff.fire(emp_id)
    except staff.StaffError:
        pass
    return redirect(url_for("web.staff_page"))


@bp.route("/staff/roster", methods=["POST"])
def staff_roster():
    for role in staff.ROLES:
        try:
            staff.set_roster_next(role, int(request.form.get(f"roster_{role}", 0)))
        except ValueError:
            pass
    return redirect(url_for("web.staff_page"))


@bp.route("/staff/hire_candidate", methods=["POST"])
def staff_hire_candidate():
    try:
        staff.hire_candidate(request.form["key"], request.form.get("contract", "full"))
    except staff.StaffError:
        pass
    return redirect(url_for("web.staff_page"))


@bp.route("/staff/shift", methods=["POST"])
def staff_shift():
    today_wd = clock.today().weekday()
    for e in staff.receptionists():
        for wd in range(7):
            if wd == today_wd:
                continue
            raw = request.form.get(f"shift_{e['id']}_{wd}")
            if raw is None:
                continue
            shift = None if raw == "-" else raw
            if shift == staff.schedule().get(str(e["id"]), {}).get(str(wd)):
                continue
            try:
                staff.set_shift(e["id"], wd, shift)
            except staff.StaffError as exc:
                return _staff_page(msg=str(exc))
    return redirect(url_for("web.staff_page"))


HOURS_TPL = """
<div class="card">
<h2>Foglio ore</h2>
<pre>{{ sheet }}</pre>
<a class="btn" href="{{ url_for('web.staff_page') }}">Torna ai dipendenti</a>
</div>
"""


@bp.route("/staff/hours")
def staff_hours():
    return render_page("Foglio ore", "web.staff_page", HOURS_TPL, live=False,
                       sheet=staff.hours_sheet(clock.today()))


# --- banca ---------------------------------------------------------------------

BANK_TPL = """
<div class="card">
<h2>Banca di Aurora</h2>
<p>Debito residuo: &euro; {{ '%.2f'|format(debt) }} &mdash;
   rate del prossimo mese: &euro; {{ '%.2f'|format(due) }}</p>
{% for principal, info in tiers %}
<form method="post" style="margin:4px 0"><input type="hidden" name="principal" value="{{ principal }}">
  <button {{ 'disabled' if not can_borrow }}>&euro; {{ '{:,}'.format(principal) }}
    &mdash; TAN {{ (info.rate * 100)|round(0, 'floor')|int }}%
    (12 rate da &euro; {{ '%.2f'|format(info.installment) }})</button>
</form>
{% endfor %}
<h3>Prestiti aperti</h3>
{% if not loans %}<p>Nessun prestito aperto.</p>{% endif %}
<ul>{% for l in loans %}
<li>&euro; {{ '{:,}'.format(l.principal) }} @ {{ (l.rate * 100)|round(0, 'floor')|int }}%
    &mdash; residuo &euro; {{ '%.2f'|format(l.remaining) }} (rata &euro; {{ '%.2f'|format(l.installment) }})</li>
{% endfor %}</ul>
{% if bank_msg %}<p class="msg">{{ bank_msg }}</p>{% endif %}
</div>
"""


@bp.route("/bank", methods=["GET", "POST"])
def bank_page():
    msg = None
    if request.method == "POST":
        try:
            bank.take_loan(int(request.form["principal"]))
        except (bank.BankError, ValueError) as exc:
            msg = str(exc)
    tiers = [(p, {**info, "installment": round(p * (1 + info["rate"]) / info["months"], 2)})
             for p, info in bank.LOAN_TIERS.items()]
    return render_page("Banca", "web.browser_page", BANK_TPL, debt=bank.total_debt(),
                       due=bank.monthly_due(), tiers=tiers,
                       can_borrow=len(bank.loans()) < bank.MAX_LOANS,
                       loans=bank.loans(), bank_msg=msg)


# --- budget --------------------------------------------------------------------

BUDGET_TPL = """
<div class="card">
<h2>Budget</h2>
<p>Saldo: &euro; {{ '%.2f'|format(totals.balance) }} &mdash;
   Introiti: &euro; {{ '%.2f'|format(totals.income) }} &mdash;
   Perdite: &euro; {{ '%.2f'|format(totals.loss) }}</p>
<p>IVA accantonata (versata a fine mese): &euro; {{ '%.2f'|format(vat_due) }}</p>
<table>
<tr><th>Data</th><th>Tipo</th><th>Categoria</th><th>Importo</th><th>Nota</th></tr>
{% for e in entries %}
<tr><td>{{ e.day }}</td><td>{{ 'Introito' if e.kind == 'income' else 'Perdita' }}</td>
<td>{{ e.category }}</td><td>{{ '%.2f'|format(e.amount) }}</td><td>{{ e.note }}</td></tr>
{% endfor %}
</table>
</div>
"""


@bp.route("/budget")
def budget_page():
    entries = list(reversed(budget.entries()))[:200]
    return render_page("Budget", "web.budget_page", BUDGET_TPL,
                       totals=budget.totals(), vat_due=taxes.vat_due(), entries=entries)


# --- recensioni (TrustHotel) ---------------------------------------------------

REVIEWS_TPL = """
<div class="card">
<h2>TrustHotel &mdash; {{ hotel_name }} {{ '★' * tier }} ({{ tier }} stelle)</h2>
<p>Rating ospiti: {{ '★' * stars_round }}{{ '☆' * (5 - stars_round) }}
   {{ reputation }}/5 &mdash; Domanda attuale: x{{ '%.2f'|format(demand) }}</p>
{% if not reviews %}<p>Ancora nessuna recensione.</p>{% endif %}
{% if reviews %}
<table>
<tr><th>Data</th><th>Ospite</th><th>Stelle</th><th>Recensione</th></tr>
{% for r in reviews %}
<tr><td>{{ r.day }}</td><td>{{ r.guest }}</td><td>{{ '★' * r.stars }}</td><td>{{ r.text }}</td></tr>
{% endfor %}
</table>
{% endif %}
</div>
"""


@bp.route("/reviews")
def reviews_page():
    rep = reviews.reputation()
    return render_page("Recensioni", "web.browser_page", REVIEWS_TPL, tier=amenities.tier(),
                       reputation=rep, stars_round=round(rep), demand=mail.demand_factor(),
                       reviews=reviews.all_reviews())


# --- to do ---------------------------------------------------------------------

PROBLEMS_TPL = """
<div class="card">
<h2>To Do</h2>
<table>
<tr><th>Problema</th><th>Rimedio</th><th>Stato</th><th></th></tr>
{% for p in items %}
<tr {{ 'style="color:#888;text-decoration:line-through"' if p.done else '' }}>
<td>{{ p.desc }}</td><td>{{ p.fix_label }}</td><td>{{ 'Risolto' if p.done else 'APERTO' }}</td>
<td>{% if not p.done %}
<form method="post" action="{{ url_for('web.problems_resolve', problem_id=p.id) }}">
  {% if p.needs_operator %}<select name="operator_id">
    {% for op in cleaners %}<option value="{{ op.id }}">{{ op.first_name }} {{ op.last_name }}</option>{% endfor %}
  </select>{% endif %}
  <button {{ 'disabled' if p.needs_operator and not cleaners else '' }}>Risolvi</button>
</form>{% endif %}</td>
</tr>
{% endfor %}
</table>
{% if problems_msg %}<p class="msg">{{ problems_msg }}</p>{% endif %}
</div>
"""


def _problems_page(msg=None):
    items = []
    for p in problems.todo_list():
        kind, amount = problems.PROBLEMS[p["key"]]["fix"]
        fix_label = (f"Ripara: € {amount:g}" if kind == "money" else f"Pulizie: {amount:g}h")
        items.append({**dict(p), "desc": problems.describe(p), "fix_label": fix_label,
                     "done": p["resolved_at"] is not None, "needs_operator": kind == "cleaning"})
    cleaners = [e for e in staff.all_employees() if e["role"] == staff.ROLE_CLEANING]
    return render_page("To Do", "web.problems_page", PROBLEMS_TPL,
                       items=items, cleaners=cleaners, problems_msg=msg)


@bp.route("/problems")
def problems_page():
    return _problems_page()


@bp.route("/problems/<int:problem_id>/resolve", methods=["POST"])
def problems_resolve(problem_id):
    operator_id = request.form.get("operator_id", type=int)
    try:
        problems.resolve(problem_id, operator_id=operator_id)
    except (problems.ProblemError, estate.EstateError) as exc:
        return _problems_page(msg=str(exc))
    return redirect(url_for("web.problems_page"))


# --- fogli (pulizie / pasti) ---------------------------------------------------

REPORTS_TPL = """
<div class="card">
<h2>Fogli</h2>
<form method="get">
  <select name="type">
    {% for key, label in types %}<option value="{{ key }}" {{ 'selected' if key == sel_type }}>{{ label }}</option>{% endfor %}
  </select>
  <input type="date" name="date" value="{{ sel_date }}">
  <button>Genera</button>
</form>
<pre>{{ sheet }}</pre>
</div>
"""


@bp.route("/reports")
def reports_page():
    types = [("pulizie", "Foglio pulizie"), ("colazione", "Colazione"),
             ("pranzo", "Pranzo"), ("cena", "Cena")]
    sel_type = request.args.get("type", "pulizie")
    sel_date = request.args.get("date", clock.today().isoformat())
    try:
        day = date.fromisoformat(sel_date)
        sheet = (cleaning.sheet_text(day) if sel_type == "pulizie"
                 else meals.sheet_text(sel_type, day))
    except (ValueError, KeyError):
        sheet = "Data o tipo non validi."
    return render_page("Fogli", "web.reports_page", REPORTS_TPL, live=False,
                       types=types, sel_type=sel_type, sel_date=sel_date, sheet=sheet)


# --- sala pasti ----------------------------------------------------------------

DINING_TPL = """
<div class="card">
<h2>Sala pasti</h2>
<p>{{ header }}</p>
<p style="font-size:12px;color:#555">Trascina un tavolo su una cella libera per
  spostarlo. Compra tavoli piccoli e grandi e sedie dalle
  <a href="{{ url_for('web.estate_page') }}">Ristrutturazioni</a>.</p>
<div class="dgrid">
  {% for cell in cells %}
  <div class="dcell" data-col="{{ cell.col }}" data-row="{{ cell.row }}">
    {% if cell.table %}
    <div class="dtable {{ cell.table.kind }}" draggable="true" data-table="{{ cell.table.id }}">
      <div class="top-chairs">
        {% for i in range(cell.top) %}<span class="chair{{ ' busy' if loop.index0 < cell.occupied }}"></span>{% endfor %}
      </div>
      <div class="surface">{{ 'Cam. ' ~ cell.room if cell.room else 'Tavolo ' ~ cell.table.id }}</div>
      <div class="bot-chairs">
        {% for i in range(cell.bottom) %}<span class="chair{{ ' busy' if (cell.top + loop.index0) < cell.occupied }}"></span>{% endfor %}
      </div>
    </div>
    {% endif %}
  </div>
  {% endfor %}
</div>
</div>
<script>
(function(){
  let dragged = null;
  document.querySelectorAll(".dtable[draggable=true]").forEach(t => {
    t.addEventListener("dragstart", () => { dragged = t.dataset.table; });
    t.addEventListener("dragend", () => {
      dragged = null;
      document.querySelectorAll(".dcell.drop").forEach(c => c.classList.remove("drop"));
    });
  });
  document.querySelectorAll(".dcell").forEach(cell => {
    cell.addEventListener("dragover", e => { if (dragged) { e.preventDefault(); cell.classList.add("drop"); } });
    cell.addEventListener("dragleave", () => cell.classList.remove("drop"));
    cell.addEventListener("drop", e => {
      e.preventDefault();
      cell.classList.remove("drop");
      if (!dragged) return;
      const body = new FormData();
      body.append("table_id", dragged);
      body.append("col", cell.dataset.col);
      body.append("row", cell.dataset.row);
      fetch("{{ url_for('web.dining_move') }}", { method: "POST", body })
        .then(r => r.json())
        .then(d => { if (d && d.error) alert(d.error); location.reload(); })
        .catch(() => location.reload());
      dragged = null;
    });
  });
})();
</script>
"""


def _dining_page():
    now = clock.now()
    meal, placements, waiting = dining.seating(now)
    if meal is None:
        header = "Nessun pasto in corso"
    else:
        seated = sum(len(m) for _r, m in placements.values())
        header = f"{meal} — a tavola: {seated}"
        if waiting:
            header += "  |  in attesa (senza tavolo): camere " + ", ".join(
                str(m[0]["room_number"]) for _r, m in waiting)
    # celle della griglia col x row: il tavolo che occupa quella cella, con le
    # sedie divise fra bordo alto e basso (top = meta arrotondata per eccesso)
    by_pos = {(t["col"], t["row"]): t for t in dining.tables()}
    cells = []
    for row in range(dining.GRID_ROWS):
        for col in range(dining.GRID_COLS):
            t = by_pos.get((col, row))
            placed = placements.get(t["id"]) if t else None
            chairs = t["chairs"] if t else 0
            top = (chairs + 1) // 2
            cells.append({"col": col, "row": row, "table": t, "top": top,
                          "bottom": chairs - top,
                          "occupied": len(placed[1]) if placed else 0,
                          "room": placed[1][0]["room_number"] if placed else None})
    return render_page("Sala pasti", "web.dining_page", DINING_TPL, live=False,
                       header=header, cells=cells, dining_cols=dining.GRID_COLS)


@bp.route("/dining")
def dining_page():
    return _dining_page()


@bp.route("/dining/move", methods=["POST"])
def dining_move():
    """Spostamento tavolo via drag&drop (JSON, chiamato in fetch)."""
    try:
        dining.move_table(int(request.form["table_id"]), int(request.form["col"]),
                          int(request.form["row"]))
    except (dining.DiningError, ValueError, KeyError) as exc:
        return {"error": str(exc) or "Spostamento non valido."}, 400
    return {"ok": True}


# --- browser hub ---------------------------------------------------------------

BROWSER_TPL = """
<div class="card">
<h2>Browser</h2>
<div class="apps">
  <a href="{{ url_for('web.mail_page') }}">&#9993; Mail</a>
  <a href="{{ url_for('web.estate_page') }}">&#127959; Ristrutturazioni</a>
  <a href="{{ url_for('web.allfoods_page') }}">&#129386; AllFoods!</a>
  <a href="{{ url_for('web.reviews_page') }}">&#11088; TrustHotel</a>
  <a href="{{ url_for('web.staff_page') }}">&#128188; JobHotel</a>
  <a href="{{ url_for('web.bank_page') }}">&#127974; Banca di Aurora</a>
  <a href="{{ url_for('web.help_page') }}">&#128218; Istruzioni</a>
</div>
</div>
<div class="card">
<h3>Booking</h3>
<form method="post">
  <label><input type="checkbox" name="block" onchange="this.form.submit()"
    {{ 'checked' if blocked }}> Blocca l'arrivo di nuove prenotazioni</label>
</form>
</div>
"""


@bp.route("/browser", methods=["GET", "POST"])
def browser_page():
    if request.method == "POST":
        mail.config.block_new_bookings = "block" in request.form
        return redirect(url_for("web.browser_page"))
    return render_page("Browser", "web.browser_page", BROWSER_TPL,
                       blocked=mail.config.block_new_bookings)


# --- mail ----------------------------------------------------------------------

MAIL_TPL = """
<div class="card">
<h2>Mail</h2>
<form method="get">
  <input name="q" value="{{ q }}" placeholder="Cerca...">
  <label><input type="checkbox" name="archived" value="1" onchange="this.form.submit()" {{ 'checked' if archived }}> Archiviate</label>
  <button>Cerca</button>
</form>
{% if not mails %}<p>Nessuna email.</p>{% endif %}
{% if mails %}
<table>
<tr><th>Ricevuta</th><th>Mittente</th><th>Oggetto</th><th>Stato</th><th></th></tr>
{% for m in mails %}
<tr>
  <td>{{ m.received }}</td><td>{{ m.sender }}</td>
  <td><a href="{{ url_for('web.mail_view', mail_id=m.id) }}">{{ m.subject }}</a></td>
  <td>{{ m.status }}</td>
  <td>
    <form method="post" action="{{ url_for('web.mail_action', mail_id=m.id, action='archive') }}" style="display:inline"><button>Archivia</button></form>
    <form method="post" action="{{ url_for('web.mail_action', mail_id=m.id, action='delete') }}" style="display:inline" onsubmit="return confirm('Eliminare?')"><button>Elimina</button></form>
  </td>
</tr>
{% endfor %}
</table>
{% endif %}
</div>
"""


@bp.route("/mail")
def mail_page():
    q = request.args.get("q", "")
    archived = request.args.get("archived") == "1"
    mails = [{**dict(m), "status": mail.status(m),
              "received": m["received_at"][:16].replace("T", " ")}
             for m in mail.search_mails(q, archived)]
    return render_page("Mail", "web.mail_page", MAIL_TPL, mails=mails, q=q, archived=archived)


MAIL_VIEW_TPL = """
<div class="card">
<h2>{{ m.subject }}</h2>
<p>Da: {{ m.sender }} &mdash; Ricevuta: {{ m.received }} &mdash; Stato: <b>{{ m.status }}</b></p>
<pre>{{ m.body }}</pre>
{% if m.status == 'Da gestire' %}
<form method="post" action="{{ url_for('web.mail_action', mail_id=m.id, action='insert') }}" style="display:inline"><button>Inserisci prenotazione</button></form>
<form method="post" action="{{ url_for('web.mail_action', mail_id=m.id, action='reject') }}" style="display:inline"><button>Rifiuta</button></form>
{% endif %}
<a class="btn" href="{{ url_for('web.mail_page') }}">Torna alla casella</a>
{% if mail_msg %}<p class="msg">{{ mail_msg }}</p>{% endif %}
{% if mail_ok %}<p style="color:#2e7d32;font-weight:600">{{ mail_ok }}</p>{% endif %}
</div>
"""


def _mail_view(mail_id, msg=None, ok=None):
    m = mail.get(mail_id)
    if m is None:
        return redirect(url_for("web.mail_page"))
    ctx = {**dict(m), "status": mail.status(m),
           "received": m["received_at"][:16].replace("T", " ")}
    return render_page(m["subject"], "web.mail_page", MAIL_VIEW_TPL, live=False,
                       m=ctx, mail_msg=msg, mail_ok=ok)


@bp.route("/mail/<int:mail_id>")
def mail_view(mail_id):
    return _mail_view(mail_id)


@bp.route("/mail/<int:mail_id>/<action>", methods=["POST"])
def mail_action(mail_id, action):
    if action == "insert":
        try:
            room = mail.insert(mail_id)
        except reservations.ValidationError as exc:
            return _mail_view(mail_id, msg=str(exc))
        return _mail_view(mail_id, ok=f"Prenotazione inserita in camera {room}.")
    if action == "reject":
        mail.reject(mail_id)
        return _mail_view(mail_id)
    if action == "archive":
        mail.archive(mail_id)
    elif action == "delete":
        mail.delete(mail_id)
    return redirect(url_for("web.mail_page"))


# --- AllFoods! -----------------------------------------------------------------

ALLFOODS_TPL = """
<div class="card">
<h2>AllFoods!</h2>
<p><b>Dispensa: {{ food }} / {{ cap }}</b> &mdash; 1 unita = 1 pasto servito</p>
<form method="post">
  <label>Unita (&euro; {{ '%.0f'|format(unit_cost) }} l'una):
    <input type="number" name="units" min="1" value="10" style="width:70px"></label>
  <button>Compra</button>
</form>
{% if food_msg %}<p class="msg">{{ food_msg }}</p>{% endif %}
</div>
"""


@bp.route("/allfoods", methods=["GET", "POST"])
def allfoods_page():
    msg = None
    if request.method == "POST":
        try:
            estate.buy_food(request.form.get("units", type=int) or 0)
        except estate.EstateError as exc:
            msg = str(exc)
    return render_page("AllFoods!", "web.browser_page", ALLFOODS_TPL, food=estate.food(),
                       cap=estate.food_cap(), unit_cost=estate.FOOD_UNIT_COST, food_msg=msg)


# --- ristrutturazioni ----------------------------------------------------------

ESTATE_TPL = """
<div class="card">
<h2>Ristrutturazioni</h2>
{% if estate_msg %}<p class="msg">{{ estate_msg }}</p>{% endif %}
<h3>Piani</h3>
{% for fl, n in floors %}<p>Piano {{ fl }}: {{ n }}/{{ max_per_floor }} camere</p>{% endfor %}
<form method="post"><input type="hidden" name="action" value="floor">
  <button>Compra piano {{ next_floor }} &mdash; &euro; {{ '%.0f'|format(floor_cost) }}</button></form>
<h3>Acquista camera</h3>
<form method="post"><input type="hidden" name="action" value="room">
  <label>Piano: <select name="floor">{% for fl in free_floors %}<option>{{ fl }}</option>{% endfor %}</select></label>
  <label><input type="radio" name="suite" value="0" checked> Normale &mdash; &euro; {{ '%.2f'|format(room_cost) }}</label>
  <label><input type="radio" name="suite" value="1"> Suite &mdash; &euro; {{ '%.2f'|format(suite_cost) }}</label>
  <button {{ 'disabled' if not free_floors }}>Compra camera</button></form>
<h3>Dispensa</h3>
<p>Capienza: {{ food_cap }} unita (cibo: {{ food }})</p>
<form method="post"><input type="hidden" name="action" value="foodcap">
  <button>Aumenta capienza (+{{ cap_step }}) &mdash; &euro; {{ '%.2f'|format(foodcap_cost) }}</button></form>
<h3>Sala pasti</h3>
<p>Tavoli: {{ dining_counts.tavoli }} &mdash; Sedie/posti: {{ dining_counts.sedie }}</p>
<form method="post" style="display:inline"><input type="hidden" name="action" value="table"><input type="hidden" name="kind" value="single">
  <button>Tavolo singolo &mdash; &euro; {{ '%.0f'|format(table_costs.single) }}</button></form>
<form method="post" style="display:inline"><input type="hidden" name="action" value="table"><input type="hidden" name="kind" value="double">
  <button>Tavolo doppio &mdash; &euro; {{ '%.0f'|format(table_costs.double) }}</button></form>
<form method="post" style="display:inline"><input type="hidden" name="action" value="chair">
  <button>Sedia &mdash; &euro; {{ '%.0f'|format(chair_cost) }}</button></form>
<h3>Rinnovo camere logore</h3>
{% if not worn %}<p>Nessuna camera da rinnovare.</p>{% endif %}
{% if worn %}
<form method="post"><input type="hidden" name="action" value="renovate">
  <label>Camera: <select name="number">{% for n in worn %}<option>{{ n }}</option>{% endfor %}</select></label>
  <button>Rinnova &mdash; &euro; {{ '%.0f'|format(renovate_cost) }}</button></form>
{% endif %}
</div>
<div class="card">
<h3>Categoria e servizi</h3>
<p><b>Categoria: {{ '★' * tier }}{{ '☆' * (5 - tier) }} ({{ tier }} stelle)</b></p>
<p>{{ 'Categoria massima raggiunta.' if not missing else 'Per la prossima stella: ' + missing|join(', ') }}</p>
{% for a in amenity_rows %}
<form method="post" style="margin:3px 0"><input type="hidden" name="action" value="amenity"><input type="hidden" name="key" value="{{ a.key }}">
  <button {{ 'disabled' if a.owned }}>{{ '✓ ' + a.label if a.owned else a.label + ' — € ' + '%.0f'|format(a.cost) }}</button></form>
{% endfor %}
<h3>Upgrade camere (prezzi e costi di tutto l'hotel)</h3>
{% for lv in level_rows %}
<form method="post" style="margin:3px 0"><input type="hidden" name="action" value="upgrade"><input type="hidden" name="level" value="{{ lv.level }}">
  <button {{ 'disabled' if lv.done or not lv.next }}>{{ '✓ ' + lv.label if lv.done else lv.label + ' (x' + lv.mult + ') — € ' + '%.0f'|format(lv.cost) }}</button></form>
{% endfor %}
</div>
"""

_ESTATE_ACTIONS = {
    "floor": lambda f: estate.buy_floor(),
    "room": lambda f: estate.buy_room(int(f["floor"]), f.get("suite") == "1"),
    "foodcap": lambda f: estate.upgrade_food_cap(),
    "table": lambda f: dining.buy_table(f["kind"]),
    "chair": lambda f: dining.buy_chair(),
    "renovate": lambda f: estate.renovate_room(int(f["number"])),
    "amenity": lambda f: amenities.buy(f["key"]),
    "upgrade": lambda f: amenities.buy_room_upgrade(int(f["level"])),
}


@bp.route("/estate", methods=["GET", "POST"])
def estate_page():
    msg = None
    if request.method == "POST":
        try:
            _ESTATE_ACTIONS[request.form["action"]](request.form)
        except (estate.EstateError, ValueError, KeyError) as exc:
            msg = str(exc) or "Selezione non valida."
    floors = [(fl, estate.floor_room_count(fl)) for fl in estate.owned_floors()]
    own, lvl = amenities.owned(), amenities.room_level()
    amenity_rows = [{"key": k, "label": a["label"], "cost": a["cost"], "owned": k in own}
                    for k, a in amenities.AMENITIES.items()]
    level_rows = [{"level": lv, "label": info["label"], "mult": f"{info['mult']:g}",
                   "cost": amenities.room_upgrade_cost(lv), "done": lvl >= lv, "next": lvl == lv - 1}
                  for lv, info in amenities.ROOM_LEVELS.items()]
    return render_page(
        "Ristrutturazioni", "web.browser_page", ESTATE_TPL, estate_msg=msg,
        floors=floors, max_per_floor=estate.MAX_ROOMS_PER_FLOOR,
        next_floor=estate.next_floor_number(), floor_cost=estate.FLOOR_COST,
        free_floors=[fl for fl, n in floors if n < estate.MAX_ROOMS_PER_FLOOR],
        room_cost=estate.room_cost(False), suite_cost=estate.room_cost(True),
        food=estate.food(), food_cap=estate.food_cap(), cap_step=estate.FOOD_CAP_STEP,
        foodcap_cost=estate.food_cap_upgrade_cost(), dining_counts=dining.counts(),
        table_costs=dining.TABLE_COSTS, chair_cost=dining.CHAIR_COST,
        worn=[r["number"] for r in rooms.worn_rooms()], renovate_cost=estate.RENOVATE_COST,
        tier=amenities.tier(), missing=amenities.missing_for_next(),
        amenity_rows=amenity_rows, level_rows=level_rows)


# --- impostazioni / debug ------------------------------------------------------

DEBUG_TPL = """
<div class="card">
<h2>Impostazioni</h2>
{% if debug_msg %}<p class="msg">{{ debug_msg }}</p>{% endif %}

<h3>Tempo simulato</h3>
<form method="post"><input type="hidden" name="action" value="time">
  <label><input type="checkbox" name="running" {{ 'checked' if running }}> Avanzamento tempo attivo</label>
  <label>Scala (ore gioco / 1h reale): <input name="scale" value="{{ '%g'|format(scale_val) }}" style="width:70px"></label>
  <button>Applica</button></form>

<h3>Data attuale</h3>
<form method="post"><input type="hidden" name="action" value="setdate">
  <input type="date" name="date" value="{{ today_iso }}"> <button>Imposta data</button></form>
<form method="post"><input type="hidden" name="action" value="resetdate"><button>Reset a oggi reale</button></form>

<h3>Genera prenotazioni</h3>
<form method="post"><input type="hidden" name="action" value="generate">
  <label>Numero: <input type="number" name="count" value="30" style="width:70px"></label>
  <label>Da <input type="date" name="start" value="{{ today_iso }}"></label>
  <label>a <input type="date" name="end" value="{{ end_iso }}"></label>
  <label>Notti min <input type="number" name="min_nights" value="1" style="width:55px"></label>
  <label>max <input type="number" name="max_nights" value="7" style="width:55px"></label>
  <label><input type="checkbox" name="random_colors" checked> colori casuali</label>
  <label><input type="checkbox" name="auto_checkin" checked> check-in auto oggi</label>
  <button>Genera</button></form>
<form method="post" onsubmit="return confirm('Svuotare prenotazioni e ospiti?')"><input type="hidden" name="action" value="clear"><button>Svuota database</button></form>

<h3>Gameplay email</h3>
<form method="post"><input type="hidden" name="action" value="mail">
  <label><input type="checkbox" name="enabled" {{ 'checked' if mail_cfg.enabled }}> arrivo email</label>
  <label><input type="checkbox" name="auto_insert" {{ 'checked' if mail_cfg.auto_insert }}> inserimento automatico</label>
  <label>Intervallo (s): <input name="interval" value="{{ mail_cfg.interval_seconds }}" style="width:60px"></label>
  <label>Prob. standard: <input name="prob" value="{{ mail_cfg.probability }}" style="width:60px"></label>
  <label>Finestra (giorni): <input name="window" value="{{ mail_cfg.window_days }}" style="width:60px"></label>
  <button>Applica</button></form>
<form method="post" style="display:inline"><input type="hidden" name="action" value="spawnmail"><button>Crea email ora</button></form>

<h3>Cibo</h3>
<form method="post"><input type="hidden" name="action" value="food">
  <label>Unita possedute (max {{ food_cap }}): <input type="number" name="food" value="{{ food }}" style="width:70px"></label>
  <button>Applica</button></form>

<h3>Budget manuale</h3>
<form method="post"><input type="hidden" name="action" value="budget">
  <select name="kind"><option value="income">Introito</option><option value="loss">Perdita</option></select>
  <input name="category" placeholder="Categoria" value="Bolletta">
  <input name="amount" placeholder="Importo" value="0" style="width:80px">
  <input name="note" placeholder="Nota">
  <button>Aggiungi</button></form>

<h3>Ospiti</h3>
<a class="btn" href="{{ url_for('web.guests_meta') }}">Metadati ospiti</a>

<h3>Salvataggio</h3>
<a class="btn" href="{{ url_for('web.debug_export') }}">Esporta salvataggio (.db)</a>

<h3>Sistema</h3>
<form method="post" onsubmit="return confirm('Cancellare TUTTO e tornare al primo avvio?')"><input type="hidden" name="action" value="resetall"><button>Reset totale</button></form>
</div>
"""


@bp.route("/debug")
def debug_page():
    return render_page(
        "Impostazioni", "web.debug_page", DEBUG_TPL, live=False,
        running=clock.running, scale_val=clock.scale, today_iso=clock.today().isoformat(),
        end_iso=(clock.today() + timedelta(days=14)).isoformat(),
        mail_cfg=mail.config, food=estate.food(), food_cap=estate.food_cap())


def _debug_generate(f):
    cfg = debug_seed.SeedConfig(
        count=max(1, int(f.get("count", 1))),
        start=date.fromisoformat(f["start"]), end=date.fromisoformat(f["end"]),
        min_nights=max(1, int(f.get("min_nights", 1))),
        max_nights=max(1, int(f.get("max_nights", 1))),
        random_colors="random_colors" in f, auto_checkin="auto_checkin" in f)
    debug_seed.seed_reservations(cfg)


def _debug_mail(f):
    mail.config.enabled = "enabled" in f
    mail.config.auto_insert = "auto_insert" in f
    mail.config.interval_seconds = max(int(f.get("interval", 60) or 60), 1)
    mail.config.probability = min(max(float(f.get("prob", 0.5) or 0.5), 0.0), 1.0)
    mail.config.window_days = max(int(f.get("window", 5) or 5), 0)


@bp.route("/debug", methods=["POST"])
def debug_action():
    f = request.form
    action = f.get("action")
    try:
        if action == "time":
            clock.scale = float(f.get("scale", clock.scale).replace(",", "."))
            clock.running = "running" in f
        elif action == "setdate":
            clock.set_today(date.fromisoformat(f["date"]))
        elif action == "resetdate":
            clock.set_today(None)
        elif action == "generate":
            _debug_generate(f)
        elif action == "clear":
            debug_seed.clear_all()
        elif action == "mail":
            _debug_mail(f)
        elif action == "spawnmail":
            mail.spawn()
        elif action == "food":
            estate.set_food(int(f.get("food", 0)))
        elif action == "budget":
            budget.record(f.get("kind", "income"), f.get("category", "").strip() or "Voce",
                          float(f.get("amount", 0).replace(",", ".")), f.get("note", "").strip())
        elif action == "resetall":
            estate.reset_all()
            return redirect(url_for("web.setup"))
    except (ValueError, KeyError, estate.EstateError):
        pass   # ponytail: azioni di debug, errore silenzioso (nessun flash store)
    return redirect(url_for("web.debug_page"))


GUESTS_META_TPL = """
<div class="card">
<h2>Metadati ospiti</h2>
{% if not rows %}<p>Nessun ospite registrato.</p>{% endif %}
{% if rows %}
<table>
<tr><th>Ospite</th><th>Nascita</th><th>Ora sonno (base)</th><th>Ore sonno</th></tr>
{% for r in rows %}
<tr><td>{{ r.name }}</td><td>{{ r.birth }}</td><td>{{ r.sleep }}</td><td>{{ r.wake }}</td></tr>
{% endfor %}
</table>
{% endif %}
<a class="btn" href="{{ url_for('web.debug_page') }}">Torna alle impostazioni</a>
</div>
"""


@bp.route("/debug/guests-meta")
def guests_meta():
    rows = []
    for gu in guests.all_guests():
        meta = guest_state.metadata(gu["id"])
        rows.append({"name": f"{gu['last_name']} {gu['first_name']}".strip(),
                     "birth": gu["birth_date"] or "n.d.",
                     "sleep": guest_state.sleep_base_str(gu["id"]), "wake": meta["wake_hours"]})
    return render_page("Metadati ospiti", "web.debug_page", GUESTS_META_TPL, live=False, rows=rows)


@bp.route("/debug/export")
def debug_export():
    path = session_state.DATA_DIR / f"{session['sid']}.db"
    return send_file(path, as_attachment=True, download_name="hotelaurora_salvataggio.db")


# --- istruzioni ----------------------------------------------------------------

HELP_TPL = """
<div class="card">
<h2>Istruzioni</h2>
<pre>{{ text }}</pre>
</div>
"""

INSTRUCTIONS = """\
HOTELAURORA SIMULATOR — ISTRUZIONI

OBIETTIVO
Gestisci il tuo hotel: accetta prenotazioni, accogli gli ospiti, paga
dipendenti, tasse e bollette, e fai crescere categoria (stelle) e rating.
Si parte con 10 camere (2 suite), 10.000 euro, 1 addetto pulizie, 2 operatori
di sala e 1 receptionist a scelta tra 4.

TEMPO
La barra in alto mostra data/ora simulate e il turno. Controlli: Pausa, Play,
T (tempo reale), 1x/2x/5x. Il tempo avanza lato server anche senza ricaricare.

PRENOTAZIONI
- Le richieste arrivano per email (tab Mail): Inserisci o Rifiuta. Scadono
  dopo 48 ore o superata la data di check-in.
- "Nuova prenotazione" (tab Camere) inserisce a mano; il prezzo per notte e
  di mercato (listino soluzione x upgrade camere).
- Nella Timeline sposti una prenotazione non ancora arrivata su un'altra
  camera, a parita di date.

OSPITI E RECEPTION
- Gli arrivi compaiono in Reception (Pomeriggio/Sera): fai il check-in. Oltre
  1,5h di attesa l'ospite si arrabbia, annulla e ti stronca.
- Alla partenza scendono per il check-out: incassi il conto (l'IVA si versa a
  fine mese). Chi sfora oltre le 14:30 esce d'ufficio senza pagare.
- La tab Occupazione mostra chi e in camera (pallino per ospite); clicca per
  le info (stato, locazione, emozione).

PASTI E CIBO
- I pasti dipendono dalla soluzione. Ogni pasto consuma 1 unita di cibo
  (Browser > AllFoods!, 10 euro/unita). La sala pasti ha tavoli e sedie.
- Se manca cibo, posto o personale l'ospite si lamenta in Reception (Parla).

DIPENDENTI
- Pulizie (7-15) e sala (assegnati ai pasti). Foglio ore e stipendi il 20 del
  mese. Receptionist con bonus passivo si assumono da JobHotel (prova 3 mesi).

ECONOMIA
- Budget: entrate e uscite. A fine mese: IVA, rate prestiti e bollette.
- Banca: prestiti 5.000/15.000/40.000, 12 rate, max 3 aperti.

CRESCITA
- Ristrutturazioni: camere, piani, dispensa, tavoli, rinnovi e servizi.
- Categoria (1-5 stelle) da camere e servizi. Rating (TrustHotel) da 3.

IMPOSTAZIONI
Velocita del tempo, data, generatore prenotazioni, budget manuale, email,
cibo, metadati ospiti, esporta salvataggio e Reset totale.
"""


@bp.route("/help")
def help_page():
    return render_page("Istruzioni", "web.browser_page", HELP_TPL, live=False,
                       text=INSTRUCTIONS)
