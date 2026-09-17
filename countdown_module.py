"""Countdown/Timer module for AI-Mirror.

Displays countdowns to configured events (holidays, birthdays, etc.)
and provides a voice-activated timer function.
"""

import pygame
import logging
import math
from datetime import datetime, timedelta
from config import (
    CONFIG, FONT_NAME, COLOR_FONT_DEFAULT,
    COLOR_FONT_BODY, COLOR_FONT_SMALL, TRANSPARENCY, COLOR_ACCENT_AMBER,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_DIM, LABEL_TRACKING,
    load_font,
)
from effects_kit import draw_hero_glow

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
        self.timer_end = None
        self.timer_label = None
        self._notify = None
        self._moment_notify = None
        self._timer_notified = False
        self.title_font = None
        self.body_font = None
        self.small_font = None

    def _init_fonts(self):
        if self.title_font is None:
            self.title_font = load_font('regular', 18)
            self.body_font = load_font('regular', 14)
            self.small_font = load_font('regular', 12)
            self.hero_font = load_font('light', 52)
            self.hero_unit_font = load_font('regular', 14)

    def set_notification_callback(self, callback):
        """Register a callback for center-screen notifications."""
        self._notify = callback

    def set_moment_callback(self, callback):
        """Register a callback for Director moment triggers (event_director.py)."""
        self._moment_notify = callback

    def set_timer(self, seconds, label="Timer"):
        """Start a countdown timer for the given number of seconds."""
        self.timer_end = datetime.now() + timedelta(seconds=seconds)
        self.timer_label = label
        self._timer_notified = False
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
        # Push center notification when timer completes
        remaining = self._get_timer_remaining()
        if remaining is not None and remaining <= 0 and not self._timer_notified:
            self._timer_notified = True
            if self._notify:
                self._notify(
                    f"{self.timer_label}: TIME UP!",
                    color=(255, 120, 120),
                    duration_ms=8000,
                )
            if self._moment_notify:
                self._moment_notify('countdown_zero', {'label': self.timer_label})

    def draw(self, screen, position):
        try:
            if isinstance(position, dict):
                x, y = position["x"], position["y"]
                width = position.get("width", 300)
                height = position.get("height", 200)
            else:
                x, y = position
                width, height = 300, 200

            self._init_fonts()

            from module_base import ModuleDrawHelper
            import theme
            draw_y = ModuleDrawHelper.draw_module_title(
                screen, "Countdowns", x, y, width, accent_color=theme.module_accent('countdown')
            )

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

            # Event countdowns. The soonest event is the hero stat -- a big
            # number reads at a glance; "Christmas: 98 days" as a sentence
            # doesn't. The rest stay compact but still number-led (23d
            # Dentist, not Dentist: 23 days), so the eye lands on the count
            # first everywhere in the module, not just the top one.
            countdowns = self._get_countdowns()
            max_display = 5 if timer_remaining is None else 4

            if countdowns and draw_y <= y + height - 90:
                hero = countdowns[0]
                days = hero["days"]
                if days == 0:
                    num_text, unit_text, color = "TODAY", "", (152, 251, 152)
                elif days == 1:
                    num_text, unit_text, color = "1", "DAY", (173, 216, 230)
                else:
                    num_text, unit_text, color = str(days), "DAYS", COLOR_TEXT_PRIMARY

                accent = theme.module_accent('countdown')
                name_label = ModuleDrawHelper.render_tracked(
                    self.small_font, hero["name"].upper(), accent
                )
                name_label.set_alpha(TRANSPARENCY)
                screen.blit(name_label, (x, draw_y))

                num_y = draw_y + name_label.get_height() + 4
                num_surf = self.hero_font.render(num_text, True, color)
                num_surf.set_alpha(TRANSPARENCY)
                draw_hero_glow(screen, num_surf, x, num_y, accent, intensity=0.5)
                screen.blit(num_surf, (x, num_y))
                if unit_text:
                    unit_surf = self.hero_unit_font.render(unit_text, True, COLOR_TEXT_DIM)
                    unit_surf.set_alpha(TRANSPARENCY)
                    screen.blit(unit_surf, (x + num_surf.get_width() + 8,
                                            num_y + num_surf.get_height() - unit_surf.get_height() - 6))
                draw_y = num_y + num_surf.get_height() + 12
                countdowns = countdowns[1:]
                max_display -= 1

            for event in countdowns[:max_display]:
                if draw_y > y + height - 22:
                    break
                days = event["days"]
                name = event["name"]

                if days == 0:
                    count_text, color = "Today", (152, 251, 152)
                elif days == 1:
                    count_text, color = "Tmrw", (173, 216, 230)
                elif days <= 30:
                    count_text, color = f"{days}d", COLOR_FONT_BODY
                else:
                    count_text, color = f"{days}d", COLOR_FONT_SMALL

                count_surf = self.body_font.render(f"{count_text:>4}", True, color)
                count_surf.set_alpha(TRANSPARENCY)
                screen.blit(count_surf, (x, draw_y))

                name_surf = self.body_font.render(name, True, COLOR_TEXT_SECONDARY)
                name_surf.set_alpha(TRANSPARENCY)
                screen.blit(name_surf, (x + count_surf.get_width() + 10, draw_y))

                draw_y += 24

            if not countdowns and timer_remaining is None:
                empty = self.body_font.render("No events configured", True, COLOR_FONT_SMALL)
                empty.set_alpha(TRANSPARENCY)
                screen.blit(empty, (x, draw_y))

        except Exception as e:
            logger.error(f"Error drawing countdown module: {e}")

    def cleanup(self):
        pass
