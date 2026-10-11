#!/usr/bin/env python
"""Test Fitbit API connectivity and OAuth2 credentials."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import load_env, run_test, TestResult


def test_credentials_present():
    keys = ["FITBIT_CLIENT_ID", "FITBIT_CLIENT_SECRET", "FITBIT_ACCESS_TOKEN", "FITBIT_REFRESH_TOKEN"]
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        return False, f"missing: {', '.join(missing)}"
    return True, "all 4 Fitbit credentials set"


def test_token_refresh():
    import requests
    import base64

    client_id = os.getenv("FITBIT_CLIENT_ID")
    client_secret = os.getenv("FITBIT_CLIENT_SECRET")
    refresh_token = os.getenv("FITBIT_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        return False, "credentials missing"

    auth_string = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = requests.post(
        "https://api.fitbit.com/oauth2/token",
        headers={
            "Authorization": f"Basic {auth_string}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=10,
    )
    if resp.status_code != 200:
        return False, f"token refresh failed: HTTP {resp.status_code} - {resp.text[:100]}"
    data = resp.json()
    if "access_token" not in data:
        return False, "no access_token in response"
    return True, f"new token obtained ({len(data['access_token'])} chars)"


def test_activity_fetch():
    import requests
    from datetime import date

    access_token = os.getenv("FITBIT_ACCESS_TOKEN")
    if not access_token:
        return False, "FITBIT_ACCESS_TOKEN not set"

    today = date.today().strftime("%Y-%m-%d")
    resp = requests.get(
        f"https://api.fitbit.com/1/user/-/activities/date/{today}.json",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if resp.status_code == 401:
        return False, "token expired (run token refresh first)"
    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}"
    data = resp.json()
    summary = data.get("summary", {})
    steps = summary.get("steps", "?")
    calories = summary.get("caloriesOut", "?")
    return True, f"steps={steps}, calories={calories}"


def main():
    load_env()
    results = TestResult()

    print("Testing Fitbit API...")
    print("-" * 50)

    run_test("Credentials present", test_credentials_present, results)
    run_test("Token refresh", test_token_refresh, results)
    run_test("Activity fetch (today)", test_activity_fetch, results)

    return results.summary()


if __name__ == "__main__":
    sys.exit(main())
