"""Capture the transition sequence as a video.

Drives one Chromium instance over the DevTools protocol, stepping the
prototype's timeline by hand and grabbing a screenshot per frame, then
encodes with ffmpeg. Stepping rather than recording in real time means
the result is identical whatever the host's render speed — this machine
has no GPU path for WebGL, so a real-time capture here would say nothing
useful.

    python capture.py --from 3 --to 22 --fps 25

Real-time smoothness is a Pi measurement: see measure_on_pi.py.
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(HERE, ".frames")
PORT = 8795
DEBUG_PORT = 9334

CHROME = next((p for p in (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome",
) if os.path.exists(p)), shutil.which("chromium") or shutil.which("google-chrome"))


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def start_server():
    """Bind an ephemeral port and confirm it answers before launching the
    browser. A fixed port can collide with a listener left behind by an
    earlier run, and the browser then quietly gets connection refused."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=HERE))
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


def wait_for_target(url_fragment):
    for _ in range(60):
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=2) as r:
                for t in json.load(r):
                    if t.get("type") == "page" and url_fragment in t.get("url", ""):
                        return t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)
    raise SystemExit("DevTools target never appeared")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", type=float, default=3.0)
    ap.add_argument("--to", dest="end", type=float, default=22.0)
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--scale", type=int, default=720,
                    help="output width; 1440 for full resolution")
    args = ap.parse_args()

    from websockets.sync.client import connect

    if os.path.isdir(FRAMES):
        shutil.rmtree(FRAMES)
    os.makedirs(FRAMES)

    server, port = start_server()

    proc = subprocess.Popen([
        CHROME, "--headless=new", "--hide-scrollbars",
        "--force-device-scale-factor=1", "--window-size=1440,2560",
        "--use-gl=angle", "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader", "--disable-gpu-sandbox",
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={os.path.join(HERE, '.chrome-capture')}",
        f"http://127.0.0.1:{port}/index.html?manual=1",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    ws_url = wait_for_target("index.html")
    total = int((args.end - args.start) * args.fps)
    print(f"capturing {total} frames  t={args.start}..{args.end}")

    msg_id = 0

    def call(ws, method, params=None):
        nonlocal msg_id
        msg_id += 1
        mine = msg_id
        ws.send(json.dumps({"id": mine, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv(timeout=120))
            if msg.get("id") == mine:
                return msg.get("result", {})

    with connect(ws_url, open_timeout=20, close_timeout=5,
                 max_size=64 * 1024 * 1024) as ws:
        # Wait for the app to declare itself ready.
        for _ in range(120):
            res = call(ws, "Runtime.evaluate", {
                "expression": "!!document.body.dataset.ready", "returnByValue": True})
            if res.get("result", {}).get("value"):
                break
            time.sleep(0.5)

        started = time.time()
        for i in range(total):
            t = args.start + i / args.fps
            call(ws, "Runtime.evaluate", {
                "expression": f"window.__setTime({t:.4f})", "returnByValue": True})
            shot = call(ws, "Page.captureScreenshot", {"format": "jpeg", "quality": 92})
            with open(os.path.join(FRAMES, f"f{i:05d}.jpg"), "wb") as fh:
                fh.write(base64.b64decode(shot["data"]))
            if i % 25 == 0:
                rate = (i + 1) / max(time.time() - started, 1e-3)
                print(f"  {i+1}/{total}  ({rate:.1f} frames/s)")

    proc.terminate()
    server.shutdown()

    out = os.path.join(HERE, "shots", "transitions.mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-framerate", str(args.fps),
        "-i", os.path.join(FRAMES, "f%05d.jpg"),
        "-vf", f"scale={args.scale}:-2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
        out,
    ], check=True)
    print(f"wrote {out}  ({os.path.getsize(out)//1024} KB)")
    shutil.rmtree(FRAMES, ignore_errors=True)


if __name__ == "__main__":
    main()
