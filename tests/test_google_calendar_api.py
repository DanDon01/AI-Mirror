#!/usr/bin/env python
"""Test Google Calendar API connectivity and OAuth2 credentials."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import load_env, run_test, TestResult


def test_credentials_present():
    keys = ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_ACCESS_TOKEN", "GOOGLE_REFRESH_TOKEN"]
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        return False, f"missing: {', '.join(missing)}"
    return True, "all 4 Google credentials set"


def test_token_refresh():
    import requests

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        return False, "credentials missing, cannot test refresh"

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=10,
    )
    if resp.status_code != 200:
        return False, f"token refresh failed: HTTP {resp.status_code}"
    data = resp.json()
    if "access_token" not in data:
        return False, "no access_token in response"
    return True, f"new token obtained ({len(data['access_token'])} chars)"


def test_event_listing():
    import requests
    from datetime import datetime, timezone

    # First refresh the token
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        return False, "credentials missing"

    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=10,
    )
    if token_resp.status_code != 200:
        return False, "could not refresh token"

    access_token = token_resp.json()["access_token"]
    now = datetime.now(timezone.utc).isoformat()

    resp = requests.get(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"timeMin": now, "maxResults": 5, "singleEvents": True, "orderBy": "startTime"},
        timeout=10,
    )
    if resp.status_code != 200:
        return False, f"event list failed: HTTP {resp.status_code}"
    data = resp.json()
    events = data.get("items", [])
    return True, f"{len(events)} upcoming events found"


def main():
    load_env()
    results = TestResult()

    print("Testing Google Calendar API...")
    print("-" * 50)

    run_test("Credentials present", test_credentials_present, results)
    run_test("Token refresh", test_token_refresh, results)
    run_test("Event listing", test_event_listing, results)

    return results.summary()


if __name__ == "__main__":
    sys.exit(main())
