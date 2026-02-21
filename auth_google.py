"""Google Calendar OAuth2 re-authentication script.

Run on the Pi to refresh or re-authorize Google Calendar tokens.
Tries refresh first; if that fails, runs full OAuth2 flow.
Updates Variables.env with new tokens.

Usage: python auth_google.py
"""

import os
import sys
import json
import webbrowser
import http.server
import urllib.parse
import requests
from dotenv import load_dotenv

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Variables.env')
REDIRECT_URI = "http://127.0.0.1:8090"
SCOPES = "https://www.googleapis.com/auth/calendar.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def load_env():
    load_dotenv(ENV_FILE)
    return {
        'client_id': os.getenv('GOOGLE_CLIENT_ID', ''),
        'client_secret': os.getenv('GOOGLE_CLIENT_SECRET', ''),
        'access_token': os.getenv('GOOGLE_ACCESS_TOKEN', ''),
        'refresh_token': os.getenv('GOOGLE_REFRESH_TOKEN', ''),
    }


def save_tokens(access_token, refresh_token):
    with open(ENV_FILE, 'r') as f:
        lines = f.readlines()

    found_access = False
    found_refresh = False

    with open(ENV_FILE, 'w') as f:
        for line in lines:
            if line.startswith('GOOGLE_ACCESS_TOKEN='):
                f.write(f"GOOGLE_ACCESS_TOKEN={access_token}\n")
                found_access = True
            elif line.startswith('GOOGLE_REFRESH_TOKEN='):
                f.write(f"GOOGLE_REFRESH_TOKEN={refresh_token}\n")
                found_refresh = True
            else:
                f.write(line)

        # Add lines if they didn't exist
        if not found_access:
            f.write(f"GOOGLE_ACCESS_TOKEN={access_token}\n")
        if not found_refresh:
            f.write(f"GOOGLE_REFRESH_TOKEN={refresh_token}\n")

    print(f"Tokens saved to {ENV_FILE}")


def try_refresh(creds):
    """Attempt to refresh using existing refresh token."""
    if not creds['refresh_token']:
        print("No refresh token found, skipping refresh attempt")
        return False

    print("Attempting token refresh...")

    resp = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": creds['refresh_token'],
        "client_id": creds['client_id'],
        "client_secret": creds['client_secret'],
    })

    if resp.status_code == 200:
        tokens = resp.json()
        print("Refresh successful!")
        # Google refresh responses may not include a new refresh_token
        new_refresh = tokens.get('refresh_token', creds['refresh_token'])
        save_tokens(tokens['access_token'], new_refresh)
        return True
    else:
        print(f"Refresh failed ({resp.status_code}): {resp.text}")
        return False


def full_auth(creds):
    """Run full OAuth2 authorization code flow with local redirect."""
    print("\n--- Full OAuth2 Authorization ---")
    print("A browser window will open. Log in to Google and authorize calendar access.")

    params = urllib.parse.urlencode({
        'response_type': 'code',
        'client_id': creds['client_id'],
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPES,
        'access_type': 'offline',
        'prompt': 'consent',  # Force consent to get a refresh_token
    })
    url = f"{AUTH_URL}?{params}"

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
            pass

    server = http.server.HTTPServer(('127.0.0.1', 8090), Handler)

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

    resp = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": creds['client_id'],
        "client_secret": creds['client_secret'],
    })

    if resp.status_code == 200:
        tokens = resp.json()
        refresh = tokens.get('refresh_token', '')
        if not refresh:
            print("WARNING: No refresh_token in response. Token will expire.")
            print("You may need to revoke access at https://myaccount.google.com/permissions")
            print("and run this script again.")
        print("Authorization successful!")
        save_tokens(tokens['access_token'], refresh or creds['refresh_token'])
        return True
    else:
        print(f"Token exchange failed ({resp.status_code}): {resp.text}")
        return False


def verify_token(creds):
    """Quick test that the token works."""
    print("\nVerifying token with Google Calendar API...")
    resp = requests.get(
        "https://www.googleapis.com/calendar/v3/calendars/primary",
        headers={"Authorization": f"Bearer {creds['access_token']}"},
    )
    if resp.status_code == 200:
        cal = resp.json()
        print(f"Connected to calendar: {cal.get('summary', 'unknown')}")
        return True
    else:
        print(f"Verification failed ({resp.status_code})")
        return False


def main():
    print("=== Google Calendar Re-Authentication ===\n")

    creds = load_env()
    if not creds['client_id'] or not creds['client_secret']:
        print("ERROR: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in Variables.env")
        sys.exit(1)

    print(f"Client ID: {creds['client_id'][:20]}...")
    print(f"Refresh token: {'present' if creds['refresh_token'] else 'missing'}")

    # Try refresh first
    if try_refresh(creds):
        # Reload and verify
        creds = load_env()
        verify_token(creds)
        print("\nDone! Google Calendar tokens are up to date.")
        return

    # Fall back to full auth
    if full_auth(creds):
        creds = load_env()
        verify_token(creds)
        print("\nDone! Google Calendar tokens are up to date.")
    else:
        print("\nFailed to authenticate. Check your client ID/secret.")
        print("Also ensure http://127.0.0.1:8090 is in your OAuth redirect URIs")
        print("in the Google Cloud Console.")
        sys.exit(1)


if __name__ == "__main__":
    main()
