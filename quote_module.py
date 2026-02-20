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
)

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


class QuoteModule:
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
        self._surface_cache = SurfaceCache()

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
            import requests
            resp = requests.get("https://zenquotes.io/api/today", timeout=10)
            if resp.status_code == 200:
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

    def update(self):
        today = date.today()
        if self.last_fetch_date == today:
            return

        # Try API first, then local file, then builtin
        quote, author = self._fetch_from_api()
        if not quote:
            quote, author = self._fetch_from_file()
        if not quote:
            quote, author = self._fetch_builtin()

        self.current_quote = quote
        self.current_author = author
        self.last_fetch_date = today
        self._wrapped_lines = []  # Reset wrap cache
        logger.info(f"Quote of the day: '{quote[:50]}...' - {author}")

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
            draw_y = ModuleDrawHelper.draw_module_title(
                screen, "Quote", x, y, width
            )

            if not self.current_quote:
                empty = self.quote_font.render("Loading...", True, COLOR_FONT_SMALL)
                screen.blit(empty, (x, draw_y))
                return

            # Word-wrap the quote (cached until quote changes)
            text_width = width - 20
            if not self._wrapped_lines:
                self._wrapped_lines = self._word_wrap(self.current_quote, self.quote_font, text_width)

            quote_hash = self.current_quote[:30] + (self.current_author or "")

            # Opening quote mark
            mark = self._surface_cache.get_or_render(
                "quote_mark",
                lambda: self.quote_font.render('"', True, COLOR_FONT_SMALL),
                quote_hash,
            )
            screen.blit(mark, (x, draw_y - 2))

            for i, line in enumerate(self._wrapped_lines):
                def _render_line(l=line):
                    s = self.quote_font.render(l, True, COLOR_FONT_BODY)
                    s.set_alpha(TRANSPARENCY)
                    return s

                line_surf = self._surface_cache.get_or_render(
                    f"quote_line_{i}", _render_line, quote_hash
                )
                screen.blit(line_surf, (x + 10, draw_y))
                draw_y += 22

            draw_y += 5
            author_text = f"-- {self.current_author}"

            def _render_author():
                s = self.author_font.render(author_text, True, COLOR_FONT_SMALL)
                s.set_alpha(TRANSPARENCY)
                return s

            author_surf = self._surface_cache.get_or_render(
                "quote_author", _render_author, quote_hash
            )
            screen.blit(author_surf, (x + 20, draw_y))

        except Exception as e:
            logger.error(f"Error drawing quote module: {e}")

    def cleanup(self):
        pass
