"""Shared test utilities for AI-Mirror test suite.

Usage from any test script:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from tests.test_helpers import load_env, run_test, create_test_window
"""

import os
import sys
import time
import logging

# Ensure project root is on the path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("TestHelper")


def load_env():
    """Load Variables.env using the same path logic as config.py."""
    from dotenv import load_dotenv

    env_path = os.path.join(_PROJECT_ROOT, "..", "Variables.env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
        logger.info(f"Loaded env from {os.path.abspath(env_path)}")
    else:
        logger.warning(f"Variables.env not found at {os.path.abspath(env_path)}")


class TestResult:
    """Collects and prints PASS/FAIL results."""

    def __init__(self):
        self.results = []

    def record(self, name, passed, detail=""):
        status = "PASS" if passed else "FAIL"
        self.results.append((name, passed, detail))
        marker = "[PASS]" if passed else "[FAIL]"
        msg = f"  {marker} {name}"
        if detail:
            msg += f" -- {detail}"
        print(msg)

    def summary(self):
        total = len(self.results)
        passed = sum(1 for _, p, _ in self.results if p)
        failed = total - passed
        print(f"\n{'='*50}")
        print(f"  Results: {passed}/{total} passed, {failed} failed")
        print(f"{'='*50}")
        return 0 if failed == 0 else 1


def run_test(name, fn, results):
    """Run a test function, catch exceptions, record result."""
    try:
        ok, detail = fn()
        results.record(name, ok, detail)
    except Exception as e:
        results.record(name, False, str(e))


def create_test_window(width, height, title="AI-Mirror Test"):
    """Create a pygame window for visual tests. Returns (screen, clock)."""
    import pygame

    pygame.init()
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption(title)
    clock = pygame.time.Clock()
    return screen, clock


def run_display_loop(screen, clock, draw_fn, duration_seconds=5, fps=30):
    """Run a pygame display loop for a fixed duration.

    draw_fn(screen, elapsed_ms) is called every frame.
    """
    import pygame

    start = time.time()
    running = True
    while running and (time.time() - start) < duration_seconds:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        elapsed = int((time.time() - start) * 1000)
        screen.fill((0, 0, 0))
        draw_fn(screen, elapsed)
        pygame.display.flip()
        clock.tick(fps)

    pygame.quit()
