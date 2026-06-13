"""Re-authorise Google Calendar and write fresh tokens to Variables.env.

Run this when the calendar logs `invalid_grant: Bad Request` - it means
the stored refresh token expired or was revoked (Google expires refresh
tokens after 7 days while the OAuth consent screen is in "Testing" mode;
publish it to "Production" to stop that happening).

Run on a machine WITH a browser (the Pi desktop is fine):

    ./venv/bin/python google_reauth.py

It opens a browser, you approve access, and GOOGLE_ACCESS_TOKEN /
GOOGLE_REFRESH_TOKEN in ../Variables.env are updated in place. Restart
the mirror afterwards.
"""

import os
import shutil
import sys

from dotenv import load_dotenv

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV = os.path.join(_PROJECT_DIR, "..", "Variables.env")

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# Fixed port so the redirect URL is predictable. If your OAuth client is
# a "Web application" type, add exactly this URL (with trailing slash) to
# its Authorized redirect URIs in Google Cloud Console. A "Desktop app"
# client needs no redirect URI registration at all (recommended).
REDIRECT_PORT = 8765


def _prepare_pi_browser():
    """Make the auth page open in a real browser on the Pi's screen.

    Over SSH, Python's webbrowser has no DISPLAY and falls back to a
    text browser (no JavaScript -> Google rejects it). Point it at the
    Pi's display and a graphical browser instead.
    """
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        os.environ["DISPLAY"] = ":0"
    for name in ("chromium-browser", "chromium", "firefox", "epiphany-browser"):
        path = shutil.which(name)
        if path:
            os.environ["BROWSER"] = path
            return name
    return None


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
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("ERROR: pip install google-auth-oauthlib", file=sys.stderr)
        return 1

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    browser = _prepare_pi_browser()
    if browser:
        print(f"Opening {browser} on the Pi's screen "
              f"(DISPLAY={os.environ.get('DISPLAY', '?')})...")
        print("Approve there. If nothing appears, the URL is also printed")
        print("below - open it in any browser that can reach this Pi.")
    else:
        print("No graphical browser found on the Pi. Open the URL below in")
        print("a browser that can reach this machine on localhost.")
    print()

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    # open_browser=True launches the Pi browser we just selected and ALSO
    # prints the URL as a fallback; offline+consent guarantees a refresh token
    creds = flow.run_local_server(
        port=REDIRECT_PORT, access_type="offline", prompt="consent",
        open_browser=True,
    )

    if not creds.refresh_token:
        print("ERROR: no refresh token returned - try again", file=sys.stderr)
        return 1

    _write_env(creds.token, creds.refresh_token)
    print(f"Updated GOOGLE_ACCESS_TOKEN and GOOGLE_REFRESH_TOKEN in {_ENV}")
    print("Restart the mirror:  sudo systemctl restart ai-mirror")
    return 0


if __name__ == "__main__":
    sys.exit(main())
