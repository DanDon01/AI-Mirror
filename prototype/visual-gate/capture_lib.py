"""Shared browser driving for stills and video.

One Chromium instance, driven over the DevTools protocol, with the page's
timeline stepped by hand. This machine has no GPU path for WebGL and
falls back to SwiftShader, so anything real-time here would be both slow
and meaningless; stepping makes output identical on any host.
"""

import base64
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))

CHROME = next((p for p in (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome",
) if os.path.exists(p)), shutil.which("chromium") or shutil.which("google-chrome"))


def start_server():
    """Ephemeral port, verified live before the browser is pointed at it.
    A fixed port can collide with a listener left by an earlier run, and
    the browser then quietly gets connection refused.

    Serves the labelled fixture through the real state endpoint: the page
    refuses unlabelled data, so a plain static server leaves it blank."""
    from serve import fixture_handler
    server = ThreadingHTTPServer(("127.0.0.1", 0),
                                 partial(fixture_handler(), directory=HERE))
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    for _ in range(40):
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/index.html", timeout=2) as r:
                if r.status == 200:
                    return server, port
        except Exception:
            time.sleep(0.25)
    raise SystemExit("local server did not come up")


class Session:
    def __init__(self, debug_port=9360, profile=".chrome-cap", width=1440, height=2560, query=""):
        self.debug_port = debug_port
        self.query = query
        self.profile = os.path.join(HERE, profile)
        self.width, self.height = width, height
        self._id = 0

    def __enter__(self):
        from websockets.sync.client import connect
        self.server, port = start_server()
        self.proc = subprocess.Popen([
            CHROME, "--headless=new", "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--window-size={self.width},{self.height}",
            "--use-gl=angle", "--use-angle=swiftshader",
            "--enable-unsafe-swiftshader", "--disable-gpu-sandbox",
            "--no-first-run", "--disable-extensions",
            f"--remote-debugging-port={self.debug_port}",
            f"--user-data-dir={self.profile}",
            f"http://127.0.0.1:{port}/index.html?manual=1{self.query}",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        ws_url = None
        for _ in range(80):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.debug_port}/json", timeout=2) as r:
                    for t in json.load(r):
                        if t.get("type") == "page" and "index.html" in t.get("url", ""):
                            ws_url = t["webSocketDebuggerUrl"]
            except Exception:
                pass
            if ws_url:
                break
            time.sleep(0.5)
        if not ws_url:
            raise SystemExit("DevTools target never appeared")

        self.ws = connect(ws_url, open_timeout=30, close_timeout=5,
                          max_size=96 * 1024 * 1024).__enter__()

        # --window-size sets the OUTER window, so the viewport came out at
        # 1424x2409 and every still was a silent crop of the plate: the
        # markets rail ran off the bottom of shots that looked fine.
        # Override the metrics so the viewport is exactly the mirror.
        self.call("Emulation.setDeviceMetricsOverride", {
            "width": self.width, "height": self.height,
            "deviceScaleFactor": 1, "mobile": False})

        # The scene loads 96k points and compiles shaders under a software
        # rasteriser; give it real time before expecting frames.
        for _ in range(240):
            if self.eval("document.body.dataset.ready === '1'"):
                break
            time.sleep(0.5)
        else:
            err = self.eval("document.body.dataset.error || '(no error set)'")
            raise SystemExit(f"page never became ready: {err}")
        return self

    def __exit__(self, *exc):
        try:
            self.ws.__exit__(*exc)
        except Exception:
            pass
        self.proc.terminate()
        self.server.shutdown()

    def call(self, method, params=None):
        self._id += 1
        mine = self._id
        self.ws.send(json.dumps({"id": mine, "method": method,
                                 "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv(timeout=300))
            if msg.get("id") == mine:
                return msg.get("result", {})

    def eval(self, expression, await_promise=False):
        res = self.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
            "awaitPromise": await_promise})
        return res.get("result", {}).get("value")

    def seek(self, t):
        self.eval(f"window.__setTime({t:.4f})")

    def shot(self, path, fmt="png", quality=92):
        params = {"format": fmt, "fromSurface": True, "captureBeyondViewport": False}
        if fmt == "jpeg":
            params["quality"] = quality
        data = self.call("Page.captureScreenshot", params)["data"]
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(data))
