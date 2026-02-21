"""Fitbit OAuth2 re-authentication script.

Run on the Pi to refresh or re-authorize Fitbit tokens.
Tries refresh first; if that fails, runs full OAuth2 flow.
Updates Variables.env with new tokens.

Usage: python auth_fitbit.py
"""

import os
import sys
import base64
import requests
import webbrowser
import http.server
import urllib.parse
from dotenv import load_dotenv

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Variables.env')
REDIRECT_URI = "http://127.0.0.1:8080"
SCOPES = "activity heartrate sleep profile"
AUTH_URL = "https://www.fitbit.com/oauth2/authorize"
TOKEN_URL = "https://api.fitbit.com/oauth2/token"


def load_env():
    load_dotenv(ENV_FILE)
    return {
        'client_id': os.getenv('FITBIT_CLIENT_ID', ''),
        'client_secret': os.getenv('FITBIT_CLIENT_SECRET', ''),
        'access_token': os.getenv('FITBIT_ACCESS_TOKEN', ''),
        'refresh_token': os.getenv('FITBIT_REFRESH_TOKEN', ''),
    }


def save_tokens(access_token, refresh_token):
    with open(ENV_FILE, 'r') as f:
        lines = f.readlines()

    with open(ENV_FILE, 'w') as f:
        for line in lines:
            if line.startswith('FITBIT_ACCESS_TOKEN='):
                f.write(f"FITBIT_ACCESS_TOKEN={access_token}\n")
            elif line.startswith('FITBIT_REFRESH_TOKEN='):
                f.write(f"FITBIT_REFRESH_TOKEN={refresh_token}\n")
            else:
                f.write(line)

    print(f"Tokens saved to {ENV_FILE}")


def try_refresh(creds):
    """Attempt to refresh using existing refresh token."""
    if not creds['refresh_token']:
        print("No refresh token found, skipping refresh attempt")
        return False

    print("Attempting token refresh...")
    auth_header = base64.b64encode(
        f"{creds['client_id']}:{creds['client_secret']}".encode()
    ).decode()

    resp = requests.post(TOKEN_URL, headers={
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded",
    }, data={
        "grant_type": "refresh_token",
        "refresh_token": creds['refresh_token'],
    })

    if resp.status_code == 200:
        tokens = resp.json()
        print("Refresh successful!")
        save_tokens(tokens['access_token'], tokens['refresh_token'])
        return True
    else:
        print(f"Refresh failed ({resp.status_code}): {resp.text}")
        return False


def full_auth(creds):
    """Run full OAuth2 authorization code flow with local redirect."""
    print("\n--- Full OAuth2 Authorization ---")
    print("A browser window will open. Log in to Fitbit and authorize the app.")

    params = urllib.parse.urlencode({
        'response_type': 'code',
        'client_id': creds['client_id'],
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPES,
    })
    url = f"{AUTH_URL}?{params}"

    # Capture the auth code via a one-shot local HTTP server
    auth_code = None

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal auth_code
            query = urllib.parse.urlparse(self.path).query
            qs = urllib.parse.parse_qs(query)
            auth_code = qs.get('code', [None])[0]

            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<h2>Authorization complete. You can close this tab.</h2>")

        def log_message(self, format, *args):
            pass  # Suppress request logging

    server = http.server.HTTPServer(('127.0.0.1', 8080), Handler)

    print(f"\nOpening: {url}\n")
    webbrowser.open(url)

    print("If the browser didn't open, visit this URL manually:")
    print(url)
    print("\nWaiting for callback...")
    server.handle_request()
    server.server_close()

    if not auth_code:
        print("ERROR: No authorization code received")
        return False

    print("Authorization code received, exchanging for tokens...")

    auth_header = base64.b64encode(
        f"{creds['client_id']}:{creds['client_secret']}".encode()
    ).decode()

    resp = requests.post(TOKEN_URL, headers={
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded",
    }, data={
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": REDIRECT_URI,
    })

    if resp.status_code == 200:
        tokens = resp.json()
        print("Authorization successful!")
        save_tokens(tokens['access_token'], tokens['refresh_token'])
        return True
    else:
        print(f"Token exchange failed ({resp.status_code}): {resp.text}")
        return False


def main():
    print("=== Fitbit Re-Authentication ===\n")

    creds = load_env()
    if not creds['client_id'] or not creds['client_secret']:
        print("ERROR: FITBIT_CLIENT_ID and FITBIT_CLIENT_SECRET must be set in Variables.env")
        sys.exit(1)

    print(f"Client ID: {creds['client_id'][:8]}...")
    print(f"Refresh token: {'present' if creds['refresh_token'] else 'missing'}")

    # Try refresh first
    if try_refresh(creds):
        print("\nDone! Fitbit tokens are up to date.")
        return

    # Fall back to full auth
    if full_auth(creds):
        print("\nDone! Fitbit tokens are up to date.")
    else:
        print("\nFailed to authenticate. Check your client ID/secret.")
        sys.exit(1)


if __name__ == "__main__":
    main()
