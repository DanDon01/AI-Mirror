#!/usr/bin/env python
"""Integration test: initialize all modules, calculate layout, draw one frame.

Saves a screenshot to tests/integration_screenshot.png.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import load_env, TestResult

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    load_env()
    import pygame

    results = TestResult()

    print("Integration Test: Full module init + one draw cycle")
    print("-" * 50)

    # Initialize pygame
    pygame.init()
    screen = pygame.display.set_mode((800, 1280))
    pygame.display.set_caption("AI-Mirror Integration Test")

    modules = {}

    # Clock
    try:
        from clock_module import ClockModule

        modules["clock"] = ClockModule(
            time_font_size=60, date_font_size=30,
            color=(240, 240, 240), time_format="%H:%M:%S",
            date_format="%A, %B %d, %Y", timezone="local",
        )
        results.record("Init: ClockModule", True, "")
    except Exception as e:
        results.record("Init: ClockModule", False, str(e))

    # Weather
    try:
        from weather_module import WeatherModule

        modules["weather"] = WeatherModule(
            api_key=os.getenv("OPENWEATHERMAP_API_KEY"),
            city="Birmingham,UK",
            screen_width=800, screen_height=1280,
            icons_path=os.path.join(_PROJECT_ROOT, "assets", "weather_icons"),
        )
        results.record("Init: WeatherModule", True, "")
    except Exception as e:
        results.record("Init: WeatherModule", False, str(e))

    # Stocks
    try:
        from stocks_module import StocksModule

        modules["stocks"] = StocksModule(
            tickers=["AAPL", "GOOGL", "MSFT", "TSLA"],
        )
        results.record("Init: StocksModule", True, "")
    except Exception as e:
        results.record("Init: StocksModule", False, str(e))

    # Retro Characters
    try:
        from retrocharacters_module import RetroCharactersModule

        modules["retro"] = RetroCharactersModule(
            screen_size=(800, 1280), icon_size=64,
            icon_directory=os.path.join(_PROJECT_ROOT, "assets", "retro_icons"),
            spawn_probability=0.1, fall_speed=2,
            max_active_icons=10, rotation_speed=1,
        )
        results.record("Init: RetroCharactersModule", True, "")
    except Exception as e:
        results.record("Init: RetroCharactersModule", False, str(e))

    # Layout
    try:
        from layout_manager import LayoutManager

        layout = LayoutManager(800, 1280)
        positions = layout.calculate_positions(list(modules.keys()))
        results.record("LayoutManager positions", True, f"{len(positions)} positions calculated")
    except Exception as e:
        results.record("LayoutManager positions", False, str(e))
        positions = {}

    # Update all modules
    print("\n  Updating modules (fetching data)...")
    for name, module in modules.items():
        try:
            if hasattr(module, "update"):
                module.update()
            results.record(f"Update: {name}", True, "")
        except Exception as e:
            results.record(f"Update: {name}", False, str(e))

    # Draw one frame
    screen.fill((0, 0, 0))
    for name, module in modules.items():
        try:
            if hasattr(module, "draw"):
                pos = positions.get(name, {"x": 20, "y": 20, "width": 225, "height": 200})
                module.draw(screen, pos)
            results.record(f"Draw: {name}", True, "")
        except Exception as e:
            results.record(f"Draw: {name}", False, str(e))

    pygame.display.flip()

    # Save screenshot
    screenshot_path = os.path.join(os.path.dirname(__file__), "integration_screenshot.png")
    try:
        pygame.image.save(screen, screenshot_path)
        results.record("Screenshot saved", True, screenshot_path)
    except Exception as e:
        results.record("Screenshot saved", False, str(e))

    pygame.quit()

    return results.summary()


if __name__ == "__main__":
    sys.exit(main())
