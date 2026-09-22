"""Phone-friendly web control panel for AI-Mirror.

A wall-mounted mirror has no keyboard, so this serves a small dark-themed
page on the LAN to control it: switch state (active/screensaver/sleep),
toggle module visibility, and watch API usage and recent logs.

Zero dependencies - stdlib ThreadingHTTPServer running in a daemon
thread. The handler only READS mirror state; all writes are pushed onto
a command queue that the main render loop drains each frame, so there is
no cross-thread mutation of pygame or module state.

No authentication: intended for a trusted home LAN only. Set
web_panel.enabled = False in config to turn it off.
"""

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Queue
from urllib.parse import urlparse, parse_qs

from api_tracker import api_tracker

logger = logging.getLogger("WebPanel")

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG_FILE = os.path.join(_PROJECT_DIR, "magic_mirror.log")

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI-Mirror</title>
<style>
  :root { color-scheme:dark; --bg:#090b10; --card:#111722; --card-2:#0d121b;
          --line:#253143; --ink:#edf4ff; --muted:#8f9bad; --blue:#69c6ff;
          --green:#80e1af; --danger:#ff8d9b; }
  * { box-sizing:border-box; }
  body { background:radial-gradient(1000px 520px at 50% -180px,#17344d 0%,var(--bg) 58%);
         color:var(--ink); font-family:Inter,'Segoe UI',sans-serif; margin:0; padding:18px; }
  .shell { max-width:980px; margin:auto; }
  .topbar { display:flex; align-items:center; gap:14px; margin:3px 0 18px; }
  h1 { color:var(--ink); font-weight:450; font-size:1.35rem; letter-spacing:.01em; margin:0; }
  .live { display:inline-flex; align-items:center; gap:7px; color:var(--muted); font-size:.78rem; }
  .live::before { content:''; width:8px; height:8px; border-radius:50%; background:var(--green); box-shadow:0 0 12px rgba(128,225,175,.6); }
  .refresh { margin-left:auto; flex:0; min-width:auto; padding:8px 11px; font-size:.8rem; }
  nav { display:flex; gap:6px; overflow-x:auto; padding-bottom:12px; margin-bottom:4px; }
  nav a { white-space:nowrap; padding:7px 10px; color:var(--muted); font-size:.78rem; text-decoration:none; border:1px solid transparent; border-radius:999px; }
  nav a:hover { color:var(--ink); border-color:var(--line); background:rgba(105,198,255,.06); }
  .grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
  .card { background:linear-gradient(145deg,rgba(22,31,45,.96),rgba(11,15,23,.96));
          border:1px solid var(--line); border-radius:14px; padding:15px; box-shadow:0 12px 30px rgba(0,0,0,.15); }
  .card.wide { grid-column:1 / -1; }
  h2 { color:#b9dbf4; font-size:.72rem; text-transform:uppercase; letter-spacing:.14em; margin:0 0 12px; font-weight:650; }
  .row { display:flex; flex-wrap:wrap; gap:8px; }
  button { background:#172130; color:#dbe8f6; border:1px solid #304056; border-radius:9px;
           padding:10px 12px; font-size:.88rem; cursor:pointer; flex:1 1 28%; min-width:82px;
           transition:background .15s,border-color .15s,transform .15s; }
  button:hover:not(:disabled) { border-color:#6b9fc1; background:#1d2b3d; }
  button:active:not(:disabled) { transform:translateY(1px); }
  button:disabled { cursor:not-allowed; }
  button.on { border-color:#31895a; color:var(--green); background:rgba(42,109,74,.16); }
  button.off { color:#788596; background:#111822; }
  button.state-active { border-color:var(--blue); color:#d8f2ff; background:rgba(57,145,204,.18); box-shadow:inset 0 0 0 1px rgba(105,198,255,.13); }
  .meta { color:var(--muted); font-size:.78rem; line-height:1.35; margin-top:9px; }
  .saved { color:var(--green); }
  .split { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:10px; }
  .count { color:var(--muted); font-size:.75rem; }
  .ticker-add { display:flex; gap:8px; margin-bottom:10px; }
  input[type=text] { min-width:0; flex:1; background:#0a1018; color:var(--ink); border:1px solid #304056; border-radius:9px; padding:10px 11px; font:inherit; text-transform:uppercase; }
  .ticker-add button { flex:0; min-width:78px; }
  .chips { display:flex; flex-wrap:wrap; gap:7px; min-height:38px; }
  .chip { display:inline-flex; align-items:center; gap:7px; padding:6px 7px 6px 9px; border:1px solid #33455c; border-radius:999px; background:#101a27; font-size:.84rem; }
  .chip input { accent-color:var(--blue); width:15px; height:15px; margin:0; }
  .chip.off { opacity:.48; }
  .chip button { min-width:22px; flex:0; padding:0; width:22px; height:22px; border:0; color:#aebccd; background:transparent; font-size:1.1rem; line-height:1; }
  .chip button:hover { color:var(--danger); background:rgba(255,141,155,.12); }
  .halist { max-height:330px; overflow-y:auto; border:1px solid var(--line); border-radius:10px; padding:4px 10px; background:#0b1018; }
  .halist label { display:flex; align-items:center; gap:10px; padding:9px 2px; font-size:.88rem; border-bottom:1px solid rgba(48,64,86,.48); }
  .halist label:last-child { border-bottom:0; }
  .halist input { width:17px; height:17px; accent-color:var(--blue); }
  .halist .st { color:var(--muted); margin-left:auto; font-size:.78rem; max-width:36%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .entity-tools { display:flex; gap:7px; margin-bottom:8px; }
  .entity-tools button { flex:0; min-width:auto; padding:7px 9px; font-size:.76rem; }
  table { width:100%; border-collapse:collapse; font-size:.82rem; }
  td, th { padding:7px 6px; text-align:left; border-bottom:1px solid rgba(48,64,86,.58); }
  th { color:var(--muted); font-weight:550; font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; }
  pre { margin:0; background:#080c12; border:1px solid var(--line); border-radius:10px;
        padding:11px; font-size:.72rem; overflow-x:auto; white-space:pre-wrap; max-height:300px; overflow-y:auto; }
  details summary { cursor:pointer; color:#b9dbf4; font-size:.82rem; }
  details[open] summary { margin-bottom:12px; }
  @media (max-width:680px) { body { padding:12px; } .grid { grid-template-columns:1fr; } .card.wide { grid-column:auto; } .topbar { margin-bottom:12px; } .halist { max-height:270px; } }
</style>
</head>
<body>
<main class="shell">
  <header class="topbar">
    <div><h1>AI-Mirror</h1><span class="live">Local control</span></div>
    <button class="refresh" onclick="refreshAll()">Refresh</button>
  </header>
  <nav aria-label="Control sections">
    <a href="#mirror">Mirror</a><a href="#avatar">Avatar</a><a href="#modules">Modules</a>
    <a href="#stocks">Stocks</a><a href="#home">Home</a><a href="#system">System</a>
  </nav>
  <div class="grid">
    <section class="card" id="mirror">
      <h2>Mirror state</h2><div class="row" id="states"></div>
      <div class="meta">Choose how the mirror behaves right now.</div>
    </section>
    <section class="card">
      <h2>Theme & effects</h2><div class="row" id="themes"></div>
      <div class="row" style="margin-top:8px"><button id="ringBtn" onclick="postRing()">Portal ring</button></div>
    </section>
    <section class="card" id="avatar">
      <h2>Avatar character</h2><div class="row" id="avatars"></div>
      <div class="meta" id="avatarMeta">Loading avatar choices...</div>
    </section>
    <section class="card">
      <h2>Moments</h2><div class="row">
        <button onclick="post('/api/trigger_moment')">Trigger now</button>
        <button id="guestModeBtn" onclick="post('/api/guest_mode')">Guest mode</button>
      </div>
      <div class="meta" id="momentMeta">Fires something now for guests, ignoring the usual rarity cooldowns.</div>
      <div class="meta" id="guestModeMeta">Guest mode makes moments more frequent.</div>
    </section>
    <section class="card wide" id="modules">
      <div class="split"><h2>Visible modules</h2><span class="count" id="moduleCount"></span></div>
      <div class="row" id="modules"></div>
      <div class="meta">Tap a module to show or hide it on the mirror.</div>
    </section>
    <section class="card" id="stocks">
      <div class="split"><h2>Stocks watchlist</h2><span class="count" id="tickerCount"></span></div>
      <div class="ticker-add"><input id="tickerInput" type="text" placeholder="Add ticker e.g. RR.L" maxlength="20"><button onclick="addTicker()">Add</button></div>
      <div class="chips" id="tickerList">Loading…</div>
      <div class="row" style="margin-top:10px"><button onclick="saveTickers()">Save display list</button><button onclick="loadTickers()">Reload</button></div>
      <div class="meta" id="tickersMeta">Tick symbols to display; × removes a symbol. Supports AAPL, RR.L and BTC/USD.</div>
    </section>
    <section class="card" id="home">
      <div class="split"><h2>Smart home entities</h2><span class="count" id="entityCount"></span></div>
      <div class="entity-tools"><button onclick="setEntityChecks(true)">All</button><button onclick="setEntityChecks(false)">None</button></div>
      <div class="halist" id="haList">Loading…</div>
      <div class="row" style="margin-top:10px"><button onclick="saveEntities()">Save selection</button><button onclick="loadEntities()">Reload</button></div>
      <div class="meta" id="haMeta">Tick which entities the mirror can display.</div>
    </section>
    <section class="card wide" id="system">
      <h2>System</h2>
      <details open><summary>API usage · last 24 hours</summary>
        <table id="api"><thead><tr><th>Service</th><th>Day</th><th>Hour</th><th>Cost</th></tr></thead><tbody></tbody></table>
        <div class="meta" id="apiTotals"></div>
      </details>
      <details><summary>Recent log</summary><pre id="log">Loading…</pre></details>
    </section>
  </div>
</main>

<script>
const STATES = ["active", "screensaver", "sleep"];

async function getStatus() {
  const r = await fetch("/api/status");
  return r.json();
}

async function post(path) {
  await fetch(path, { method: "POST" });
  refresh();
}

function refreshAll() {
  refresh(); refreshLog(); loadTickers(); loadEntities(); loadThemes(); loadAvatars();
}

async function loadThemes() {
  try {
    const r = await fetch("/api/themes");
    const j = await r.json();
    const box = document.getElementById("themes");
    box.innerHTML = "";
    for (const [key, label] of j.themes) {
      const b = document.createElement("button");
      b.textContent = label;
      if (key === j.current) b.className = "state-active";
      b.onclick = () => postTheme(key);
      box.appendChild(b);
    }
  } catch (e) {}
}

async function postTheme(key) {
  await fetch("/api/theme?value=" + key, { method: "POST" });
  loadThemes();
}

async function postRing() {
  await fetch("/api/portal_ring", { method: "POST" });
  refresh();
}

async function loadAvatars() {
  const box = document.getElementById("avatars");
  const meta = document.getElementById("avatarMeta");
  try {
    const r = await fetch("/api/avatars");
    const j = await r.json();
    box.innerHTML = "";
    if (!j.enabled) {
      meta.textContent = "Avatar mode is disabled. Set ENABLE_AVATAR=1 and restart the mirror.";
      return;
    }
    for (const avatar of (j.avatars || [])) {
      const b = document.createElement("button");
      b.textContent = avatar.name;
      b.title = avatar.description;
      b.disabled = !!j.busy || !avatar.reference_available;
      b.className = avatar.selected ? "state-active" : (avatar.reference_available ? "" : "off");
      b.onclick = () => selectAvatar(avatar.key);
      box.appendChild(b);
    }
    const selected = (j.avatars || []).find(a => a.selected);
    meta.textContent = j.busy
      ? "Current response is finishing; character switching is temporarily locked."
      : (selected ? selected.name + " - " + selected.description : "Choose a character.");
  } catch (e) {
    meta.textContent = "Avatar choices unavailable.";
  }
}

async function selectAvatar(key) {
  const meta = document.getElementById("avatarMeta");
  meta.textContent = "Switching character...";
  const r = await fetch("/api/avatar?value=" + encodeURIComponent(key), { method: "POST" });
  if (!r.ok) {
    const j = await r.json();
    meta.textContent = j.error || "Character switch failed.";
    return;
  }
  setTimeout(loadAvatars, 300);
}

function render(s) {
  const states = document.getElementById("states");
  states.innerHTML = "";
  for (const st of STATES) {
    const b = document.createElement("button");
    b.textContent = st;
    if (st === s.state) b.className = "state-active";
    b.onclick = () => post("/api/state?value=" + st);
    states.appendChild(b);
  }

  const mods = document.getElementById("modules");
  mods.innerHTML = "";
  for (const [name, vis] of Object.entries(s.modules)) {
    const b = document.createElement("button");
    b.textContent = name;
    b.className = vis ? "on" : "off";
    b.onclick = () => post("/api/toggle?module=" + name);
    mods.appendChild(b);
  }
  document.getElementById("moduleCount").textContent =
    Object.values(s.modules).filter(Boolean).length + " on";

  const tbody = document.querySelector("#api tbody");
  tbody.innerHTML = "";
  const svc = s.api.by_service || {};
  for (const name of Object.keys(svc).sort()) {
    const v = svc[name];
    const tr = document.createElement("tr");
    tr.innerHTML = "<td>" + name + "</td><td>" + v.daily + "</td><td>"
      + v.hourly + "</td><td>"
      + (v.cost > 0 ? "$" + v.cost.toFixed(3) : "-") + "</td>";
    tbody.appendChild(tr);
  }
  document.getElementById("apiTotals").textContent =
    s.api.total_calls_24h + " calls, $" + s.api.total_cost.toFixed(3)
    + " estimated, up " + s.api.uptime_hours.toFixed(1) + "h";

  const momentMeta = document.getElementById("momentMeta");
  if (s.moments && s.moments.active) {
    momentMeta.textContent = "Playing now: " + s.moments.active;
  } else {
    momentMeta.textContent = "Fires something now for guests, ignoring the usual rarity cooldowns.";
  }

  const guestBtn = document.getElementById("guestModeBtn");
  const guestOn = !!(s.moments && s.moments.guest_mode);
  guestBtn.className = guestOn ? "on" : "off";
  guestBtn.textContent = guestOn ? "Guest mode: ON" : "Guest mode: OFF";

  const ringBtn = document.getElementById("ringBtn");
  ringBtn.className = s.portal_ring ? "on" : "off";
  ringBtn.textContent = s.portal_ring ? "Portal ring: ON" : "Portal ring: OFF";
}

async function refreshLog() {
  const r = await fetch("/api/logs?lines=60");
  document.getElementById("log").textContent = await r.text();
}

async function refresh() {
  try { render(await getStatus()); } catch (e) {}
}

async function loadTickers() {
  try {
    const r = await fetch("/api/tickers");
    const j = await r.json();
    tickerItems = (j.tickers || []).map(symbol => ({ symbol, enabled: true }));
    renderTickers();
    document.getElementById("tickersMeta").textContent =
      "Tick symbols to display; × removes a symbol. Supports AAPL, RR.L and BTC/USD.";
  } catch (e) {}
}

let tickerItems = [];
function renderTickers() {
  const list = document.getElementById("tickerList");
  list.innerHTML = "";
  for (const item of tickerItems) {
    const chip = document.createElement("label");
    chip.className = "chip" + (item.enabled ? "" : " off");
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = item.enabled;
    cb.onchange = () => { item.enabled = cb.checked; renderTickers(); };
    const name = document.createElement("span"); name.textContent = item.symbol;
    const remove = document.createElement("button"); remove.type = "button"; remove.title = "Remove " + item.symbol; remove.textContent = "×";
    remove.onclick = () => { tickerItems = tickerItems.filter(t => t !== item); renderTickers(); };
    chip.append(cb, name, remove); list.appendChild(chip);
  }
  if (!tickerItems.length) list.textContent = "No symbols selected.";
  document.getElementById("tickerCount").textContent = tickerItems.filter(t => t.enabled).length + " displayed";
}

function addTicker() {
  const input = document.getElementById("tickerInput");
  const symbol = input.value.trim().toUpperCase();
  if (!symbol) return;
  if (tickerItems.some(t => t.symbol === symbol)) { input.select(); return; }
  tickerItems.push({ symbol, enabled: true }); input.value = ""; renderTickers();
}

async function saveTickers() {
  const meta = document.getElementById("tickersMeta");
  const symbols = tickerItems.filter(t => t.enabled).map(t => t.symbol);
  await fetch("/api/tickers", { method: "POST", body: symbols.join("\\n") });
  meta.innerHTML = "<span class='saved'>Saved - refetching prices...</span>";
  setTimeout(loadTickers, 1500);
}

async function loadEntities() {
  try {
    const r = await fetch("/api/ha_entities");
    const j = await r.json();
    const list = document.getElementById("haList");
    list.innerHTML = "";
    const ents = j.entities || [];
    if (!ents.length) {
      list.textContent = "No entities yet (Home Assistant not connected?)";
      return;
    }
    for (const e of ents) {
      const lab = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox"; cb.value = e.id; cb.checked = e.shown;
      const nm = document.createElement("span"); nm.textContent = e.name;
      const st = document.createElement("span"); st.className = "st"; st.textContent = e.state;
      lab.appendChild(cb); lab.appendChild(nm); lab.appendChild(st);
      list.appendChild(lab);
    }
    document.getElementById("haMeta").textContent =
      ents.filter(e => e.shown).length + " shown of " + ents.length + " offered";
    document.getElementById("entityCount").textContent =
      ents.filter(e => e.shown).length + " / " + ents.length;
  } catch (e) {}
}

function setEntityChecks(checked) {
  document.querySelectorAll("#haList input").forEach(cb => { cb.checked = checked; });
}

async function saveEntities() {
  const ids = [...document.querySelectorAll("#haList input:checked")].map(c => c.value);
  document.getElementById("haMeta").innerHTML =
    "<span class='saved'>Saved - refreshing...</span>";
  await fetch("/api/ha_entities", { method: "POST", body: JSON.stringify(ids) });
  setTimeout(loadEntities, 1500);
}

refresh();
refreshLog();
loadTickers();
loadEntities();
loadThemes();
loadAvatars();
document.getElementById("tickerInput").addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); addTicker(); }
});
setInterval(refresh, 5000);
setInterval(refreshLog, 10000);
setInterval(loadThemes, 10000);
setInterval(loadAvatars, 5000);
</script>
</body>
</html>
"""


class WebPanel:
    """LAN control panel. Writes go through self.commands, drained by the
    main loop via process_commands()."""

    def __init__(self, mirror, host="0.0.0.0", port=8780):
        self.mirror = mirror
        self.host = host
        self.port = port
        self.commands = Queue()
        self._server = None
        self._thread = None

    # ----- main-loop side -------------------------------------------------

    def process_commands(self):
        """Apply queued panel commands. Called from the main render loop."""
        while not self.commands.empty():
            try:
                cmd, value = self.commands.get_nowait()
            except Exception:
                break
            try:
                if cmd == "toggle":
                    mm = self.mirror.module_manager
                    current = mm.is_module_visible(value)
                    mm.module_visibility[value] = not current
                    logger.info(f"Panel toggled {value}: {'OFF' if current else 'ON'}")
                    if hasattr(self.mirror, "animation_manager"):
                        self.mirror.animation_manager.push_notification(
                            f"[panel] {value}: {'OFF' if current else 'ON'}",
                            duration_ms=2000,
                        )
                elif cmd == "state":
                    self.mirror.change_state(value)
                    logger.info(f"Panel set state: {value}")
                elif cmd == "set_tickers":
                    stocks = self.mirror.modules.get("stocks")
                    if stocks and hasattr(stocks, "set_tickers"):
                        stocks.set_tickers(value)
                elif cmd == "set_entities":
                    sh = self.mirror.modules.get("smarthome")
                    if sh and hasattr(sh, "set_entities"):
                        sh.set_entities(value)
                elif cmd == "set_avatar":
                    avatar = self.mirror.modules.get("avatar")
                    if avatar and hasattr(avatar, "select_avatar"):
                        profile = avatar.select_avatar(value)
                        logger.info("Panel selected avatar: %s", profile.name)
                        if hasattr(self.mirror, "animation_manager"):
                            self.mirror.animation_manager.push_notification(
                                f"Avatar: {profile.name}", duration_ms=2500,
                            )
                elif cmd == "trigger_moment":
                    director = getattr(self.mirror, "director", None)
                    if director:
                        started = director.trigger_random()
                        logger.info(f"Panel triggered a moment: {'ok' if started else 'busy/none'}")
                elif cmd == "guest_mode":
                    director = getattr(self.mirror, "director", None)
                    if director:
                        director.guest_mode = not director.guest_mode
                        logger.info(f"Panel set guest mode: {'ON' if director.guest_mode else 'OFF'}")
                elif cmd == "portal_ring":
                    import theme
                    theme.portal_ring_enabled = not theme.portal_ring_enabled
                    logger.info(f"Panel set portal ring: {'ON' if theme.portal_ring_enabled else 'OFF'}")
                elif cmd == "set_theme":
                    import theme
                    if theme.set_theme(value):
                        logger.info(f"Panel set theme: {value}")
                        if hasattr(self.mirror, "animation_manager"):
                            self.mirror.animation_manager.push_notification(
                                f"Theme: {dict(theme.names())[value]}", duration_ms=2500,
                            )
            except Exception as e:
                logger.error(f"Panel command {cmd}={value} failed: {e}")

    # ----- server side ----------------------------------------------------

    def start(self):
        panel = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass  # keep request noise out of the mirror log

            def _send(self, code, body, ctype="application/json"):
                data = body.encode("utf-8") if isinstance(body, str) else body
                self.send_response(code)
                self.send_header("Content-Type", ctype + "; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                url = urlparse(self.path)
                if url.path == "/":
                    self._send(200, PAGE, "text/html")
                elif url.path == "/api/status":
                    self._send(200, json.dumps(panel.status()))
                elif url.path == "/api/logs":
                    qs = parse_qs(url.query)
                    lines = int(qs.get("lines", ["60"])[0])
                    self._send(200, panel.tail_log(min(lines, 500)), "text/plain")
                elif url.path == "/api/tickers":
                    stocks = panel.mirror.modules.get("stocks")
                    tickers = (stocks.get_tickers()
                               if stocks and hasattr(stocks, "get_tickers") else [])
                    self._send(200, json.dumps({"tickers": tickers}))
                elif url.path == "/api/ha_entities":
                    sh = panel.mirror.modules.get("smarthome")
                    opts = (sh.get_entity_options()
                            if sh and hasattr(sh, "get_entity_options") else [])
                    self._send(200, json.dumps({"entities": opts}))
                elif url.path == "/api/themes":
                    import theme
                    self._send(200, json.dumps({
                        "themes": theme.names(), "current": theme.current(),
                    }))
                elif url.path == "/api/avatars":
                    avatar = panel.mirror.modules.get("avatar")
                    payload = (
                        avatar.get_avatar_options()
                        if avatar and hasattr(avatar, "get_avatar_options")
                        else {"enabled": False, "avatars": [], "current": None, "busy": False}
                    )
                    payload.setdefault("enabled", True)
                    self._send(200, json.dumps(payload))
                else:
                    self._send(404, json.dumps({"error": "not found"}))

            def do_POST(self):
                url = urlparse(self.path)
                qs = parse_qs(url.query)
                if url.path == "/api/trigger_moment":
                    panel.commands.put(("trigger_moment", None))
                    self._send(200, json.dumps({"ok": True}))
                elif url.path == "/api/guest_mode":
                    panel.commands.put(("guest_mode", None))
                    self._send(200, json.dumps({"ok": True}))
                elif url.path == "/api/theme":
                    value = qs.get("value", [""])[0]
                    panel.commands.put(("set_theme", value))
                    self._send(200, json.dumps({"ok": True}))
                elif url.path == "/api/portal_ring":
                    panel.commands.put(("portal_ring", None))
                    self._send(200, json.dumps({"ok": True}))
                elif url.path == "/api/avatar":
                    value = qs.get("value", [""])[0]
                    avatar = panel.mirror.modules.get("avatar")
                    if not avatar or not hasattr(avatar, "get_avatar_options"):
                        self._send(409, json.dumps({"error": "avatar mode is disabled"}))
                    else:
                        options = avatar.get_avatar_options()
                        valid = {
                            item["key"] for item in options.get("avatars", [])
                            if item.get("reference_available")
                        }
                        if options.get("busy"):
                            self._send(409, json.dumps({"error": "wait for the current avatar turn to finish"}))
                        elif value not in valid:
                            self._send(400, json.dumps({"error": "unknown avatar"}))
                        else:
                            panel.commands.put(("set_avatar", value))
                            self._send(200, json.dumps({"ok": True, "avatar": value}))
                elif url.path == "/api/toggle":
                    module = qs.get("module", [""])[0]
                    if module in panel.mirror.modules:
                        panel.commands.put(("toggle", module))
                        self._send(200, json.dumps({"ok": True}))
                    else:
                        self._send(400, json.dumps({"error": "unknown module"}))
                elif url.path == "/api/state":
                    value = qs.get("value", [""])[0]
                    if value in ("active", "screensaver", "sleep"):
                        panel.commands.put(("state", value))
                        self._send(200, json.dumps({"ok": True}))
                    else:
                        self._send(400, json.dumps({"error": "bad state"}))
                elif url.path == "/api/tickers":
                    length = int(self.headers.get("Content-Length", 0) or 0)
                    body = self.rfile.read(length).decode("utf-8") if length else ""
                    # Accept newline- or comma-separated symbols
                    syms = [s.strip() for s in body.replace(",", "\n").splitlines()
                            if s.strip()]
                    panel.commands.put(("set_tickers", syms))
                    self._send(200, json.dumps({"ok": True, "count": len(syms)}))
                elif url.path == "/api/ha_entities":
                    length = int(self.headers.get("Content-Length", 0) or 0)
                    body = self.rfile.read(length).decode("utf-8") if length else ""
                    try:
                        ids = json.loads(body) if body else []
                        if not isinstance(ids, list):
                            ids = []
                    except Exception:
                        ids = [s.strip() for s in body.splitlines() if s.strip()]
                    panel.commands.put(("set_entities", ids))
                    self._send(200, json.dumps({"ok": True, "count": len(ids)}))
                else:
                    self._send(404, json.dumps({"error": "not found"}))

        try:
            self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        except OSError as e:
            logger.error(f"Web panel could not bind {self.host}:{self.port}: {e}")
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True, name="web-panel"
        )
        self._thread.start()
        logger.info(f"Web panel listening on http://{self.host}:{self.port}")

    def stop(self):
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            self._server = None

    # ----- data assembly --------------------------------------------------

    def status(self):
        import theme
        mm = self.mirror.module_manager
        director = getattr(self.mirror, "director", None)
        return {
            "state": self.mirror.state,
            "modules": {
                name: bool(mm.is_module_visible(name))
                for name in sorted(self.mirror.modules.keys())
            },
            "api": api_tracker.get_summary(),
            "moments": {
                "active": director.active_name if director else None,
                "guest_mode": bool(director.guest_mode) if director else False,
            } if director else None,
            "portal_ring": bool(theme.portal_ring_enabled),
        }

    def tail_log(self, lines):
        try:
            with open(_LOG_FILE, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 64 * 1024))
                text = f.read().decode("utf-8", errors="replace")
            return "\n".join(text.splitlines()[-lines:])
        except Exception as e:
            return f"(log unavailable: {e})"
