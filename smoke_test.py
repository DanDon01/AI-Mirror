"""Headless smoke test for AI-Mirror.

Run after a git pull (deploy/deploy.sh does this) or in CI to catch
import errors and basic module breakage before restarting the mirror.
No network, no display, no audio hardware required.

Exit code 0 = pass, 1 = fail.
"""

import importlib
import os
import sys
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

PROJECT_MODULES = [
    "config",
    "module_base",
    "animation_manager",
    "layout_manager",
    "module_manager",
    "api_tracker",
    "background_fetcher",
    "data_cache",
    "visual_effects",
    "voice_commands",
    "weather_animations",
    "clock_module",
    "weather_module",
    "stocks_module",
    "calendar_module",
    "fitbit_module",
    "countdown_module",
    "quote_module",
    "news_module",
    "openclaw_module",
    "smarthome_module",
    "sysinfo_module",
    "greeting_module",
    "retrocharacters_module",
    "octopus_energy_module",
    "avatar_module",
    "web_panel",
    "ai_voice_module",
    "AI_Module",
    "elevenvoice_module",
]


def main():
    failures = []

    print("== Import check ==")
    for name in PROJECT_MODULES:
        try:
            importlib.import_module(name)
            print(f"  ok   {name}")
        except Exception as e:
            failures.append((name, e))
            print(f"  FAIL {name}: {e}")

    print("== Instantiation and draw check ==")
    try:
        import pygame
        pygame.init()
        screen = pygame.Surface((1440, 2560))

        from avatar_module import AvatarModule
        from greeting_module import GreetingModule
        from news_module import NewsModule
        from quote_module import QuoteModule

        instances = {
            "avatar": AvatarModule(size=320),
            "greeting": GreetingModule(rotation_interval=60),
            "news": NewsModule(),
            "quote": QuoteModule(),
        }
        pos = {"x": 20, "y": 20, "width": 320, "height": 320}
        for _ in range(30):
            for name, mod in instances.items():
                mod.update()
                mod.draw(screen, pos)
        for mod in instances.values():
            mod.cleanup()
        print("  ok   30 frames across avatar/greeting/news/quote")
    except Exception as e:
        failures.append(("frame-test", e))
        print(f"  FAIL frame test: {e}")
        traceback.print_exc()

    if failures:
        print(f"SMOKE TEST FAILED ({len(failures)} failure(s))")
        return 1
    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
