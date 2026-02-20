#!/usr/bin/env python
"""Visual test: CalendarModule rendering in a standalone window (5 seconds)."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import load_env, create_test_window, run_display_loop


def main():
    load_env()
    from calendar_module import CalendarModule

    print("Testing CalendarModule display (5 seconds)...")
    print("  Press ESC or close window to exit early.")

    config = {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "access_token": os.getenv("GOOGLE_ACCESS_TOKEN"),
        "refresh_token": os.getenv("GOOGLE_REFRESH_TOKEN"),
    }

    module = CalendarModule(config=config)

    print("  Fetching calendar events...")
    module.update()
    events = getattr(module, "events", [])
    print(f"  {len(events)} events loaded")

    screen, clock = create_test_window(400, 400, "Calendar Module Test")

    def draw(screen, elapsed):
        module.draw(screen, {"x": 20, "y": 10, "width": 360, "height": 380})

    run_display_loop(screen, clock, draw, duration_seconds=5)
    print("  Calendar display test complete.")


if __name__ == "__main__":
    main()
