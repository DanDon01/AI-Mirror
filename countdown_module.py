"""Countdown/Timer module for AI-Mirror.

Displays countdowns to configured events (holidays, birthdays, etc.)
and provides a voice-activated timer function.
"""

import pygame
import logging
import math
from datetime import datetime, timedelta
from config import (
    CONFIG, FONT_NAME, COLOR_FONT_DEFAULT, COLOR_FONT_TITLE,
    COLOR_FONT_BODY, COLOR_FONT_SMALL, COLOR_BG_MODULE_ALPHA,
    COLOR_BG_HEADER_ALPHA, TRANSPARENCY,
)
from visual_effects import VisualEffects
from config import draw_module_background_fallback

logger = logging.getLogger("Countdown")


class CountdownModule:
    """Displays countdowns to configured events and a voice-activated timer."""

    def __init__(self, events=None, **kwargs):
        """
        Args:
            events: list of dicts with 'name' and 'date' (YYYY-MM-DD) keys.
                    Example: [{'name': 'Christmas', 'date': '2026-12-25'}]
        """
        self.events = events or []
        self.effects = VisualEffects()
        self.timer_end = None
        self.timer_label = None
        self.title_font = None
        self.body_font = None
        self.small_font = None

    def _init_fonts(self):
        if self.title_font is None:
            styling = CONFIG.get("module_styling", {})
            fonts = styling.get("fonts", {})
            title_size = fonts.get("title", {}).get("size", 18)
            body_size = fonts.get("body", {}).get("size", 14)
            small_size = fonts.get("small", {}).get("size", 12)
            self.title_font = pygame.font.SysFont(FONT_NAME, title_size)
            self.body_font = pygame.font.SysFont(FONT_NAME, body_size)
            self.small_font = pygame.font.SysFont(FONT_NAME, small_size)

    def set_timer(self, seconds, label="Timer"):
        """Start a countdown timer for the given number of seconds."""
        self.timer_end = datetime.now() + timedelta(seconds=seconds)
        self.timer_label = label
        logger.info(f"Timer set: {label} for {seconds}s")

    def cancel_timer(self):
        """Cancel the active timer."""
        self.timer_end = None
        self.timer_label = None
        logger.info("Timer cancelled")

    def _get_countdowns(self):
        """Calculate days remaining for each configured event."""
        now = datetime.now()
        results = []
        for event in self.events:
            try:
                target = datetime.strptime(event["date"], "%Y-%m-%d")
                delta = target - now
                days = delta.days
                if days < 0:
                    # Event has passed this year, skip or show as past
                    continue
                results.append({
                    "name": event["name"],
                    "days": days,
                    "date": target,
                })
            except (ValueError, KeyError) as e:
                logger.warning(f"Invalid event config: {event} -- {e}")
        results.sort(key=lambda e: e["days"])
        return results

    def _get_timer_remaining(self):
        """Return seconds remaining on the active timer, or None."""
        if self.timer_end is None:
            return None
        remaining = (self.timer_end - datetime.now()).total_seconds()
        if remaining <= 0:
            return 0
        return remaining

    def update(self):
        pass

    def draw(self, screen, position):
        try:
            if isinstance(position, dict):
                x, y = position["x"], position["y"]
                width = position.get("width", 225)
                height = position.get("height", 200)
            else:
                x, y = position
                width, height = 225, 200

            self._init_fonts()

            styling = CONFIG.get("module_styling", {})
            radius = styling.get("radius", 15)
            padding = styling.get("spacing", {}).get("padding", 10)

            # Background
            module_rect = pygame.Rect(x - padding, y - padding, width, height)
            header_rect = pygame.Rect(x - padding, y - padding, width, 40)
            try:
                self.effects.draw_rounded_rect(screen, module_rect, COLOR_BG_MODULE_ALPHA, radius=radius, alpha=0)
                self.effects.draw_rounded_rect(screen, header_rect, COLOR_BG_HEADER_ALPHA, radius=radius, alpha=0)
            except Exception:
                draw_module_background_fallback(screen, x, y, width, height, padding)

            # Title
            title_surf = self.title_font.render("Countdowns", True, COLOR_FONT_TITLE)
            screen.blit(title_surf, (x + padding, y + padding))

            draw_y = y + 50

            # Active timer
            timer_remaining = self._get_timer_remaining()
            if timer_remaining is not None:
                if timer_remaining <= 0:
                    # Timer finished -- pulsing alert
                    pulse = int(128 + 127 * math.sin(pygame.time.get_ticks() / 200))
                    color = (255, pulse, pulse)
                    label = f"{self.timer_label}: TIME UP!"
                else:
                    color = (152, 251, 152)  # pastel green
                    mins = int(timer_remaining // 60)
                    secs = int(timer_remaining % 60)
                    label = f"{self.timer_label}: {mins:02d}:{secs:02d}"

                timer_surf = self.body_font.render(label, True, color)
                timer_surf.set_alpha(TRANSPARENCY)
                screen.blit(timer_surf, (x, draw_y))
                draw_y += 25

            # Event countdowns
            countdowns = self._get_countdowns()
            max_display = 5 if timer_remaining is None else 4

            for event in countdowns[:max_display]:
                days = event["days"]
                name = event["name"]

                if days == 0:
                    text = f"{name}: TODAY!"
                    color = (152, 251, 152)
                elif days == 1:
                    text = f"{name}: Tomorrow"
                    color = (173, 216, 230)
                elif days <= 7:
                    text = f"{name}: {days} days"
                    color = (173, 216, 230)
                elif days <= 30:
                    text = f"{name}: {days} days"
                    color = COLOR_FONT_BODY
                else:
                    text = f"{name}: {days} days"
                    color = COLOR_FONT_SMALL

                event_surf = self.body_font.render(text, True, color)
                event_surf.set_alpha(TRANSPARENCY)
                screen.blit(event_surf, (x, draw_y))

                # Date below
                date_str = event["date"].strftime("%d %b %Y")
                date_surf = self.small_font.render(date_str, True, COLOR_FONT_SMALL)
                date_surf.set_alpha(TRANSPARENCY)
                screen.blit(date_surf, (x + 10, draw_y + 18))

                draw_y += 35

            if not countdowns and timer_remaining is None:
                empty = self.body_font.render("No events configured", True, COLOR_FONT_SMALL)
                empty.set_alpha(TRANSPARENCY)
                screen.blit(empty, (x, draw_y))

        except Exception as e:
            logger.error(f"Error drawing countdown module: {e}")

    def cleanup(self):
        pass
