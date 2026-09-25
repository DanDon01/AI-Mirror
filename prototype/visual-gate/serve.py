"""Serve the visual gate with live data.

Static files exactly as python3 -m http.server did, plus one endpoint:

    /api/state.json   what the mirror currently knows

The page polls that. Everything it draws comes from there, and anything
absent from the payload is not drawn at all - a feed that is down makes
its panel stay away rather than show a number nobody measured.

    python3 serve.py                 live data, visual 8795 + controls 8780
    python3 serve.py --port 8795     live data, fixed port
    python3 serve.py --fixture       the development fixture instead

--fixture exists so the page can be worked on without credentials or a
network. It serves fixtures/DEV-FIXTURE.json through the same endpoint,
still carrying its _fixture flag, so the page knows what it is holding
and says so on screen.
"""

import argparse
import json
import logging
import os
import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
logger = logging.getLogger("serve")


class Handler(SimpleHTTPRequestHandler):
    """Static files, plus the state endpoint."""

    def end_headers(self):
        # Page code must never be served from a browser cache: after a
        # git pull the kiosk and the control page would otherwise keep
        # running the old HTML/JS against the new server. Revalidation is
        # cheap on the LAN (unchanged files answer 304).
        path = self.path.split("?")[0]
        if path == "/" or path.endswith((".html", ".js", ".css")):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    source = None          # callable returning the payload dict
    bridge = None          # optional live bridge for control actions
    control_root = False

    def do_GET(self):
        if self.control_root and self.path.split("?")[0] in ("/", "/index.html"):
            self.path = "/control.html"
        if self.path.split("?")[0] == "/api/state.json":
            self._serve_state()
            return
        if self.path.split("?")[0] == "/api/events":
            self._serve_events()
            return
        if self.path.split("?")[0] == "/api/avatar/thumb":
            from urllib.parse import parse_qs, urlsplit
            key = (parse_qs(urlsplit(self.path).query).get("key") or [""])[0]
            path = self.bridge.avatar_thumb(key) if self.bridge is not None else None
            if not path:
                self.send_error(404, "no such avatar")
                return
            with open(path, "rb") as fh:
                body = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split("?")[0] == "/api/resident/media":
            self._serve_resident_media()
            return
        if self.path.split("?")[0] == "/api/control/status":
            if self.bridge is None:
                self._json({"live": False, "modules": {}, "configured_entities": {}})
            else:
                self._json({"live": True, **self.bridge.control_status()})
            return
        if self.path.split("?")[0] == "/api/control/tuning":
            if self.bridge is None:
                self._json({"tuning": {}})
            else:
                self._json({"tuning": self.bridge.tuning.copy()})
            return
        if self.path.split("?")[0] in ("/api/avatars", "/api/tickers", "/api/modules"):
            if self.bridge is None:
                self._json({"error": "live bridge unavailable"})
            else:
                status = self.bridge.control_status()
                key = self.path.split("?")[0].rsplit("/", 1)[-1]
                self._json({"avatars": status["avatars"]} if key == "avatars" else
                           {"tickers": status["tickers"]} if key == "tickers" else
                           {"modules": status["visibility"]})
            return
        super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]
        if path in ("/api/moments/catalogue", "/api/moments/enabled", "/api/moments/play",
                    "/api/moments/played"):
            if self.bridge is None:
                self.send_error(503, "live bridge unavailable")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}") if length else {}
                if path == "/api/moments/catalogue":
                    self.bridge.moments_catalogue(payload if isinstance(payload, list) else [])
                    self._json({"ok": True})
                elif path == "/api/moments/enabled":
                    self._json({"ok": True, "enabled": self.bridge.moments_set_enabled(payload)})
                elif path == "/api/moments/play":
                    self.bridge.moments_play(payload.get("name", ""))
                    self._json({"ok": True})
                else:
                    self.bridge.moments_played(payload.get("name", ""), payload.get("reason", ""))
                    self._json({"ok": True})
            except (TypeError, ValueError, json.JSONDecodeError):
                self.send_error(400, "invalid moments request")
            return
        if path in ("/api/resident/talk", "/api/resident/done", "/api/resident/unprompted"):
            if self.bridge is None or getattr(self.bridge, "resident", None) is None:
                self.send_error(503, "resident unavailable")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}") if length else {}
                if path == "/api/resident/talk":
                    self._json({"ok": True, **self.bridge.resident_talk()})
                elif path == "/api/resident/done":
                    self.bridge.resident_finished(str(payload.get("clip", "")))
                    self._json({"ok": True})
                else:
                    self._json({"ok": True, **self.bridge.resident_unprompted_now()})
            except Exception as exc:
                logger.exception("resident action failed")
                self.send_error(409, str(exc))
            return
        if path == "/api/presence":
            if self.bridge is None:
                self.send_error(503, "live bridge unavailable")
                return
            self._json({"ok": True, "presence": self.bridge.ping_presence()})
            return
        if path == "/api/control/calendar-refresh":
            if self.bridge is None:
                self.send_error(503, "live bridge unavailable")
                return
            try:
                self._json({"ok": True, "queued": self.bridge.refresh_calendar()})
            except Exception:
                logger.exception("manual calendar refresh failed")
                self.send_error(500, "calendar refresh failed")
            return
        if path in ("/api/avatar", "/api/tickers", "/api/modules"):
            if self.bridge is None:
                self.send_error(503, "live bridge unavailable")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode("utf-8") if length else ""
                payload = json.loads(raw) if raw.startswith("{") else {"value": raw}
                if path == "/api/avatar":
                    result = {"avatar": self.bridge.select_avatar(payload.get("value", ""))}
                elif path == "/api/tickers":
                    symbols = payload.get("tickers", payload.get("value", ""))
                    if isinstance(symbols, str):
                        symbols = [item.strip() for item in symbols.replace(",", "\n").splitlines() if item.strip()]
                    result = {"tickers": self.bridge.set_tickers(symbols or [])}
                else:
                    result = {"modules": self.bridge.set_visibility(payload)}
                self._json({"ok": True, **result})
            except Exception as exc:
                self.send_error(400, str(exc))
            return
        if path in ("/api/control/config", "/api/control/tuning"):
            if self.bridge is None:
                self.send_error(503, "live bridge unavailable")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                updates = json.loads(self.rfile.read(length) or b"{}")
                if path == "/api/control/tuning":
                    self._json({"tuning": self.bridge.update_tuning(updates)})
                else:
                    self._json(self.bridge.update_gate(updates))
            except (TypeError, ValueError, json.JSONDecodeError):
                self.send_error(400, "invalid configuration")
            except Exception:
                logger.exception("visual-gate configuration update failed")
                self.send_error(500, "configuration update failed")
            return
        if self.path.split("?")[0] == "/api/control/pump":
            if self.bridge is None:
                self.send_error(503, "live bridge unavailable")
                return
            try:
                self.bridge.pump()
                self._json({"ok": True})
            except Exception:
                logger.exception("manual bridge pump failed")
                self.send_error(500, "pump failed")
            return
        self.send_error(404, "unknown control action")

    def _json(self, payload):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        self.wfile.write(body)

    def _serve_events(self):
        """Server-sent events: presence, resident and moment cues pushed the
        moment they happen, instead of waiting for the next two-second poll.
        One handler thread per open page; a 15 s comment keeps proxies and
        the browser from treating a quiet stream as dead."""
        hub = getattr(self.bridge, "events", None)
        if hub is None:
            self.send_error(404, "no event stream without the live bridge")
            return
        q = hub.subscribe()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            import queue
            while True:
                try:
                    event = q.get(timeout=15)
                    self.wfile.write(("data: " + json.dumps(event, default=str) + "\n\n").encode("utf-8"))
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            hub.unsubscribe(q)

    def _serve_resident_media(self):
        """A resident clip by opaque token, with byte ranges for <video>."""
        from urllib.parse import parse_qs, urlsplit
        token = (parse_qs(urlsplit(self.path).query).get("t") or [""])[0]
        path = self.bridge.resident_media(token) if self.bridge is not None else None
        if not path or not os.path.isfile(path):
            self.send_error(404, "no such clip")
            return
        size = os.path.getsize(path)
        start, end = 0, size - 1
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes="):
            first, _, last = rng[6:].partition("-")
            try:
                start = int(first) if first else max(0, size - int(last))
                end = int(last) if first and last else size - 1
            except ValueError:
                start, end = 0, size - 1
            end = min(end, size - 1)
            if start > end:
                self.send_error(416, "range not satisfiable")
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            with open(path, "rb") as fh:
                fh.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = fh.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _serve_state(self):
        try:
            payload = type(self).source()
        except Exception:
            logger.exception("state source failed")
            # 503 rather than an empty object: the page can tell the
            # difference between "nothing is happening" and "the data
            # layer fell over", and only the second is worth shouting
            # about in the log.
            self.send_error(503, "state unavailable")
            return

        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # The whole point is that it changes; never let it be cached.
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def fixture_source():
    with open(os.path.join(HERE, "fixtures", "DEV-FIXTURE.json"),
              encoding="utf-8") as fh:
        return json.load(fh)


def fixture_handler():
    """A quiet Handler serving the labelled fixture, for offline tools.

    Capture, validation and Pi measurement load the real page, which
    refuses unlabelled data, so they need the state endpoint and not a
    plain static server. The fixture keeps its _fixture flag and the
    page marks itself as a fixture on screen."""
    return type("FixtureHandler", (Handler,), {
        "source": staticmethod(fixture_source),
        "log_message": lambda self, *args: None,
    })


def free_port():
    """An ephemeral port, verified free. A fixed default can collide
    with a listener left by an earlier run, and the browser then quietly
    gets connection refused."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8795,
                    help="visual display port (default: 8795)")
    ap.add_argument("--bind", default="0.0.0.0",
                    help="interface to serve on (default: all interfaces)")
    ap.add_argument("--fixture", action="store_true",
                     help="serve the development fixture, not live data")
    ap.add_argument("--control-port", type=int, default=8780,
                    help="settings and diagnostics port (default: 8780; 0 disables)")
    ap.add_argument("--interval", type=float, default=1.0,
                    help="seconds between data refreshes")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    if args.fixture:
        Handler.source = fixture_source
        logger.warning("serving the DEVELOPMENT FIXTURE - not live data")
    else:
        import bridge
        live = bridge.start(interval=args.interval)
        Handler.source = live.snapshot
        Handler.bridge = live
        logger.info("live data; %d module(s) available: %s",
                    len(live.modules), ", ".join(sorted(live.modules)) or "none")

    port = args.port or free_port()
    visual_server = ThreadingHTTPServer((args.bind, port),
                                        partial(Handler, directory=HERE))
    threading.Thread(target=visual_server.serve_forever, daemon=True).start()
    logger.info("visual display on http://%s:%d/", args.bind, port)

    if args.control_port:
        ControlHandler = type("ControlHandler", (Handler,), {"control_root": True})
        control_server = ThreadingHTTPServer(
            (args.bind, args.control_port),
            partial(ControlHandler, directory=HERE),
        )
        threading.Thread(target=control_server.serve_forever, daemon=True).start()
        logger.info("control panel on http://%s:%d/", args.bind, args.control_port)
    print(port, flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
