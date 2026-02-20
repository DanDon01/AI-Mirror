#!/usr/bin/env python
"""Visual test: VisualEffects methods in a standalone window (5 seconds)."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import create_test_window, run_display_loop


def main():
    import pygame
    from visual_effects import VisualEffects

    print("Testing VisualEffects (5 seconds)...")
    print("  Press ESC or close window to exit early.")

    effects = VisualEffects()
    screen, clock = create_test_window(600, 400, "Visual Effects Test")
    font = pygame.font.Font(None, 24)

    def draw(screen, elapsed):
        # 1. Rounded rectangle
        rect1 = pygame.Rect(20, 20, 160, 80)
        effects.draw_rounded_rect(screen, rect1, (40, 40, 80), radius=15, alpha=200)
        label1 = font.render("Rounded Rect", True, (200, 200, 200))
        screen.blit(label1, (30, 50))

        # 2. Gradient surface
        grad = effects.create_gradient_surface(160, 80, (0, 100, 200), (200, 50, 0))
        screen.blit(grad, (200, 20))
        label2 = font.render("Gradient", True, (255, 255, 255))
        screen.blit(label2, (230, 50))

        # 3. Pulse effect
        alpha = effects.pulse_effect(100, 255, speed=2.0)
        rect3 = pygame.Rect(380, 20, 160, 80)
        effects.draw_rounded_rect(screen, rect3, (100, 40, 40), radius=15, alpha=int(alpha))
        label3 = font.render(f"Pulse a={int(alpha)}", True, (255, 200, 200))
        screen.blit(label3, (400, 50))

        # 4. Text with shadow
        shadow_surf = effects.create_text_with_shadow(
            font, "Shadow Text", (255, 255, 255), (0, 0, 0), offset=(2, 2)
        )
        screen.blit(shadow_surf, (20, 140))

        # 5. Faded surface
        test_surf = pygame.Surface((160, 80), pygame.SRCALPHA)
        test_surf.fill((0, 200, 100))
        faded = effects.fade_surface(test_surf, 128)
        screen.blit(faded, (200, 140))
        label5 = font.render("Faded (a=128)", True, (200, 200, 200))
        screen.blit(label5, (210, 170))

        # Info
        info = font.render(f"elapsed: {elapsed}ms", True, (120, 120, 120))
        screen.blit(info, (20, 370))

    run_display_loop(screen, clock, draw, duration_seconds=5)
    print("  Visual effects test complete.")


if __name__ == "__main__":
    main()
