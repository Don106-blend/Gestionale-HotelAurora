"""Layout condiviso e helper di rendering: niente file .html, i template sono
stringhe Jinja2 (render_template_string) per restare senza build step."""

from flask import render_template_string
from markupsafe import Markup

NAV = (
    ("web.dashboard", "Camere"),
    ("web.timeline_page", "Timeline"),
    ("web.occupancy", "Occupazione"),
    ("web.dining_page", "Sala pasti"),
    ("web.reception_page", "Reception"),
    ("web.mail_page", "Mail"),
    ("web.staff_page", "Dipendenti"),
    ("web.problems_page", "To Do"),
    ("web.budget_page", "Budget"),
    ("web.reports_page", "Fogli"),
    ("web.browser_page", "Browser"),
    ("web.debug_page", "Impostazioni"),
)

BASE = """
<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} - {{ hotel_name }}</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: system-ui, sans-serif; background: #eceff1; color: #222; }
  header.topbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
    background: #263238; color: #eceff1; padding: 8px 16px; }
  header.topbar b { color: #fff; }
  header.topbar form { display: inline-flex; gap: 2px; margin: 0; }
  header.topbar a.msg { color: #ffd54f; text-decoration: none; font-weight: 600; }
  .shift-pill { padding: 2px 10px; border-radius: 10px; color: #222; font-weight: 600; }
  nav.tabs { display: flex; flex-wrap: wrap; background: #37474f; }
  nav.tabs a { color: #cfd8dc; text-decoration: none; padding: 10px 14px; font-size: 14px; }
  nav.tabs a.active { background: #eceff1; color: #222; font-weight: 700; }
  main { padding: 16px; max-width: 1200px; margin: 0 auto; }
  table { border-collapse: collapse; width: 100%; background: #fff; }
  th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; font-size: 14px; }
  th { background: #eceff1; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; }
  .room { position: relative; display: block; text-decoration: none; color: #222;
    border-radius: 6px; padding: 6px; min-height: 62px; border: 1px solid #555;
    font-size: 12px; line-height: 1.3; overflow: hidden; }
  .room .num { font-weight: 700; }
  .room .m-checkout { position: absolute; top: 0; right: 0; width: 10px; height: 100%;
    background: #e3d27a; }
  .room .m-dirty { position: absolute; left: 4px; right: 4px; bottom: 4px; height: 3px;
    background: #8a8a8a; }
  .room .m-blocked { position: absolute; left: 4px; right: 4px; top: 4px; height: 3px;
    background: #b03030; }
  .room .m-wear { position: absolute; left: 4px; top: 6px; bottom: 6px; width: 3px;
    background: #e07b00; }
  .room .m-arr-today { position: absolute; top: 3px; right: 3px; width: 12px; height: 12px;
    background: #cc2e88; border: 1px solid #555; }
  .room .m-arr-next { position: absolute; bottom: 3px; right: 3px; width: 12px; height: 12px;
    background: #2d6cdf; border: 1px solid #555; }
  .msg { color: #b71c1c; font-weight: 600; }
  .card { background: #fff; border-radius: 8px; padding: 12px 16px; margin-bottom: 14px;
    box-shadow: 0 1px 3px rgba(0,0,0,.15); }
  button, .btn { background: #37474f; color: #fff; border: none; border-radius: 4px;
    padding: 6px 12px; cursor: pointer; font-size: 13px; text-decoration: none;
    display: inline-block; }
  button:disabled { opacity: .35; cursor: default; }
  input, select { padding: 4px 6px; }
  pre { white-space: pre-wrap; background: #fafafa; border: 1px solid #ddd;
    padding: 12px; border-radius: 6px; font-family: "Courier New", monospace; font-size: 13px; }
  /* --- Occupazione: visione termica --- */
  .thermal { background: #000; padding: 16px; border-radius: 8px; }
  .thermal .legend { height: 14px; border-radius: 7px; margin: 0 0 6px;
    background: linear-gradient(90deg, #0057ff, #00c878, #ffd600, #ff1744); }
  .thermal .legkey { color: #bbb; font-size: 12px; margin-bottom: 14px; }
  .thermal .room { border-color: #333; color: #fff; text-shadow: 0 0 4px #000;
    background: #101418; }
  .dots { display: flex; gap: 4px; margin-top: 6px; flex-wrap: wrap; }
  .dot { width: 12px; height: 12px; border-radius: 50%; border: 1px solid #222; }
  /* --- Timeline --- */
  .tl { overflow-x: auto; }
  .tl table { border-collapse: collapse; background: #fff; }
  .tl td, .tl th { border: 1px solid #eee; padding: 0; font-size: 11px; text-align: center;
    min-width: 30px; height: 22px; }
  .tl th.room, .tl td.room { min-width: 48px; font-weight: 700; text-align: left;
    padding: 0 4px; position: sticky; left: 0; background: #fff; }
  .tl td.today { background: #eef3e8; }
  .tl .bar { height: 18px; border-radius: 3px; border: 1px solid #666; margin: 1px 0;
    font-size: 10px; color: #222; overflow: hidden; white-space: nowrap; padding: 0 2px; }
  .tl .bar.movable { cursor: grab; }
  .tl .bar.movable:active { cursor: grabbing; }
  .tl tr.drop td { background: #dbeafe; }
  /* --- Bentornato Direttore --- */
  .welcome-banner { position: relative; max-width: 1200px; margin: 12px auto 0;
    background: linear-gradient(135deg, #1b5e20, #2e7d32); color: #fff;
    padding: 16px 20px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,.25); }
  .welcome-banner h2 { margin: 0 0 6px; }
  .welcome-banner p { margin: 3px 0; }
  .welcome-banner .wb-x { position: absolute; top: 8px; right: 10px;
    background: transparent; font-size: 20px; line-height: 1; padding: 2px 8px; }
  /* --- Sala pasti: tavoli con sedie, piccoli (single) e grandi (double) --- */
  .dgrid { display: grid; grid-template-columns: repeat({{ dining_cols|default(6) }}, 1fr);
    gap: 10px; background: #e8eef0; padding: 12px; border-radius: 8px; }
  .dcell { min-height: 104px; border: 1px dashed #c3ccd2; border-radius: 8px;
    display: flex; align-items: center; justify-content: center; }
  .dcell.drop { background: #dbeafe; }
  .dtable { cursor: grab; display: flex; flex-direction: column; align-items: center; gap: 3px; }
  .dtable:active { cursor: grabbing; }
  .dtable .top-chairs, .dtable .bot-chairs { display: flex; gap: 6px; }
  .dtable .surface { background: linear-gradient(#c8945a, #a9743f); color: #fff;
    border: 2px solid #7a4e26; border-radius: 6px; padding: 10px 12px; font-size: 11px;
    font-weight: 700; text-align: center; min-width: 52px; }
  .dtable.double .surface { min-width: 96px; padding: 14px 22px; }
  .chair { width: 12px; height: 12px; background: #cfd8dc; border: 1px solid #90a4ae;
    border-radius: 50% 50% 3px 3px; }
  .chair.busy { background: #ffd600; border-color: #c8a900; }
  .apps { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
  .apps a { display: block; background: #37474f; color: #fff; text-decoration: none;
    text-align: center; padding: 34px 10px; border-radius: 8px; font-size: 15px; font-weight: 600; }
</style>
</head>
<body>
<header class="topbar">
  <b>{{ hotel_name }}</b>
  <span>{{ now_str }}</span>
  <span class="shift-pill" style="background: {{ shift_color }}">{{ shift_name }}</span>
  <span>Saldo: &euro; {{ '%.2f'|format(balance) }}</span>
  <form method="post" action="{{ url_for('web.speed') }}">
    <input type="hidden" name="back" value="{{ request.full_path }}">
    <button name="mode" value="pause" {{ 'disabled' if paused }}>Pausa</button>
    <button name="mode" value="play" {{ 'disabled' if not paused }}>Play</button>
    <button name="mode" value="realtime" {{ 'disabled' if (not paused) and realtime }}>T</button>
    <button name="mode" value="1" {{ 'disabled' if (not paused) and (not realtime) and speed == 1 }}>1x</button>
    <button name="mode" value="2" {{ 'disabled' if (not paused) and (not realtime) and speed == 2 }}>2x</button>
    <button name="mode" value="5" {{ 'disabled' if (not paused) and (not realtime) and speed == 5 }}>5x</button>
  </form>
  {% if pending_count %}<a class="msg" href="{{ url_for('web.reception_page') }}">&#9873; Reception: {{ pending_count }} in attesa</a>{% endif %}
  {% if mail_new %}<a class="msg" href="{{ url_for('web.mail_page') }}">&#9993; {{ mail_new }} mail da gestire</a>{% endif %}
</header>
<nav class="tabs">
  {% for endpoint, label in nav %}
  <a href="{{ url_for(endpoint) }}" class="{{ 'active' if endpoint == active else '' }}">{{ label }}</a>
  {% endfor %}
</nav>
{% if welcome %}
<div class="welcome-banner" id="welcomeBanner">
  <button class="wb-x" onclick="document.getElementById('welcomeBanner').remove()">&times;</button>
  <h2>Bentornato Direttore!</h2>
  <p>Mentre eri via sono passati <b>{{ welcome.days }}</b> giorni e <b>{{ welcome.hours }}</b> ore di gioco.</p>
  <p>Stanze vendute: <b>{{ welcome.rooms_sold }}</b></p>
  <p>Guadagnato &euro; {{ '%.2f'|format(welcome.earned) }} &minus; Speso (tasse e costi)
     &euro; {{ '%.2f'|format(welcome.spent) }} = <b>Guadagno effettivo
     &euro; {{ '%.2f'|format(welcome.profit) }}</b></p>
</div>
{% endif %}
<main>{{ content }}</main>
<script>
// aggiornamento live: l'orologio (header) si aggiorna su OGNI pagina; il
// contenuto (main) solo dove `live` e attivo, per non disturbare i form e il
// drag&drop delle pagine di modifica. Salta il giro se si sta scrivendo.
const __liveMain = {{ 'true' if live else 'false' }};
setInterval(async () => {
  // scheda in background o chiusa: niente poll -> la sessione va in idle (e
  // parte l'automazione). Con la scheda in primo piano il poll fa da battito
  // di presenza: l'utente e li a guardare, quindi NON e idle.
  if (document.hidden) return;
  const ae = document.activeElement;
  if (ae && ["INPUT", "SELECT", "TEXTAREA"].includes(ae.tagName)) return;
  try {
    // X-Poll: questo fetch e un refresh di fondo, non un'azione dell'utente
    const html = await (await fetch(location.href, {headers: {"X-Poll": "1"}})).text();
    const doc = new DOMParser().parseFromString(html, "text/html");
    for (const sel of (__liveMain ? ["header.topbar", "main"] : ["header.topbar"])) {
      const cur = document.querySelector(sel), next = doc.querySelector(sel);
      if (cur && next && cur.innerHTML !== next.innerHTML)
        cur.innerHTML = next.innerHTML;
    }
  } catch (e) { /* server assente per un attimo: si riprova al giro dopo */ }
}, 2000);
</script>
</body>
</html>
"""


def page(title: str, active: str, body_tpl: str, ctx: dict, live: bool = True) -> str:
    """Renderizza il contenuto della pagina e lo incornicia nel layout comune.

    live=False (pagine con campi di testo: prenotazione, impostazioni, fogli)
    disattiva l'auto-refresh, che altrimenti sovrascriverebbe quanto digitato.
    """
    inner = render_template_string(body_tpl, **ctx)
    return render_template_string(
        BASE, title=title, active=active, nav=NAV, content=Markup(inner),
        live=live, **ctx)
