"""Clock module for AI-Mirror top bar.

Displays time with a cool monospace digital look, static date right-aligned.
Renders as the top bar of the mirror interface.
"""

import pygame
import logging
import calendar
from datetime import datetime
import pytz
from config import (
    FONT_NAME, FONT_NAME_CLOCK, FONT_SIZE_CLOCK, FONT_SIZE_BODY, FONT_SIZE_SMALL,
    COLOR_CLOCK_FACE, COLOR_TEXT_SECONDARY, COLOR_TEXT_DIM,
    TRANSPARENCY, ANIMATION,
)

logger = logging.getLogger("Clock")


class ClockModule:
    def __init__(self, font_file=None, time_font_size=None, date_font_size=None,
                 color=None, time_format='%H:%M:%S', date_format='%a, %b %d, %Y',
                 timezone='local', **kwargs):
        size = time_font_size or FONT_SIZE_CLOCK
        date_size = date_font_size or FONT_SIZE_BODY
        self.time_font = pygame.font.SysFont(FONT_NAME_CLOCK, size)
        self.date_font = pygame.font.SysFont(FONT_NAME, date_size)
        self.status_font = pygame.font.SysFont(FONT_NAME, FONT_SIZE_SMALL)
        self.color = COLOR_CLOCK_FACE
        self.time_format = time_format
        self.date_format = date_format
        self.tz = pytz.timezone(timezone) if timezone != 'local' else None

        self.scroll_position = 0
        self.scroll_speed = ANIMATION.get('scroll_speed_clock', 0.5)
        self.screen_width = 0
        self.total_width = 0

        # Status indicators set by main loop
        self._status_text = ""

    def set_status_indicators(self, text):
        """Set status text displayed in the top bar (e.g. weather summary)."""
        self._status_text = text

    def update(self):
        self.scroll_position -= self.scroll_speed
        if self.total_width > 0 and self.scroll_position < -self.total_width:
            self.scroll_position = self.screen_width

    def draw(self, screen, position):
        """Draw top bar: scrolling time, static date."""
        try:
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', screen.get_width())
                height = position.get('height', 80)
            else:
                x, y = position
                width = screen.get_width()
                height = 80

            self.screen_width = width
            current_time = self.get_current_time()
            current_date = self.get_current_date()

            # --- Static elements first (date + weather status, top-right) ---
            date_surf = self.date_font.render(current_date, True, COLOR_TEXT_SECONDARY)
            date_surf.set_alpha(TRANSPARENCY)
            date_x = width - date_surf.get_width() - 20
            date_y = y + height - date_surf.get_height() - 12
            screen.blit(date_surf, (date_x, date_y))

            if self._status_text:
                status_surf = self.status_font.render(
                    self._status_text, True, COLOR_TEXT_DIM
                )
                status_surf.set_alpha(TRANSPARENCY)
                screen.blit(status_surf, (date_x, y + 8))

            # --- Scrolling time, clipped to avoid the static right corner ---
            # The scroll region ends before the date/status block
            scroll_limit = date_x - 20
            time_surf = self.time_font.render(current_time, True, self.color)
            time_surf.set_alpha(TRANSPARENCY)
            self.total_width = time_surf.get_width()

            self.scroll_position -= self.scroll_speed
            if self.scroll_position < -time_surf.get_width():
                self.scroll_position = scroll_limit

            time_y = y + (height - time_surf.get_height() - 10) // 2

            # Clip so the time never overlaps the date area
            old_clip = screen.get_clip()
            screen.set_clip(pygame.Rect(0, y, scroll_limit, height))
            screen.blit(time_surf, (self.scroll_position, time_y))

            # Seamless wrap
            if self.scroll_position < 0:
                second_x = self.scroll_position + time_surf.get_width() + scroll_limit
                if second_x < scroll_limit:
                    screen.blit(time_surf, (second_x, time_y))

            screen.set_clip(old_clip)

        except Exception as e:
            logger.error(f"Error drawing clock: {e}")

    def format_date(self, date):
        day_abbr = calendar.day_abbr[date.weekday()][:4]
        month_abbr = date.strftime("%b")
        if month_abbr == "Sep":
            month_abbr = "Sept"
        return f"{day_abbr}, {month_abbr} {date.strftime('%d')}, {date.strftime('%Y')}"

    def get_current_time(self):
        now = datetime.now(self.tz) if self.tz else datetime.now()
        return now.strftime(self.time_format)

    def get_current_date(self):
        now = datetime.now(self.tz) if self.tz else datetime.now()
        return self.format_date(now)

    def cleanup(self):
        pass
