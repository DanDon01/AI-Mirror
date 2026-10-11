"""Quote of the Day module for AI-Mirror.

Displays a daily quote with elegant typography.
Fetches from ZenQuotes API (free, no key needed) with local JSON fallback.
"""

import pygame
import logging
import os
import json
import random
from datetime import datetime, date
from config import (
    CONFIG, FONT_NAME, COLOR_FONT_DEFAULT,
    COLOR_FONT_BODY, COLOR_FONT_SMALL, TRANSPARENCY,
    COLOR_TEXT_DIM,)
from module_base import InstrumentPanel

logger = logging.getLogger("Quote")

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Fallback quotes used when API and local file are both unavailable
_BUILTIN_QUOTES = [
    {"q": "The only way to do great work is to love what you do.", "a": "Steve Jobs"},
    {"q": "Be yourself; everyone else is already taken.", "a": "Oscar Wilde"},
    {"q": "In the middle of difficulty lies opportunity.", "a": "Albert Einstein"},
    {"q": "Stay hungry, stay foolish.", "a": "Steve Jobs"},
    {"q": "Not all those who wander are lost.", "a": "J.R.R. Tolkien"},
    {"q": "Do what you can, with what you have, where you are.", "a": "Theodore Roosevelt"},
    {"q": "It does not do to dwell on dreams and forget to live.", "a": "J.K. Rowling"},
    {"q": "The best time to plant a tree was 20 years ago. The second best time is now.", "a": "Chinese Proverb"},
]


class QuoteModule(InstrumentPanel):
    """Displays a daily inspirational quote."""

    def __init__(self, quotes_file=None, **kwargs):
        """
        Args:
            quotes_file: optional path to a local JSON file of quotes.
                         Format: [{"q": "quote text", "a": "author"}, ...]
        """
        self.quotes_file = quotes_file or os.path.join(_PROJECT_DIR, "data", "quotes.json")
        self.current_quote = None
        self.current_author = None
        self.last_fetch_date = None
        self.title_font = None
        self.quote_font = None
        self.author_font = None
        self._wrapped_lines = []
        from module_base import SurfaceCache
        from background_fetcher import BackgroundFetcher
        self._surface_cache = SurfaceCache()
        self._fetcher = BackgroundFetcher("quote")

    def _init_fonts(self):
        if self.title_font is None:
            styling = CONFIG.get("module_styling", {})
            fonts = styling.get("fonts", {})
            title_size = fonts.get("title", {}).get("size", 18)
            body_size = fonts.get("body", {}).get("size", 14)
            small_size = fonts.get("small", {}).get("size", 12)
            self.title_font = pygame.font.SysFont(FONT_NAME, title_size)
            self.quote_font = pygame.font.SysFont(FONT_NAME, body_size)
            self.author_font = pygame.font.SysFont(FONT_NAME, small_size)

    def _fetch_from_api(self):
        """Fetch quote of the day from ZenQuotes API."""
        try:
            from api_tracker import api_tracker
            if not api_tracker.allow("quote", "zenquotes"):
                return None, None
            import requests
            resp = requests.get("https://zenquotes.io/api/today", timeout=10)
            if resp.status_code == 200:
                api_tracker.record("quote", "zenquotes")
                data = resp.json()
                if data and isinstance(data, list) and len(data) > 0:
                    return data[0].get("q", ""), data[0].get("a", "Unknown")
        except Exception as e:
            logger.warning(f"ZenQuotes API failed: {e}")
        return None, None

    def _fetch_from_file(self):
        """Load a random quote from local JSON file."""
        try:
            if os.path.exists(self.quotes_file):
                with open(self.quotes_file, "r", encoding="utf-8") as f:
                    quotes = json.load(f)
                if quotes:
                    # Use day of year as seed for consistent daily quote
                    idx = date.today().timetuple().tm_yday % len(quotes)
                    q = quotes[idx]
                    return q.get("q", ""), q.get("a", "Unknown")
        except Exception as e:
            logger.warning(f"Local quotes file failed: {e}")
        return None, None

    def _fetch_builtin(self):
        """Return a quote from the built-in list."""
        idx = date.today().timetuple().tm_yday % len(_BUILTIN_QUOTES)
        q = _BUILTIN_QUOTES[idx]
        return q["q"], q["a"]

    def _word_wrap(self, text, font, max_width):
        """Wrap text to fit within max_width pixels."""
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            test = f"{current_line} {word}".strip()
            if font.size(test)[0] <= max_width:
                current_line = test
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return lines

    def _fetch_daily_quote(self):
        """API -> local file -> builtin fallback. Runs off the main loop."""
        quote, author = self._fetch_from_api()
        if not quote:
            quote, author = self._fetch_from_file()
        if not quote:
            quote, author = self._fetch_builtin()
        return quote, author

    def update(self):
        result = self._fetcher.take_result()
        if result is not None:
            ok, value = result
            if ok:
                self.current_quote, self.current_author = value
                self._wrapped_lines = []  # Reset wrap cache
                logger.info(
                    f"Quote of the day: '{self.current_quote[:50]}...' - {self.current_author}"
                )
            self.last_fetch_date = date.today()

        if self.last_fetch_date == date.today():
            return
        self._fetcher.submit(self._fetch_daily_quote)

    def draw(self, screen, position):
        """A quote is text by nature; it gets typography, not a chart."""
        self.draw_instrument(screen, position, default=(300, 200))

    def _render_panel(self, surf, width, height, position=None):
        import theme
        accent = theme.module_accent('quote')
        pad = 6
        ix, iw = pad, width - pad * 2

        cur = self._panel_header(surf, ix, 0, iw, "Log", accent, align='right')

        if not self.current_quote:
            msg = self._text('f_nano', "LOADING...", COLOR_TEXT_DIM, spacing=1)
            surf.blit(msg, (ix + iw - msg.get_width(), cur))
            return

        # An oversized opening quote mark anchors the block
        mark = self._text('f_hero', '"', (*accent[:3],))
        mark.set_alpha(70)
        surf.blit(mark, (ix + iw - mark.get_width() - 2, cur - 12))

        cur += 6
        for line in self._panel_wrap(self.current_quote, iw - 14):
            if cur + 17 > height - 14:
                break
            ls = self._text('f_small', line, COLOR_FONT_BODY)
            surf.blit(ls, (ix + iw - ls.get_width(), cur))
            cur += 17

        if self.current_author and cur + 14 < height:
            pygame.draw.line(surf, (*accent, 90),
                             (ix + iw - 28, cur + 5), (ix + iw, cur + 5), 1)
            au = self._text('f_nano', str(self.current_author).upper(),
                            COLOR_TEXT_DIM, spacing=2)
            surf.blit(au, (ix + iw - au.get_width(), cur + 10))

    def _panel_wrap(self, text, max_w):
        font = self.f_small
        words, lines, line = str(text).split(), [], ""
        for word in words:
            trial = f"{line} {word}".strip()
            if font.size(trial)[0] <= max_w or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
        return lines


    def cleanup(self):
        pass
