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

    source = None          # callable returning the payload dict
    bridge = None          # optional live bridge for control actions
    control_root = False

    def do_GET(self):
        if self.control_root and self.path.split("?")[0] in ("/", "/index.html"):
            self.path = "/control.html"
        if self.path.split("?")[0] == "/api/state.json":
            self._serve_state()
            return
        super().do_GET()

    def do_POST(self):
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
