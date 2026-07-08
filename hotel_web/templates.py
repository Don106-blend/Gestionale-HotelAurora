"""Layout condiviso, tema "Vista/Frutiger Aero" e icone pixel-art.

Niente file .html ne asset esterni: i template sono stringhe Jinja2 e le
icone sono pixel-art disegnata a caratteri e resa come SVG inline (un rect
per "run" di pixel), cosi tutto resta in un unico processo Python.
"""

from flask import render_template_string
from markupsafe import Markup

# --- icone pixel-art -----------------------------------------------------------
# Ogni icona e una griglia 12x12 di caratteri; '.' = trasparente, il resto
# indica un colore della palette. Aggiungere un'icona = disegnare 12 righe.

_PAL = {
    "k": "#1c3550", "w": "#ffffff", "b": "#4aa3e8", "B": "#2266aa",
    "t": "#8adfff", "g": "#63c94f", "G": "#2e8b2e", "y": "#ffd24a",
    "Y": "#c8931a", "r": "#e05252", "o": "#ef9a3c", "s": "#c9d2da",
    "S": "#8494a3", "n": "#b98651", "N": "#7a5426", "f": "#f5c9a0",
    "p": "#ff9ad5",
}

ICONS = {
    "bed": (
        "............",
        "............",
        ".k..........",
        ".k..........",
        ".kww.bbbbb..",
        ".kwwbbbbbbk.",
        ".kkkkkkkkkk.",
        ".k........k.",
        ".k........k.",
        "............",
        "............",
        "............",
    ),
    "gantt": (
        "............",
        ".kkkkkkkkkk.",
        ".k........k.",
        ".k.bbbb...k.",
        ".k........k.",
        ".k...gggg.k.",
        ".k........k.",
        ".k.yyyyy..k.",
        ".k........k.",
        ".kkkkkkkkkk.",
        "............",
        "............",
    ),
    "thermo": (
        ".....kk.....",
        "....kwwk....",
        "....kwrk....",
        "....kwrk....",
        "....kwrk....",
        "....kwrk....",
        "...kwrrwk...",
        "..kwrrrrwk..",
        "..kwrrrrwk..",
        "...kwrrwk...",
        "....kkkk....",
        "............",
    ),
    "cloche": (
        "............",
        ".....kk.....",
        "....kwwk....",
        "..kkwwwwkk..",
        "..kwwwwwwk..",
        ".kwwwwwwwwk.",
        ".kwwwwwwwwk.",
        ".kkkkkkkkkk.",
        "kssssssssssk",
        ".kkkkkkkkkk.",
        "............",
        "............",
    ),
    "bell": (
        "............",
        ".....kk.....",
        "....kyyk....",
        "...kyyyyk...",
        "..kyyyyyyk..",
        "..kyyyyyyk..",
        ".kyyyyyyyyk.",
        ".kYYYYYYYYk.",
        ".kkkkkkkkkk.",
        "..kssssssk..",
        "..kkkkkkkk..",
        "............",
    ),
    "mail": (
        "............",
        "............",
        ".kkkkkkkkkk.",
        ".kwwwwwwwwk.",
        ".kwkwwwwkwk.",
        ".kwwkwwkwwk.",
        ".kwwwkkwwwk.",
        ".kwwwwwwwwk.",
        ".kwwwwwwwwk.",
        ".kkkkkkkkkk.",
        "............",
        "............",
    ),
    "person": (
        "............",
        "....kkkk....",
        "...kffffk...",
        "...kffffk...",
        "...kffffk...",
        "....kkkk....",
        "..kkbbbbkk..",
        ".kbbbbbbbbk.",
        ".kbbbbbbbbk.",
        ".kbbkbbkbbk.",
        ".kkk....kkk.",
        "............",
    ),
    "todo": (
        "............",
        ".kkkkkkkkkk.",
        ".kwwwwwwwwk.",
        ".kwggwssswk.",
        ".kwwwwwwwwk.",
        ".kwggwssswk.",
        ".kwwwwwwwwk.",
        ".kwggwssswk.",
        ".kwwwwwwwwk.",
        ".kkkkkkkkkk.",
        "............",
        "............",
    ),
    "coin": (
        "............",
        "....kkkk....",
        "..kkyyyykk..",
        ".kyyykkkyyk.",
        ".kyykyyyyyk.",
        ".kykkkkyyyk.",
        ".kyykyyyyyk.",
        ".kyyykkkyyk.",
        "..kkyyyykk..",
        "....kkkk....",
        "............",
        "............",
    ),
    "sheet": (
        "............",
        "..kkkkkkk...",
        "..kwwwwwkk..",
        "..kwwwwwwsk.",
        "..kwsssswwk.",
        "..kwwwwwwwk.",
        "..kwsssswwk.",
        "..kwwwwwwwk.",
        "..kwsssswwk.",
        "..kwwwwwwwk.",
        "..kkkkkkkkk.",
        "............",
    ),
    "globe": (
        "............",
        "....kkkk....",
        "..kkttttkk..",
        ".kttggttttk.",
        ".ktgggtttgk.",
        ".kttggttggk.",
        ".ktttttggtk.",
        ".kttgtttttk.",
        "..kkttttkk..",
        "....kkkk....",
        "............",
        "............",
    ),
    "gear": (
        ".....kk.....",
        ".kk.kssk.kk.",
        ".kskssssksk.",
        "..kssssssk..",
        ".kssskksssk.",
        ".ksskwwkssk.",
        ".ksskwwkssk.",
        ".kssskksssk.",
        "..kssssssk..",
        ".kskssssksk.",
        ".kk.kssk.kk.",
        ".....kk.....",
    ),
    "hammer": (
        "............",
        "..kkkkkk....",
        ".kssssssk...",
        ".kssssssk...",
        "..kkkknkk...",
        ".....knnk...",
        ".....knnk...",
        "......knnk..",
        "......knnk..",
        ".......kk...",
        "............",
        "............",
    ),
    "apple": (
        "......kk....",
        "....ggkk....",
        "...kkrrkk...",
        "..krrrrrrk..",
        ".krrwrrrrrk.",
        ".krwrrrrrrk.",
        ".krrrrrrrrk.",
        ".krrrrrrrrk.",
        "..krrrrrrk..",
        "...kkkkkk...",
        "............",
        "............",
    ),
    "star": (
        ".....kk.....",
        "....kyyk....",
        "....kyyk....",
        ".kkkkyykkkk.",
        ".kyyyyyyyyk.",
        "..kyyyyyyk..",
        "...kyyyyk...",
        "...kyyyyk...",
        "..kyykkyyk..",
        "..kyk..kyk..",
        "..kk....kk..",
        "............",
    ),
    "case": (
        "............",
        "....kkkk....",
        "...knnnnk...",
        ".kkkkkkkkkk.",
        ".knnnnnnnnk.",
        ".knnnkknnnk.",
        ".kkkkkkkkkk.",
        ".knnnnnnnnk.",
        ".knnnnnnnnk.",
        ".kkkkkkkkkk.",
        "............",
        "............",
    ),
    "bank": (
        "............",
        ".....kk.....",
        "..kkkwwkkk..",
        ".kwwwwwwwwk.",
        ".kkkkkkkkkk.",
        ".kwwkwwkwwk.",
        ".kwwkwwkwwk.",
        ".kwwkwwkwwk.",
        ".kwwkwwkwwk.",
        ".kkkkkkkkkk.",
        "kkkkkkkkkkkk",
        "............",
    ),
    "book": (
        "............",
        "..kkkkkkkk..",
        "..kbbybbbk..",
        "..kbbybbbk..",
        "..kbbybbbk..",
        "..kbbbbbbk..",
        "..kbbbbbbk..",
        "..kbbbbbbk..",
        "..kbbbbbbk..",
        "..kkkkkkkk..",
        "............",
        "............",
    ),
    "flag": (
        "............",
        "..k.........",
        "..krrrrrr...",
        "..krrrrrrr..",
        "..krrrrrr...",
        "..k.........",
        "..k.........",
        "..k.........",
        "..k.........",
        "..k.........",
        "............",
        "............",
    ),
    "plus": (
        "............",
        "............",
        "....kkkk....",
        "....kggk....",
        ".kkkkggkkkk.",
        ".kggggggggk.",
        ".kggggggggk.",
        ".kkkkggkkkk.",
        "....kggk....",
        "....kkkk....",
        "............",
        "............",
    ),
}


def icon(name: str, size: int = 16) -> Markup:
    """SVG pixel-art inline: un <rect> per ogni run orizzontale di pixel."""
    rows = ICONS[name]
    rects = []
    for y, row in enumerate(rows):
        x = 0
        while x < len(row):
            ch = row[x]
            if ch == ".":
                x += 1
                continue
            run = 1
            while x + run < len(row) and row[x + run] == ch:
                run += 1
            rects.append(f'<rect x="{x}" y="{y}" width="{run}" height="1"'
                         f' fill="{_PAL[ch]}"/>')
            x += run
    return Markup(
        f'<svg class="px" viewBox="0 0 12 12" width="{size}" height="{size}"'
        f' shape-rendering="crispEdges" aria-hidden="true">{"".join(rects)}</svg>')


NAV = (
    ("web.dashboard", "Camere", "bed"),
    ("web.timeline_page", "Timeline", "gantt"),
    ("web.occupancy", "Occupazione", "thermo"),
    ("web.dining_page", "Sala pasti", "cloche"),
    ("web.reception_page", "Reception", "bell"),
    ("web.mail_page", "Mail", "mail"),
    ("web.staff_page", "Dipendenti", "person"),
    ("web.problems_page", "To Do", "todo"),
    ("web.budget_page", "Budget", "coin"),
    ("web.reports_page", "Fogli", "sheet"),
    ("web.browser_page", "Browser", "globe"),
    ("web.debug_page", "Impostazioni", "gear"),
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
  body { margin: 0; color: #1c3550;
    font-family: "Segoe UI", Tahoma, Verdana, sans-serif;
    background:
      radial-gradient(circle at 85% 10%, rgba(255,255,255,.6), transparent 42%),
      radial-gradient(circle at 10% 90%, rgba(120,220,160,.28), transparent 45%),
      radial-gradient(circle at 70% 80%, rgba(90,190,255,.22), transparent 40%),
      linear-gradient(180deg, #a6d8f7, #dbeffb 45%, #cfeadd);
    background-attachment: fixed; min-height: 100vh; }
  svg.px { vertical-align: -3px; }

  /* --- barra del titolo stile Vista --- */
  header.topbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
    padding: 8px 16px; color: #eaf6ff;
    text-shadow: 0 1px 2px rgba(6,40,70,.7);
    border-bottom: 1px solid #0c2f52;
    background:
      linear-gradient(180deg, rgba(255,255,255,.38), rgba(255,255,255,.10) 46%,
                      rgba(4,26,48,.25) 52%, rgba(255,255,255,.06)),
      linear-gradient(180deg, #2f6da8, #174a7c 60%, #0f3a64); }
  header.topbar b { color: #fff; font-size: 15px; letter-spacing: .3px; }
  header.topbar form { display: inline-flex; gap: 3px; margin: 0; }
  header.topbar a.msg { color: #ffe27a; text-decoration: none; font-weight: 700; }
  .shift-pill { padding: 2px 12px; border-radius: 12px; color: #1c3550;
    font-weight: 700; text-shadow: none; border: 1px solid rgba(12,47,82,.45);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.8), 0 1px 2px rgba(6,40,70,.4); }

  /* --- tab di navigazione: vetro aero --- */
  nav.tabs { display: flex; flex-wrap: wrap; gap: 3px; padding: 6px 10px 0;
    background: linear-gradient(180deg, rgba(255,255,255,.75), rgba(214,236,250,.55));
    border-bottom: 1px solid #7ab0d4; backdrop-filter: blur(3px); }
  nav.tabs a { display: inline-flex; align-items: center; gap: 6px;
    color: #17568a; text-decoration: none; padding: 7px 12px; font-size: 13px;
    font-weight: 600; border: 1px solid transparent; border-bottom: none;
    border-radius: 7px 7px 0 0; }
  nav.tabs a:hover { background: rgba(255,255,255,.65); border-color: #a6cbe6;
    box-shadow: 0 0 8px rgba(120,200,255,.7); }
  nav.tabs a.active { color: #0f3a64; border-color: #7ab0d4;
    background: linear-gradient(180deg, #ffffff, #e8f4fd 60%, #d6ecfa);
    box-shadow: inset 0 1px 0 #fff, inset 0 -8px 12px -10px #4aa3e8; }

  main { padding: 16px; max-width: 1200px; margin: 0 auto; }

  /* --- pannelli di vetro --- */
  .card { background: rgba(255,255,255,.82); border: 1px solid rgba(122,176,212,.65);
    border-radius: 9px; padding: 12px 16px; margin-bottom: 14px;
    box-shadow: 0 2px 10px rgba(23,86,138,.18), inset 0 1px 0 #fff;
    backdrop-filter: blur(4px); }
  h2, h3 { color: #17568a; }
  .card h2 { margin-top: 2px; }

  table { border-collapse: collapse; width: 100%; background: rgba(255,255,255,.92); }
  th, td { border: 1px solid #cfe0ee; padding: 6px 8px; text-align: left; font-size: 14px; }
  th { background: linear-gradient(180deg, #f4fafe, #ddeefb);
    color: #17568a; }
  tr:nth-child(even) td { background: rgba(214,235,250,.28); }

  /* --- pulsanti vetro aero --- */
  button, .btn { display: inline-flex; align-items: center; gap: 6px;
    color: #1c3550; font-weight: 600; font-size: 13px; cursor: pointer;
    text-decoration: none; padding: 5px 12px; border-radius: 5px;
    border: 1px solid #7ab0d4; font-family: inherit;
    background: linear-gradient(180deg, #fdfeff, #e6f2fb 45%, #cfe6f8 52%, #e9f6ff);
    box-shadow: inset 0 1px 0 #fff, 0 1px 2px rgba(23,86,138,.25); }
  button:hover, .btn:hover { border-color: #4aa3e8;
    box-shadow: inset 0 1px 0 #fff, 0 0 7px rgba(110,195,255,.85); }
  button:active, .btn:active {
    background: linear-gradient(180deg, #cfe6f8, #e6f2fb 55%, #fdfeff); }
  button:disabled { opacity: .45; cursor: default; filter: grayscale(.6);
    box-shadow: none; }
  input, select { padding: 4px 6px; border: 1px solid #7ab0d4; border-radius: 4px;
    background: linear-gradient(180deg, #ffffff, #f2f9ff); font-family: inherit; }
  input:focus, select:focus { outline: none; border-color: #4aa3e8;
    box-shadow: 0 0 6px rgba(110,195,255,.8); }

  .msg { color: #b71c1c; font-weight: 600; }
  pre { white-space: pre-wrap; background: rgba(255,255,255,.9);
    border: 1px solid #cfe0ee; padding: 12px; border-radius: 6px;
    font-family: "Courier New", monospace; font-size: 13px; }

  /* --- griglia camere --- */
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; }
  .room { position: relative; display: block; text-decoration: none; color: #1c3550;
    border-radius: 7px; padding: 6px; min-height: 62px; border: 1px solid #6b8aa5;
    font-size: 12px; line-height: 1.3; overflow: hidden;
    background-image: linear-gradient(180deg, rgba(255,255,255,.55), rgba(255,255,255,0) 55%);
    box-shadow: 0 1px 3px rgba(23,86,138,.25); }
  .room:hover { box-shadow: 0 0 8px rgba(110,195,255,.9); }
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

  /* --- Occupazione: visione termica --- */
  .thermal { background: #05070c; padding: 16px; border-radius: 10px;
    border: 1px solid #123; box-shadow: inset 0 0 30px rgba(0,60,120,.5); }
  .thermal .legend { height: 14px; border-radius: 7px; margin: 0 0 6px;
    background: linear-gradient(90deg, #0057ff, #00c878, #ffd600, #ff1744); }
  .thermal .legkey { color: #9fb4c4; font-size: 12px; margin-bottom: 14px; }
  .thermal .room { border-color: #223; color: #fff; text-shadow: 0 0 4px #000;
    background-image: none; }
  .dots { display: flex; gap: 4px; margin-top: 6px; flex-wrap: wrap; }
  .dot { width: 12px; height: 12px; border-radius: 50%; border: 1px solid #222; }

  /* --- Timeline: barre continue --- */
  .tl { overflow-x: auto; }
  .tl table { border-collapse: collapse; background: rgba(255,255,255,.95);
    table-layout: fixed; width: max-content; }
  .tl td, .tl th { border: 1px solid #e2ecf5; padding: 0; font-size: 11px;
    text-align: center; width: 34px; height: 24px; }
  .tl tr:nth-child(even) td { background: transparent; }
  .tl th.room, .tl td.room { width: 52px; font-weight: 700; text-align: left;
    padding: 0 4px; position: sticky; left: 0;
    background: linear-gradient(180deg, #f4fafe, #ddeefb); z-index: 1; }
  .tl td.today { background: rgba(180,230,140,.35); }
  .tl th.today { background: linear-gradient(180deg, #e9f9d8, #cdeeb2); }
  .tl .bar { height: 18px; border-radius: 9px; border: 1px solid #5c7d99;
    margin: 2px 3px; font-size: 10px; color: #1c3550; overflow: hidden;
    white-space: nowrap; padding: 0 6px; text-align: left;
    background-image: linear-gradient(180deg, rgba(255,255,255,.65),
      rgba(255,255,255,.15) 48%, rgba(0,0,0,.05));
    box-shadow: inset 0 1px 0 rgba(255,255,255,.8); }
  .tl .bar.movable { cursor: grab; }
  .tl .bar.movable:active { cursor: grabbing; }
  .tl tr.drop td { background: #dbeafe; }

  /* --- Bentornato Direttore --- */
  .welcome-banner { position: relative; max-width: 1200px; margin: 12px auto 0;
    color: #fff; text-shadow: 0 1px 2px rgba(20,60,25,.6);
    padding: 16px 20px; border-radius: 10px; border: 1px solid #1f7a33;
    background:
      linear-gradient(180deg, rgba(255,255,255,.4), rgba(255,255,255,.08) 48%,
                      rgba(0,40,10,.15) 52%, rgba(255,255,255,.05)),
      linear-gradient(135deg, #58c04d, #2f9440);
    box-shadow: 0 2px 10px rgba(23,86,60,.35), inset 0 1px 0 rgba(255,255,255,.55); }
  .welcome-banner h2 { margin: 0 0 6px; color: #fff; }
  .welcome-banner p { margin: 3px 0; }
  .welcome-banner .wb-x { position: absolute; top: 8px; right: 10px;
    background: transparent; border: none; box-shadow: none; color: #fff;
    font-size: 20px; line-height: 1; padding: 2px 8px; }

  /* --- Sala pasti: tavoli con sedie --- */
  .dgrid { display: grid; grid-template-columns: repeat({{ dining_cols|default(6) }}, 1fr);
    gap: 10px; padding: 12px; border-radius: 10px;
    background: linear-gradient(180deg, rgba(233,244,250,.9), rgba(214,236,222,.9));
    border: 1px solid rgba(122,176,212,.5); }
  .dcell { min-height: 104px; border: 1px dashed #a9c3d4; border-radius: 8px;
    display: flex; align-items: center; justify-content: center; }
  .dcell.drop { background: #dbeafe; }
  .dtable { cursor: grab; display: flex; flex-direction: column; align-items: center; gap: 3px; }
  .dtable:active { cursor: grabbing; }
  .dtable .top-chairs, .dtable .bot-chairs { display: flex; gap: 6px; }
  .dtable .surface { color: #fff; text-shadow: 0 1px 1px rgba(60,35,10,.8);
    border: 2px solid #7a4e26; border-radius: 6px; padding: 10px 12px;
    font-size: 11px; font-weight: 700; text-align: center; min-width: 52px;
    background: linear-gradient(180deg, #d8a76b, #b98651 45%, #a9743f);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.5), 0 1px 3px rgba(60,35,10,.4); }
  .dtable.double .surface { min-width: 96px; padding: 14px 22px; }
  .chair { width: 12px; height: 12px; background: #cfd8dc; border: 1px solid #90a4ae;
    border-radius: 50% 50% 3px 3px; }
  .chair.busy { background: #ffd600; border-color: #c8a900; }

  /* --- Browser: piastrelle app --- */
  .apps { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 12px; }
  .apps a { display: flex; flex-direction: column; align-items: center; gap: 10px;
    color: #17568a; text-decoration: none; text-align: center;
    padding: 22px 10px 18px; border-radius: 10px; font-size: 14px; font-weight: 700;
    border: 1px solid rgba(122,176,212,.7);
    background: linear-gradient(160deg, rgba(255,255,255,.92), rgba(214,236,250,.8));
    box-shadow: inset 0 1px 0 #fff, 0 2px 6px rgba(23,86,138,.2); }
  .apps a:hover { box-shadow: inset 0 1px 0 #fff, 0 0 12px rgba(110,195,255,.9); }
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
  {% if pending_count %}<a class="msg" href="{{ url_for('web.reception_page') }}">{{ icon('flag', 14) }} Reception: {{ pending_count }} in attesa</a>{% endif %}
  {% if mail_new %}<a class="msg" href="{{ url_for('web.mail_page') }}">{{ icon('mail', 14) }} {{ mail_new }} mail da gestire</a>{% endif %}
</header>
<nav class="tabs">
  {% for endpoint, label, ic in nav %}
  <a href="{{ url_for(endpoint) }}" class="{{ 'active' if endpoint == active else '' }}">{{ icon(ic, 15) }}{{ label }}</a>
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
    limita l'auto-refresh al solo header, per non toccare quanto digitato.
    """
    ctx = {**ctx, "icon": icon}
    inner = render_template_string(body_tpl, **ctx)
    return render_template_string(
        BASE, title=title, active=active, nav=NAV, content=Markup(inner),
        live=live, **ctx)
