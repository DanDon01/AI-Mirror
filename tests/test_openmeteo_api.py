#!/usr/bin/env python
"""Test Open-Meteo API connectivity (no API key needed)."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import run_test, TestResult


def test_geocoding():
    import requests

    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": "Birmingham", "count": 5, "format": "json"}
    resp = requests.get(url, params=params, timeout=10)
    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}"
    data = resp.json()
    results = data.get("results", [])
    if not results:
        return False, "no results"
    # Find UK result
    uk = [r for r in results if r.get("country_code") == "GB"]
    if uk:
        r = uk[0]
        return True, f"{r['name']}, {r['country_code']}: ({r['latitude']}, {r['longitude']})"
    r = results[0]
    return True, f"{r['name']}, {r.get('country_code','?')}: ({r['latitude']}, {r['longitude']})"


def test_weather_fetch():
    import requests

    # Birmingham, UK coordinates
    lat, lon = 52.4862, -1.8904
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,pressure_msl",
        "wind_speed_unit": "ms",
    }
    resp = requests.get(url, params=params, timeout=10)
    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}"
    data = resp.json()
    current = data.get("current", {})
    temp = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")
    if temp is None:
        return False, "no temperature data"
    return True, f"temp={temp}C, humidity={humidity}%"


def test_response_fields():
    import requests

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": 52.4862,
        "longitude": -1.8904,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,pressure_msl,cloud_cover",
        "wind_speed_unit": "ms",
    }
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()
    current = data.get("current", {})
    expected = [
        "temperature_2m",
        "relative_humidity_2m",
        "apparent_temperature",
        "weather_code",
        "wind_speed_10m",
        "pressure_msl",
        "cloud_cover",
    ]
    missing = [f for f in expected if f not in current]
    if missing:
        return False, f"missing: {missing}"
    return True, "all requested fields present"


def main():
    results = TestResult()

    print("Testing Open-Meteo API (no key required)...")
    print("-" * 50)

    run_test("Geocoding (Birmingham)", test_geocoding, results)
    run_test("Weather fetch", test_weather_fetch, results)
    run_test("Response fields", test_response_fields, results)

    return results.summary()


if __name__ == "__main__":
    sys.exit(main())
