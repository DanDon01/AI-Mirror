"""Re-authorise Google Calendar and write fresh tokens to Variables.env.

Run this when the calendar logs `invalid_grant: Bad Request` - it means
the stored refresh token expired or was revoked (Google expires refresh
tokens after 7 days while the OAuth consent screen is in "Testing" mode;
publish it to "Production" to stop that happening).

    ./venv/bin/python google_reauth.py

Manual copy-paste flow (works on a headless Pi, over SSH, or anywhere -
no loopback web server has to be reachable):
  1. It prints a Google URL and tries to open it in the Pi's browser.
  2. You approve access in any browser.
  3. The browser lands on a localhost address that probably shows an
     error or won't load - that is fine. Copy the FULL address from the
     address bar and paste it back into the terminal.
  4. Fresh tokens are written to ../Variables.env. Restart the mirror.
"""

import os
import shutil
import sys
from urllib.parse import urlparse, parse_qs

from dotenv import load_dotenv

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV = os.path.join(_PROJECT_DIR, "..", "Variables.env")

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# Loopback redirect. Desktop OAuth clients accept any localhost/127.0.0.1
# port with no registration; we never actually serve on it (manual paste).
REDIRECT_URI = "http://localhost:8765/"


def _try_open_browser(url):
    """Best-effort open of the auth URL in a graphical browser on the Pi."""
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        os.environ["DISPLAY"] = ":0"
    for name in ("chromium-browser", "chromium", "firefox", "epiphany-browser"):
        path = shutil.which(name)
        if path:
            import subprocess
            try:
                subprocess.Popen(
                    [path, url], env=os.environ.copy(),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                return name
            except Exception:
                continue
    return None


def _extract_code(pasted):
    """Pull the auth code from a pasted redirect URL, or accept a raw code."""
    pasted = pasted.strip().strip('"').strip("'")
    if pasted.lower().startswith("http"):
        qs = parse_qs(urlparse(pasted).query)
        if "error" in qs:
            return None, qs["error"][0]
        code = qs.get("code", [None])[0]
        return code, None
    return pasted or None, None


def _write_env(token, refresh_token):
    """Update the two GOOGLE_*_TOKEN lines in place, preserve the rest."""
    with open(_ENV, "r") as f:
        lines = f.readlines()

    seen_access = seen_refresh = False
    out = []
    for line in lines:
        if line.startswith("GOOGLE_ACCESS_TOKEN="):
            out.append(f"GOOGLE_ACCESS_TOKEN={token}\n")
            seen_access = True
        elif line.startswith("GOOGLE_REFRESH_TOKEN="):
            out.append(f"GOOGLE_REFRESH_TOKEN={refresh_token}\n")
            seen_refresh = True
        else:
            out.append(line)
    if not seen_access:
        out.append(f"GOOGLE_ACCESS_TOKEN={token}\n")
    if not seen_refresh:
        out.append(f"GOOGLE_REFRESH_TOKEN={refresh_token}\n")

    with open(_ENV, "w") as f:
        f.writelines(out)


def main():
    load_dotenv(_ENV)
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("ERROR: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET missing from "
              f"{_ENV}", file=sys.stderr)
        return 1

    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        print("ERROR: pip install google-auth-oauthlib", file=sys.stderr)
        return 1

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }
    }

    flow = Flow.from_client_config(client_config, scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    # offline + consent guarantees a refresh token is returned
    auth_url, _ = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true"
    )

    browser = _try_open_browser(auth_url)
    print()
    print("=" * 68)
    if browser:
        print(f"Opened {browser} on the Pi screen. If it did not appear, open")
        print("this URL in any browser (phone/laptop is fine):")
    else:
        print("Open this URL in any browser (phone/laptop is fine):")
    print()
    print(auth_url)
    print()
    print("Approve access (click Advanced -> Go to ... (unsafe) if warned).")
    print("Your browser will then go to a 'localhost:8765' page that shows an")
    print("error or will not load - THAT IS NORMAL. Copy the full address")
    print("from the browser's address bar and paste it below.")
    print("=" * 68)
    print()

    try:
        pasted = input("Paste the localhost URL (or just the code): ")
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return 1

    code, err = _extract_code(pasted)
    if err:
        print(f"ERROR: Google returned '{err}' - re-run and try again.",
              file=sys.stderr)
        return 1
    if not code:
        print("ERROR: no authorisation code found in what you pasted.",
              file=sys.stderr)
        return 1

    try:
        flow.fetch_token(code=code)
    except Exception as e:
        print(f"ERROR: token exchange failed: {e}", file=sys.stderr)
        return 1

    creds = flow.credentials
    if not creds.refresh_token:
        print("ERROR: no refresh token returned. Revoke the app at "
              "https://myaccount.google.com/permissions and re-run.",
              file=sys.stderr)
        return 1

    _write_env(creds.token, creds.refresh_token)
    print()
    print(f"Updated GOOGLE_ACCESS_TOKEN and GOOGLE_REFRESH_TOKEN in {_ENV}")
    print("Restart the mirror:  sudo systemctl restart ai-mirror")
    return 0


if __name__ == "__main__":
    sys.exit(main())
