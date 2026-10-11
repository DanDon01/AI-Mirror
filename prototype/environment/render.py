"""Render the ENVIRONMENT prototype to a 1440x2560 PNG with headless Chrome.

Serves the folder over HTTP first, because the page fetches its sample
payload the same way it will fetch live state from the Python service.

    python render.py [out.png]
"""

import os
import shutil
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8791

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
]


def find_chrome():
    for path in CHROME_CANDIDATES:
        if os.path.exists(path):
            return path
    found = shutil.which("chromium") or shutil.which("google-chrome")
    if found:
        return found
    raise SystemExit("No Chrome/Chromium found")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else
                          os.path.join(HERE, "shot.png"))
    handler = partial(QuietHandler, directory=HERE)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.4)

    profile = os.path.join(HERE, ".chrome-profile")
    chrome = find_chrome()
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        "--window-size=1440,2560",
        f"--user-data-dir={profile}",
        "--virtual-time-budget=9000",
        f"--screenshot={out}",
        f"http://127.0.0.1:{PORT}/index.html",
    ]
    print("rendering...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    server.shutdown()

    if not os.path.exists(out):
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        raise SystemExit("screenshot not produced")
    print(f"saved {out}  ({os.path.getsize(out)//1024} KB)")


if __name__ == "__main__":
    main()
