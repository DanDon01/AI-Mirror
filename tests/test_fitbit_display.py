#!/usr/bin/env python
"""Visual test: FitbitModule rendering in a standalone window (5 seconds)."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import load_env, create_test_window, run_display_loop


def main():
    load_env()
    from fitbit_module import FitbitModule

    print("Testing FitbitModule display (5 seconds)...")
    print("  Press ESC or close window to exit early.")

    config = {
        "client_id": os.getenv("FITBIT_CLIENT_ID"),
        "client_secret": os.getenv("FITBIT_CLIENT_SECRET"),
        "access_token": os.getenv("FITBIT_ACCESS_TOKEN"),
        "refresh_token": os.getenv("FITBIT_REFRESH_TOKEN"),
    }

    module = FitbitModule(config=config)

    print("  Fetching Fitbit data...")
    module.update()

    screen, clock = create_test_window(400, 300, "Fitbit Module Test")

    def draw(screen, elapsed):
        module.draw(screen, {"x": 20, "y": 10, "width": 360, "height": 280})

    run_display_loop(screen, clock, draw, duration_seconds=5)
    print("  Fitbit display test complete.")


if __name__ == "__main__":
    main()
