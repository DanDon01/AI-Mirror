#!/usr/bin/env python
"""Test that all required environment variables are set in Variables.env."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import load_env, TestResult

REQUIRED_KEYS = [
    "OPENAI_API_KEY",
    "OPENWEATHERMAP_API_KEY",
    "FITBIT_CLIENT_ID",
    "FITBIT_CLIENT_SECRET",
    "FITBIT_ACCESS_TOKEN",
    "FITBIT_REFRESH_TOKEN",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_ACCESS_TOKEN",
    "GOOGLE_REFRESH_TOKEN",
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
]

OPTIONAL_KEYS = [
    "OPENAI_VOICE_KEY",
    "OPENCLAW_GATEWAY_TOKEN",
]


def main():
    load_env()
    results = TestResult()

    print("Checking required environment variables...")
    print("-" * 50)

    for key in REQUIRED_KEYS:
        val = os.getenv(key)

        def check(k=key, v=val):
            if not v:
                return False, "NOT SET"
            if v in ("your-eleven-api-key", "your-voice-id", "your-openai-api-key"):
                return False, "placeholder value"
            return True, f"set ({len(v)} chars)"

        results.record(f"Required: {key}", *check())

    print("\nChecking optional environment variables...")
    print("-" * 50)

    for key in OPTIONAL_KEYS:
        val = os.getenv(key)
        if val:
            print(f"  [INFO] {key}: set ({len(val)} chars)")
        else:
            print(f"  [INFO] {key}: not set (optional)")

    return results.summary()


if __name__ == "__main__":
    sys.exit(main())
