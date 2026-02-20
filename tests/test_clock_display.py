#!/usr/bin/env python
"""Visual test: ClockModule rendering in a standalone window (5 seconds)."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import create_test_window, run_display_loop


def main():
    from clock_module import ClockModule

    print("Testing ClockModule display (5 seconds)...")
    print("  Press ESC or close window to exit early.")

    module = ClockModule(
        time_font_size=60,
        date_font_size=30,
        color=(240, 240, 240),
        time_format="%H:%M:%S",
        date_format="%A, %B %d, %Y",
        timezone="local",
    )

    screen, clock = create_test_window(800, 200, "Clock Module Test")

    def draw(screen, elapsed):
        module.update()
        module.draw(screen, (0, 20))

    run_display_loop(screen, clock, draw, duration_seconds=5)
    print("  Clock display test complete.")


if __name__ == "__main__":
    main()
