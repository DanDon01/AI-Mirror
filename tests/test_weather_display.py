#!/usr/bin/env python
"""Visual test: WeatherModule rendering in a standalone window (5 seconds)."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import load_env, create_test_window, run_display_loop

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    load_env()
    from weather_module import WeatherModule

    print("Testing WeatherModule display (5 seconds)...")
    print("  Press ESC or close window to exit early.")

    icons_path = os.path.join(_PROJECT_ROOT, "assets", "weather_icons")
    api_key = os.getenv("OPENWEATHERMAP_API_KEY")

    module = WeatherModule(
        api_key=api_key,
        city="Birmingham,UK",
        screen_width=400,
        screen_height=300,
        icons_path=icons_path,
    )

    # Fetch data before display loop
    print("  Fetching weather data...")
    module.update()
    if module.weather_data:
        source = getattr(module, "weather_source", "unknown")
        print(f"  Data received via {source}")
    else:
        print("  WARNING: No weather data received")

    screen, clock = create_test_window(400, 300, "Weather Module Test")

    def draw(screen, elapsed):
        module.draw(screen, {"x": 20, "y": 10, "width": 360, "height": 280})

    run_display_loop(screen, clock, draw, duration_seconds=5)
    print("  Weather display test complete.")


if __name__ == "__main__":
    main()
