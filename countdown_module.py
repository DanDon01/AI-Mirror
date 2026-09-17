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
    COLOR_ACCENT_GREEN,
    COLOR_ACCENT_BLUE,)
from module_base import InstrumentPanel
from effects_kit import draw_hero_glow

logger = logging.getLogger("Countdown")


class CountdownModule(InstrumentPanel):
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
        """COUNTDOWN: time-to-event markers."""
        self.draw_instrument(screen, position, default=(300, 200))

    def _render_panel(self, surf, width, height, position=None):
        from effects_kit import draw_bar_meter
        import theme
        accent = theme.module_accent('countdown')
        pad = 6
        ix, iw = pad, width - pad * 2

        countdowns = self._get_countdowns()
        timer_remaining = self._get_timer_remaining()
        cur = self._panel_header(
            surf, ix, 0, iw, "Countdown", accent,
            right_text=f"{len(countdowns)} MARKED" if countdowns else None)

        # A running voice timer outranks the date markers
        if timer_remaining is not None:
            if timer_remaining <= 0:
                pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 200.0)
                color = (255, int(120 + 100 * pulse), int(120 + 100 * pulse))
                label = "TIME UP"
            else:
                color = COLOR_ACCENT_GREEN
                label = f"{int(timer_remaining // 60):02d}:{int(timer_remaining % 60):02d}"
            name = self._text('f_nano', str(self.timer_label).upper(), accent, spacing=2)
            surf.blit(name, (ix, cur))
            val = self._text('f_big', label, color)
            surf.blit(val, (ix, cur + name.get_height() + 1))
            cur += name.get_height() + val.get_height() + 8

        if not countdowns:
            if timer_remaining is None:
                msg = self._text('f_small', "NO MARKERS SET", COLOR_TEXT_SECONDARY, spacing=1)
                surf.blit(msg, (ix, cur + 4))
            return

        horizon = max(max(c["days"] for c in countdowns), 1)

        hero = countdowns[0]
        days = hero["days"]
        if days == 0:
            num_text, unit_text, color = "TODAY", "", COLOR_ACCENT_GREEN
        elif days == 1:
            num_text, unit_text, color = "1", "DAY", COLOR_ACCENT_BLUE
        else:
            num_text, unit_text, color = str(days), "DAYS", COLOR_TEXT_PRIMARY

        name_label = self._text('f_nano', hero["name"].upper(), accent, spacing=2)
        surf.blit(name_label, (ix, cur))
        num_y = cur + name_label.get_height() + 2
        num_surf = self._text('f_hero', num_text, color)
        draw_hero_glow(surf, num_surf, ix, num_y, accent, intensity=0.5)
        surf.blit(num_surf, (ix, num_y))
        if unit_text:
            unit = self._text('f_nano', unit_text, COLOR_TEXT_DIM, spacing=2)
            surf.blit(unit, (ix + num_surf.get_width() + 7,
                             num_y + num_surf.get_height() - unit.get_height() - 7))
        cur = num_y + num_surf.get_height() + 8

        # Remaining markers as relative-distance bars
        for event in countdowns[1:5]:
            if cur + 20 > height:
                break
            name = self._text('f_nano', event["name"].upper()[:18],
                              COLOR_TEXT_SECONDARY, spacing=1)
            surf.blit(name, (ix, cur))
            dv = self._text('f_nano', f"{event['days']}D", COLOR_FONT_BODY, spacing=1)
            surf.blit(dv, (ix + iw - dv.get_width(), cur))
            draw_bar_meter(surf, ix, cur + name.get_height() + 2, iw, 4,
                           1.0 - (event["days"] / horizon), accent,
                           segments=max(8, int(iw / 12)))
            cur += name.get_height() + 12


    def cleanup(self):
        pass
