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
  body { background:#0a0a0c; color:#b9b9be; font-family:'Segoe UI',sans-serif;
         margin:0; padding:16px; max-width:640px; margin:auto; }
  h1 { color:#5ac3ff; font-weight:300; font-size:1.5em; margin:8px 0 16px; }
  h2 { color:#468cdc; font-size:0.95em; text-transform:uppercase;
       letter-spacing:1px; margin:22px 0 8px; font-weight:500; }
  .row { display:flex; flex-wrap:wrap; gap:8px; }
  button { background:#16161a; color:#b9b9be; border:1px solid #2a2a30;
           border-radius:8px; padding:10px 14px; font-size:0.95em;
           cursor:pointer; flex:1 1 28%; min-width:90px; }
  button.on { border-color:#2e7d4f; color:#7fd9a4; }
  button.off { opacity:0.55; }
  button.state-active { border-color:#5ac3ff; color:#5ac3ff; }
  table { width:100%; border-collapse:collapse; font-size:0.85em; }
  td, th { padding:4px 6px; text-align:left; border-bottom:1px solid #1c1c22; }
  th { color:#8c8c91; font-weight:500; }
  pre { background:#101014; border:1px solid #1c1c22; border-radius:8px;
        padding:10px; font-size:0.72em; overflow-x:auto; white-space:pre-wrap;
        max-height:300px; overflow-y:auto; }
  .meta { color:#5a5a5f; font-size:0.8em; margin-top:4px; }
</style>
</head>
<body>
<h1>AI-Mirror</h1>

<h2>State</h2>
<div class="row" id="states"></div>

<h2>Modules</h2>
<div class="row" id="modules"></div>

<h2>API usage (24h)</h2>
<table id="api"><thead>
<tr><th>Service</th><th>Day</th><th>Hour</th><th>Cost</th></tr>
</thead><tbody></tbody></table>
<div class="meta" id="apiTotals"></div>

<h2>Recent log</h2>
<pre id="log">loading...</pre>

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
}

async function refreshLog() {
  const r = await fetch("/api/logs?lines=60");
  document.getElementById("log").textContent = await r.text();
}

async function refresh() {
  try { render(await getStatus()); } catch (e) {}
}

refresh();
refreshLog();
setInterval(refresh, 5000);
setInterval(refreshLog, 10000);
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
                else:
                    self._send(404, json.dumps({"error": "not found"}))

            def do_POST(self):
                url = urlparse(self.path)
                qs = parse_qs(url.query)
                if url.path == "/api/toggle":
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
        mm = self.mirror.module_manager
        return {
            "state": self.mirror.state,
            "modules": {
                name: bool(mm.is_module_visible(name))
                for name in sorted(self.mirror.modules.keys())
            },
            "api": api_tracker.get_summary(),
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
