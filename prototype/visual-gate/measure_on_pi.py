"""Measure the visual gate on the Raspberry Pi 5.

Launches Chromium against the real page (served with the labelled
development fixture, through the same state endpoint production uses),
then samples SoC temperature, V3D clock, CPU and memory while the page
records its own frame times per scene - the set of layers on screen when
each frame was drawn ("bio", "house", "cal", "stage:probe", ...).

A single frame rate averaged over the whole loop hides which layer the Pi
struggles with; the per-scene table is the figure that matters.

Everything here has to run on the Pi. Frame rates measured on a desktop
with software WebGL say nothing about the real device.

    python3 measure_on_pi.py --seconds 480            full loop, ~6 passes
    python3 measure_on_pi.py --seconds 240 --probe    add the stage load probe
    python3 measure_on_pi.py --tier low --probe       pin a stage quality tier

Stop the mirror first so two Chromiums are not sharing the GPU:

    sudo systemctl stop ai-mirror-visual.service

Add --windowed to watch it rather than run it full screen.
"""

import argparse
import csv
import json
import os
import shutil
import statistics
import subprocess
import tempfile
import threading
import time
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

from serve import fixture_handler, free_port

HERE = os.path.dirname(os.path.abspath(__file__))
DEBUG_PORT = 9333
MIRROR_UNITS = ("ai-mirror-visual.service", "ai-mirror.service")

CHROMIUM = os.environ.get("MEASURE_CHROME") or next(
    (p for p in ("/usr/bin/chromium-browser", "/usr/bin/chromium",
                 "/usr/bin/google-chrome") if os.path.exists(p)),
    shutil.which("chromium") or shutil.which("chromium-browser"))


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


def throttled():
    """vcgencmd get_throttled: nonzero means undervoltage or thermal limits hit."""
    return vcgencmd("get_throttled") or "?"


_procs = {}


def _tree(root_pid):
    """The Chromium we launched and its children, never any other browser."""
    import psutil
    try:
        root = psutil.Process(root_pid)
        return [root] + root.children(recursive=True)
    except psutil.Error:
        return []


def chromium_usage(root_pid):
    """CPU% and RSS summed over our own Chromium process tree.

    Process objects are kept between calls: psutil's cpu_percent() is
    measured since the previous call on the same object, so a fresh
    object every sample would always read 0.0."""
    try:
        import psutil
    except ImportError:
        return float("nan"), float("nan")
    cpu = 0.0
    rss = 0
    for p in _tree(root_pid):
        p = _procs.setdefault(p.pid, p)
        try:
            cpu += p.cpu_percent(None)
            rss += p.memory_info().rss
        except psutil.Error:
            pass
    return cpu, rss / (1024 ** 2)


def other_chromium():
    """Chromium already running before we start: (process count, RSS MB)."""
    try:
        import psutil
    except ImportError:
        return 0, 0.0
    n, rss = 0, 0
    for proc in psutil.process_iter(["name", "memory_info"]):
        if "chrom" in (proc.info.get("name") or "").lower():
            n += 1
            mem = proc.info.get("memory_info")
            rss += mem.rss if mem else 0
    return n, rss / (1024 ** 2)


def mirror_running():
    active = []
    for unit in MIRROR_UNITS:
        try:
            state = subprocess.run(["systemctl", "is-active", unit], capture_output=True,
                                   text=True, timeout=4).stdout.strip()
        except Exception:
            continue
        if state == "active":
            active.append(unit)
    return active


def cdp_target(proc):
    """Wait for our page in DevTools, or for the browser to die trying."""
    for _ in range(90):
        if proc.poll() is not None:
            return None
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


def page_eval(ws_url, expression):
    try:
        from websockets.sync.client import connect
    except ImportError:
        return None
    payload = {"id": 1, "method": "Runtime.evaluate",
               "params": {"expression": expression, "returnByValue": True}}
    try:
        with connect(ws_url, open_timeout=5, close_timeout=2,
                     max_size=16 * 1024 * 1024) as ws:
            ws.send(json.dumps(payload))
            for _ in range(8):
                msg = json.loads(ws.recv(timeout=5))
                if msg.get("id") == 1:
                    value = msg["result"]["result"].get("value")
                    return json.loads(value) if value else None
    except Exception:
        return None
    return None


def percentile(bins, frames, q):
    """Percentile frame time (ms) from 1 ms histogram bins."""
    target = frames * q
    seen = 0
    for ms, n in enumerate(bins):
        seen += n
        if seen >= target:
            return ms + 0.5
    return float(len(bins))


def scene_table(scenes):
    rows = []
    for name, s in sorted(scenes.items(), key=lambda kv: -kv[1]["frames"]):
        if not s["frames"]:
            continue
        mean = s["ms"] / s["frames"]
        bins = s["bins"]
        over = sum(bins[34:])      # frames slower than ~30 fps
        rows.append({
            "scene": name, "frames": s["frames"],
            "fps": round(1000.0 / mean, 1) if mean else 0,
            "mean_ms": round(mean, 2),
            "p50_ms": percentile(bins, s["frames"], 0.50),
            "p95_ms": percentile(bins, s["frames"], 0.95),
            "worst_ms": round(s["worst"], 1),
            "below_30fps_pct": round(100.0 * over / s["frames"], 1),
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=480,
                    help="run length; the loop is 80 s, so 480 s covers six passes")
    ap.add_argument("--windowed", action="store_true")
    ap.add_argument("--headless", action="store_true",
                    help="plumbing check off the Pi only; its frame figures are meaningless")
    ap.add_argument("--probe", action="store_true",
                    help="add the stage load probe (?probe=1)")
    ap.add_argument("--tier", choices=("high", "mid", "low", "off"),
                    help="pin the stage quality tier instead of adapting")
    args = ap.parse_args()

    if not CHROMIUM:
        raise SystemExit(
            "Chromium not found. This script is meant to run on the Pi. "
            "Install it with: sudo apt install chromium-browser")

    running = mirror_running()
    if running:
        print("warning: " + ", ".join(running) + " is running; two Chromiums share the GPU "
              "and the figures will be pessimistic.\n  stop it first: sudo systemctl stop "
              + running[0] + "\n")
    n, rss = other_chromium()
    if n:
        print(f"warning: {n} Chromium process(es) already running ({rss:.0f} MB). They share "
              "the GPU with the measurement.\n  list them: pgrep -a chromium   "
              "stop them: pkill chromium\n")

    # Over SSH there is no display in the environment; the mirror's own
    # unit uses :0, so default to the same rather than failing silently.
    env = os.environ.copy()
    if not args.headless and not env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY"):
        env["DISPLAY"] = ":0"
        print("note: no DISPLAY set (SSH?); using DISPLAY=:0 like the mirror service\n")

    profile = tempfile.mkdtemp(prefix="visual-gate-measure-")
    log_path = os.path.join(profile, "chromium.log")

    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port),
                                 partial(fixture_handler(), directory=HERE))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.4)

    # fit=1 is what the mirror runs with (run.sh fits the 1440x2560 plate
    # to the real panel), so measure the same thing.
    query = "hud=1&fit=1"
    if args.probe:
        query += "&probe=1"
    if args.tier:
        query += "&tier=" + args.tier

    flags = [
        CHROMIUM,
        f"--remote-debugging-port={DEBUG_PORT}",
        # A private profile. Sharing the mirror's /tmp/visual-gate-profile
        # made Chromium hand the URL to an already-running mirror window
        # and exit, so DevTools never appeared.
        "--user-data-dir=" + profile,
        "--noerrdialogs", "--disable-infobars", "--no-first-run",
        "--autoplay-policy=no-user-gesture-required",
        # GPU path: this is the whole point of the exercise.
        "--ignore-gpu-blocklist",
        "--enable-gpu-rasterization",
        "--enable-zero-copy",
        "--disable-features=UseChromeOSDirectVideoDecoder",
        f"http://127.0.0.1:{port}/index.html?{query}",
    ]
    if args.headless:
        flags[1:1] = ["--headless=new", "--window-size=1440,2560"]
    else:
        flags.insert(1, "--window-size=1440,2560" if args.windowed else "--kiosk")

    print("launching chromium...")
    log = open(log_path, "w")
    proc = subprocess.Popen(flags, stdout=log, stderr=subprocess.STDOUT, env=env)
    ws_url = cdp_target(proc)
    if not ws_url:
        # Sampling a browser that is not there would waste the whole run.
        state = (f"exited with code {proc.returncode}" if proc.poll() is not None
                 else "is running but never exposed DevTools")
        proc.terminate()
        server.shutdown()
        log.close()
        tail = open(log_path, errors="replace").read().strip().splitlines()[-15:]
        raise SystemExit(f"Chromium {state}. Last lines of its log ({log_path}):\n  "
                         + "\n  ".join(tail or ["(empty)"]))

    # Prime psutil. The first cpu_percent() reading for any process is
    # always 0.0, so without a discarded pass the first sample lies.
    chromium_usage(proc.pid)
    time.sleep(1.0)

    rows = []
    perf = None
    print(f"sampling for {args.seconds}s   ({query})\n")
    print(f"{'t':>5} {'fps':>5} {'ms':>7} {'cpu%':>7} {'rss MB':>8} "
          f"{'temp C':>7} {'v3d MHz':>8}  scene")
    start = time.time()
    try:
        while time.time() - start < args.seconds:
            time.sleep(2.0)
            perf = page_eval(ws_url, "JSON.stringify(window.__perf||{})") if ws_url else perf
            cpu, rss = chromium_usage(proc.pid)
            row = {
                "t": round(time.time() - start, 1),
                "fps": (perf or {}).get("fps", ""),
                "frame_ms": (perf or {}).get("frame", ""),
                "cpu_pct": round(cpu, 1),
                "rss_mb": round(rss, 1),
                "temp_c": round(soc_temp_c(), 1),
                "v3d_mhz": round(v3d_mhz(), 1),
                "scene": (perf or {}).get("scene", ""),
            }
            rows.append(row)
            print(f"{row['t']:>5} {str(row['fps']):>5} {str(row['frame_ms']):>7} "
                  f"{row['cpu_pct']:>7} {row['rss_mb']:>8} "
                  f"{row['temp_c']:>7} {row['v3d_mhz']:>8}  {row['scene']}")
    except KeyboardInterrupt:
        pass
    finally:
        stage = page_eval(ws_url, "JSON.stringify(window.__stageInfo ? window.__stageInfo() : {})") if ws_url else None
        final = page_eval(ws_url, "JSON.stringify(window.__perf||{})") if ws_url else None
        perf = final or perf
        proc.terminate()
        server.shutdown()
        log.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)

    if not rows:
        return

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

    print("\nsystem")
    for key, label in (("cpu_pct", "chromium cpu %"), ("rss_mb", "chromium rss MB"),
                       ("temp_c", "soc temp C"), ("v3d_mhz", "v3d clock MHz")):
        print(f"  {label:18s} {summarise(key)}")
    print(f"  {'throttled':18s} {throttled()}   (0x0 = never throttled)")
    if stage:
        print(f"  {'stage':18s} tier {stage.get('tier')}  pinned {stage.get('pinned')}  "
              f"last actors {stage.get('actors')}")

    table = scene_table((perf or {}).get("scenes", {}))
    if table:
        print("\nper scene (frames timed in the page)")
        print(f"  {'scene':34s} {'frames':>7} {'fps':>6} {'p50':>6} {'p95':>6} "
              f"{'worst':>7} {'<30fps':>7}")
        for r in table:
            print(f"  {r['scene']:34s} {r['frames']:>7} {r['fps']:>6} {r['p50_ms']:>6} "
                  f"{r['p95_ms']:>6} {r['worst_ms']:>7} {r['below_30fps_pct']:>6}%")
        scenes_out = os.path.join(HERE, "pi-scenes.csv")
        with open(scenes_out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(table[0]))
            w.writeheader()
            w.writerows(table)
        print(f"\nwrote {out}\nwrote {scenes_out}")
    else:
        print(f"\nwrote {out}  (no per-scene figures: DevTools unreachable)")


if __name__ == "__main__":
    main()
