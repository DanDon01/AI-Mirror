"""Clock module for AI-Mirror top bar.

Premium banner: large light-weight time (platinum), seconds as a quiet
suffix, date and weather status right-aligned in small caps, and a
full-width hairline rule separating the banner from the mirror space.

The legacy scrolling-time mode is available with scrolling=True.
"""

import pygame
import logging
import calendar
from datetime import datetime
import pytz
from config import (
    FONT_NAME, FONT_SIZE_CLOCK, FONT_SIZE_SMALL, FONT_SIZE_LABEL,
    COLOR_CLOCK_FACE, COLOR_TEXT_SECONDARY, COLOR_TEXT_DIM,
    COLOR_ACCENT_PRIMARY, COLOR_ACCENT_BLUE, COLOR_ACCENT_AMBER,
    TRANSPARENCY, ANIMATION, LABEL_TRACKING, IS_NIGHT,
    load_font,
)
from effects_kit import draw_hero_glow

logger = logging.getLogger("Clock")


class ClockModule:
    def __init__(self, font_file=None, time_font_size=None, date_font_size=None,
                 color=None, time_format='%H:%M:%S', date_format='%a, %b %d, %Y',
                 timezone='local', scrolling=False, **kwargs):
        size = time_font_size or FONT_SIZE_CLOCK
        self.time_font = load_font('regular', size)
        self.seconds_font = load_font('regular', int(size * 0.45))
        self.date_font = load_font('regular', FONT_SIZE_SMALL)
        self.status_font = load_font('regular', FONT_SIZE_LABEL)
        self.color = COLOR_CLOCK_FACE
        self.time_format = time_format
        self.date_format = date_format
        self.tz = pytz.timezone(timezone) if timezone != 'local' else None
        self.scrolling = scrolling

        self.scroll_position = 0
        self.scroll_speed = ANIMATION.get('scroll_speed_clock', 0.5)
        self.screen_width = 0
        self.total_width = 0

        # Status indicators set by main loop
        self._status_text = ""
        self._weather_timeline = []
        self._astronomy_text = ""

        # Cache: HH:MM changes once a minute; seconds re-render each second
        self._cached_hhmm = None
        self._cached_hhmm_surf = None
        self._cached_date = None
        self._cached_date_surf = None
        self._hairline = None

    def set_status_indicators(self, text):
        """Set status text displayed in the top bar (e.g. weather summary)."""
        self._status_text = text

    def set_weather_timeline(self, timeline, astronomy_text=""):
        """Receive the compact leave-home outlook from WeatherModule."""
        self._weather_timeline = list(timeline or [])
        self._astronomy_text = astronomy_text or ""

    def update(self):
        if self.scrolling:
            self.scroll_position -= self.scroll_speed
            if self.total_width > 0 and self.scroll_position < -self.total_width:
                self.scroll_position = self.screen_width

    def _render_tracked(self, font, text, color, tracking=LABEL_TRACKING):
        glyphs = [font.render(ch, True, color) for ch in text]
        if not glyphs:
            return pygame.Surface((1, 1), pygame.SRCALPHA)
        width = sum(g.get_width() for g in glyphs) + tracking * (len(glyphs) - 1)
        height = max(g.get_height() for g in glyphs)
        surf = pygame.Surface((max(width, 1), height), pygame.SRCALPHA)
        gx = 0
        for g in glyphs:
            surf.blit(g, (gx, 0))
            gx += g.get_width() + tracking
        return surf

    def draw(self, screen, position):
        try:
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', screen.get_width())
                height = position.get('height', 95)
            else:
                x, y = position
                width = screen.get_width()
                height = 95

            self.screen_width = width
            if self.scrolling:
                self._draw_scrolling(screen, x, y, width, height)
            else:
                self._draw_static(screen, x, y, width, height)

            # Full-width hairline rule under the banner
            if self._hairline is None or self._hairline.get_width() != width:
                self._hairline = pygame.Surface((width, 1), pygame.SRCALPHA)
                self._hairline.fill((*COLOR_ACCENT_PRIMARY, 70))
            screen.blit(self._hairline, (x, y + height - 1))

        except Exception as e:
            logger.error(f"Error drawing clock: {e}")

    def _draw_static(self, screen, x, y, width, height):
        """Premium static banner: HH:MM large, seconds quiet, date right."""
        now = datetime.now(self.tz) if self.tz else datetime.now()
        hhmm = now.strftime('%H:%M')
        secs = now.strftime('%S')
        pad = 22

        # HH:MM (cached per minute)
        if hhmm != self._cached_hhmm:
            self._cached_hhmm = hhmm
            self._cached_hhmm_surf = self.time_font.render(hhmm, True, self.color)
            self._cached_hhmm_surf.set_alpha(TRANSPARENCY)
        time_surf = self._cached_hhmm_surf
        time_y = y + (height - time_surf.get_height()) // 2
        draw_hero_glow(screen, time_surf, x + pad, time_y, COLOR_ACCENT_PRIMARY,
                       intensity=1.0 if IS_NIGHT else 0.3)
        screen.blit(time_surf, (x + pad, time_y))

        # Seconds: smaller, dimmer, baseline-aligned to the big digits
        sec_surf = self.seconds_font.render(secs, True, COLOR_TEXT_DIM)
        sec_surf.set_alpha(TRANSPARENCY)
        sec_x = x + pad + time_surf.get_width() + 12
        sec_y = time_y + time_surf.get_height() - sec_surf.get_height() - 12
        screen.blit(sec_surf, (sec_x, sec_y))

        # Date: tracked small caps, right-aligned (cached per day)
        date_text = self.get_current_date().upper()
        if date_text != self._cached_date:
            self._cached_date = date_text
            self._cached_date_surf = self._render_tracked(
                self.date_font, date_text, COLOR_TEXT_SECONDARY, tracking=2
            )
            self._cached_date_surf.set_alpha(TRANSPARENCY)
        date_surf = self._cached_date_surf
        status_surf = None
        if self._status_text:
            status_surf = self.status_font.render(self._status_text, True, COLOR_TEXT_DIM)
            status_surf.set_alpha(TRANSPARENCY)
        astronomy_surf = None
        if self._astronomy_text:
            astronomy_surf = self.status_font.render(self._astronomy_text, True, COLOR_ACCENT_AMBER)
            astronomy_surf.set_alpha(TRANSPARENCY)
        right_w = max(date_surf.get_width(), *(s.get_width() for s in (status_surf, astronomy_surf) if s is not None))
        right_x = x + width - right_w - pad

        # The centre of the bar earns its space with a practical five-point
        # forecast, rather than being decorative empty black.
        timeline_x = sec_x + sec_surf.get_width() + 34
        timeline_right = right_x - 26
        if self._weather_timeline and timeline_right - timeline_x >= 220:
            self._draw_weather_timeline(screen, timeline_x, timeline_right, y, height)

        if status_surf or astronomy_surf:
            extra_h = sum(s.get_height() + 4 for s in (astronomy_surf, status_surf) if s is not None)
            block_h = date_surf.get_height() + 5 + extra_h
            block_y = y + (height - block_h) // 2
            screen.blit(date_surf, (x + width - date_surf.get_width() - pad, block_y))
            line_y = block_y + date_surf.get_height() + 5
            for surf in (astronomy_surf, status_surf):
                if surf is not None:
                    screen.blit(surf, (x + width - surf.get_width() - pad, line_y))
                    line_y += surf.get_height() + 4
        else:
            screen.blit(
                date_surf, (x + width - date_surf.get_width() - pad, y + (height - date_surf.get_height()) // 2)
            )

    def _draw_weather_timeline(self, screen, left, right, y, height):
        """Five-point forecast strip: time + temp, rain% only when it
        matters. The old hand-drawn sun/cloud marks read as clip-art at
        this size, so this stays typographic until real iconography
        (Moments-era) replaces it."""
        entries = self._weather_timeline[:5]
        if not entries:
            return
        slot_w = max(1, (right - left) // len(entries))
        base_y = y + height - 15
        pygame.draw.line(screen, (*COLOR_TEXT_DIM, 90), (left, base_y), (right, base_y), 1)
        for index, entry in enumerate(entries):
            cx = left + slot_w * index + slot_w // 2
            time_surf = self.status_font.render(f"{entry['time']}h", True, COLOR_TEXT_DIM)
            time_surf.set_alpha(TRANSPARENCY)
            screen.blit(time_surf, (cx - time_surf.get_width() // 2, y + 8))
            rain = entry.get('rain', 0)
            temp_text = f"{entry['temp']}°"
            temp_color = COLOR_ACCENT_BLUE if rain >= 25 else COLOR_TEXT_SECONDARY
            temp_surf = self.status_font.render(temp_text, True, temp_color)
            temp_surf.set_alpha(TRANSPARENCY)
            screen.blit(temp_surf, (cx - temp_surf.get_width() // 2, base_y - temp_surf.get_height() - 2))
            if rain >= 25:
                rain_surf = self.status_font.render(f"{rain}%", True, COLOR_ACCENT_BLUE)
                rain_surf.set_alpha(TRANSPARENCY)
                screen.blit(rain_surf, (cx - rain_surf.get_width() // 2,
                                        base_y - temp_surf.get_height() - rain_surf.get_height() - 4))

    def _draw_scrolling(self, screen, x, y, width, height):
        """Legacy scrolling time bar."""
        current_time = self.get_current_time()
        current_date = self.get_current_date()

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

        scroll_limit = date_x - 20
        time_surf = self.time_font.render(current_time, True, self.color)
        time_surf.set_alpha(TRANSPARENCY)
        self.total_width = time_surf.get_width()

        self.scroll_position -= self.scroll_speed
        if self.scroll_position < -time_surf.get_width():
            self.scroll_position = scroll_limit

        time_y = y + (height - time_surf.get_height() - 10) // 2

        old_clip = screen.get_clip()
        screen.set_clip(pygame.Rect(0, y, scroll_limit, height))
        screen.blit(time_surf, (self.scroll_position, time_y))
        if self.scroll_position < 0:
            second_x = self.scroll_position + time_surf.get_width() + scroll_limit
            if second_x < scroll_limit:
                screen.blit(time_surf, (second_x, time_y))
        screen.set_clip(old_clip)

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
