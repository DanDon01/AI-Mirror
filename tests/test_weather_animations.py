#!/usr/bin/env python
"""Visual test: Cycle through all 6 weather animation types (30 seconds total)."""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import create_test_window


def main():
    import pygame
    from weather_animations import (
        CloudAnimation,
        RainAnimation,
        SunAnimation,
        StormAnimation,
        SnowAnimation,
        MoonAnimation,
    )

    print("Testing Weather Animations (5 seconds each, 30 seconds total)...")
    print("  Press ESC or close window to exit early.")

    width, height = 800, 600
    screen, clock = create_test_window(width, height, "Weather Animations Test")
    font = pygame.font.Font(None, 36)

    animations = [
        ("Sun (Clear)", lambda: SunAnimation(width, height)),
        ("Clouds (Partly)", lambda: CloudAnimation(width, height, partly=True)),
        ("Rain (Heavy)", lambda: RainAnimation(width, height, heavy=True)),
        ("Storm", lambda: StormAnimation(width, height)),
        ("Snow", lambda: SnowAnimation(width, height)),
        ("Moon", lambda: MoonAnimation(width, height)),
    ]

    for name, create_fn in animations:
        print(f"  Showing: {name}")
        try:
            anim = create_fn()
        except Exception as e:
            print(f"    ERROR creating {name}: {e}")
            continue

        start = time.time()
        running = True
        while running and (time.time() - start) < 5:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    return

            screen.fill((20, 20, 40))
            anim.update()
            anim.draw(screen)

            label = font.render(name, True, (255, 255, 255))
            screen.blit(label, (10, 10))

            remaining = 5 - (time.time() - start)
            timer = font.render(f"{remaining:.1f}s", True, (180, 180, 180))
            screen.blit(timer, (width - 80, 10))

            pygame.display.flip()
            clock.tick(30)

    pygame.quit()
    print("  Weather animations test complete.")


if __name__ == "__main__":
    main()
