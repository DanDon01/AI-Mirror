#!/usr/bin/env python
"""Visual test: RetroCharactersModule rendering in a standalone window (5 seconds)."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import create_test_window, run_display_loop

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    from retrocharacters_module import RetroCharactersModule

    print("Testing RetroCharactersModule display (5 seconds)...")
    print("  Press ESC or close window to exit early.")

    icons_path = os.path.join(_PROJECT_ROOT, "assets", "retro_icons")

    module = RetroCharactersModule(
        screen_size=(800, 600),
        icon_size=64,
        icon_directory=icons_path,
        spawn_probability=0.05,  # Higher spawn rate for testing
        fall_speed=2,
        max_active_icons=20,
        rotation_speed=2,
    )

    icon_count = len(getattr(module, "icons", []))
    print(f"  Loaded {icon_count} icon images")

    screen, clock = create_test_window(800, 600, "Retro Characters Test")

    def draw(screen, elapsed):
        module.update()
        module.draw(screen)

    run_display_loop(screen, clock, draw, duration_seconds=5)
    print("  Retro characters display test complete.")


if __name__ == "__main__":
    main()
