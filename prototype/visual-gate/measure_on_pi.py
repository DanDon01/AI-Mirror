"""Measure the visual-gate prototype on the Raspberry Pi 5.

Launches Chromium against the prototype with GPU rasterisation enabled,
then samples the page's own frame timing alongside SoC temperature, V3D
clock, CPU and memory for the duration of a run.

Everything here has to run on the Pi. Frame rate measured on a desktop
with software WebGL says nothing about the real device.

    python3 measure_on_pi.py --seconds 120

Add --windowed to watch it rather than run it full screen.
"""

import argparse
import csv
import json
import os
import shutil
import statistics
import subprocess
import threading
import time
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8794
DEBUG_PORT = 9333

CHROMIUM = next(
    (p for p in ("/usr/bin/chromium-browser", "/usr/bin/chromium",
                 "/usr/bin/google-chrome") if os.path.exists(p)),
    shutil.which("chromium") or shutil.which("chromium-browser"))


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def vcgencmd(arg):
    try:
        out = subprocess.run(["vcgencmd"] + arg.split(), capture_output=True,
                             text=True, timeout=4).stdout.strip()
        return out.split("=", 1)[1] if "=" in out else out
    except Exception:
        return ""


def soc_temp_c():
    raw = vcgencmd("measure_temp")
    if raw.endswith("'C"):
        return float(raw[:-2])
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as fh:
            return int(fh.read().strip()) / 1000.0
    except Exception:
        return float("nan")


def v3d_mhz():
    raw = vcgencmd("measure_clock v3d")
    try:
        return int(raw) / 1e6
    except Exception:
        return float("nan")


def chromium_usage():
    """Aggregate CPU% and RSS across the Chromium process tree."""
    try:
        import psutil
    except ImportError:
        return float("nan"), float("nan")
    cpu = 0.0
    rss = 0
    for proc in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
        name = (proc.info.get("name") or "").lower()
        if "chrom" in name:
            cpu += proc.info.get("cpu_percent") or 0.0
            mem = proc.info.get("memory_info")
            if mem:
                rss += mem.rss
    return cpu, rss / (1024 ** 2)


def cdp_target():
    for _ in range(40):
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=2) as r:
                for t in json.load(r):
                    if t.get("type") == "page" and "index.html" in t.get("url", ""):
                        return t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)
    return None


def read_perf(ws_url):
    """Pull window.__perf out of the page over the DevTools protocol."""
    try:
        from websockets.sync.client import connect
    except ImportError:
        return None
    payload = {
        "id": 1,
        "method": "Runtime.evaluate",
        "params": {"expression": "JSON.stringify(window.__perf||{})",
                   "returnByValue": True},
    }
    try:
        with connect(ws_url, open_timeout=5, close_timeout=2) as ws:
            ws.send(json.dumps(payload))
            for _ in range(8):
                msg = json.loads(ws.recv(timeout=5))
                if msg.get("id") == 1:
                    value = msg["result"]["result"].get("value")
                    return json.loads(value) if value else None
    except Exception:
        return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=120)
    ap.add_argument("--windowed", action="store_true")
    args = ap.parse_args()

    if not CHROMIUM:
        raise SystemExit("Chromium not found")

    server = ThreadingHTTPServer(("127.0.0.1", PORT), partial(Quiet, directory=HERE))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.4)

    flags = [
        CHROMIUM,
        f"--remote-debugging-port={DEBUG_PORT}",
        "--user-data-dir=/tmp/visual-gate-profile",
        "--noerrdialogs", "--disable-infobars", "--no-first-run",
        "--autoplay-policy=no-user-gesture-required",
        # GPU path: this is the whole point of the exercise.
        "--ignore-gpu-blocklist",
        "--enable-gpu-rasterization",
        "--enable-zero-copy",
        "--disable-features=UseChromeOSDirectVideoDecoder",
        f"http://127.0.0.1:{PORT}/index.html?hud=1",
    ]
    flags.insert(1, "--window-size=1440,2560" if args.windowed else "--kiosk")

    print("launching chromium...")
    proc = subprocess.Popen(flags, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    ws_url = cdp_target()
    if not ws_url:
        print("warning: could not reach DevTools; FPS will be unavailable")

    rows = []
    print(f"sampling for {args.seconds}s\n")
    print(f"{'t':>5} {'fps':>5} {'ms':>7} {'cpu%':>7} {'rss MB':>8} "
          f"{'temp C':>7} {'v3d MHz':>8}")
    start = time.time()
    try:
        while time.time() - start < args.seconds:
            time.sleep(2.0)
            perf = read_perf(ws_url) if ws_url else None
            cpu, rss = chromium_usage()
            row = {
                "t": round(time.time() - start, 1),
                "fps": (perf or {}).get("fps", ""),
                "frame_ms": (perf or {}).get("frame", ""),
                "cpu_pct": round(cpu, 1),
                "rss_mb": round(rss, 1),
                "temp_c": round(soc_temp_c(), 1),
                "v3d_mhz": round(v3d_mhz(), 1),
            }
            rows.append(row)
            print(f"{row['t']:>5} {str(row['fps']):>5} {str(row['frame_ms']):>7} "
                  f"{row['cpu_pct']:>7} {row['rss_mb']:>8} "
                  f"{row['temp_c']:>7} {row['v3d_mhz']:>8}")
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        server.shutdown()

    if rows:
        out = os.path.join(HERE, "pi-measurements.csv")
        with open(out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

        def summarise(key):
            vals = [r[key] for r in rows if isinstance(r[key], (int, float))]
            if not vals:
                return "n/a"
            return (f"min {min(vals):.1f}  median {statistics.median(vals):.1f}  "
                    f"max {max(vals):.1f}")

        print("\nsummary")
        for key, label in (("fps", "frame rate"), ("frame_ms", "frame time ms"),
                           ("cpu_pct", "chromium cpu %"), ("rss_mb", "chromium rss MB"),
                           ("temp_c", "soc temp C"), ("v3d_mhz", "v3d clock MHz")):
            print(f"  {label:18s} {summarise(key)}")
        print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
