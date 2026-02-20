#!/usr/bin/env python
"""Test OpenWeatherMap API connectivity."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import load_env, run_test, TestResult


def test_api_key():
    key = os.getenv("OPENWEATHERMAP_API_KEY")
    if not key:
        return False, "OPENWEATHERMAP_API_KEY not set"
    return True, f"key present ({len(key)} chars)"


def test_weather_fetch():
    import requests

    key = os.getenv("OPENWEATHERMAP_API_KEY")
    city = "Birmingham,UK"
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={key}&units=metric"
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}: {resp.text[:100]}"
    data = resp.json()
    temp = data["main"]["temp"]
    condition = data["weather"][0]["description"]
    name = data["name"]
    return True, f"{name}: {temp:.1f}C, {condition}"


def test_response_fields():
    import requests

    key = os.getenv("OPENWEATHERMAP_API_KEY")
    url = f"http://api.openweathermap.org/data/2.5/weather?q=Birmingham,UK&appid={key}&units=metric"
    resp = requests.get(url, timeout=10)
    data = resp.json()
    required_fields = ["main", "weather", "wind", "clouds", "sys", "name"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        return False, f"missing fields: {missing}"
    return True, "all required fields present"


def main():
    load_env()
    results = TestResult()

    print("Testing OpenWeatherMap API...")
    print("-" * 50)

    run_test("API key present", test_api_key, results)
    run_test("Weather fetch (Birmingham,UK)", test_weather_fetch, results)
    run_test("Response fields complete", test_response_fields, results)

    return results.summary()


if __name__ == "__main__":
    sys.exit(main())
