"""News Headlines module for AI-Mirror.

Displays scrolling news headlines from RSS feeds.
Uses feedparser (no API key needed). Falls back to built-in headlines.
"""

import pygame
import logging
import time as time_module
from datetime import datetime, timedelta
from config import (
    CONFIG, FONT_NAME, COLOR_FONT_DEFAULT,
    COLOR_FONT_BODY, COLOR_FONT_SMALL, TRANSPARENCY, COLOR_TEXT_DIM,
)

logger = logging.getLogger("News")

# Default RSS feeds (no API key needed)
DEFAULT_FEEDS = [
    {"name": "BBC", "url": "http://feeds.bbci.co.uk/news/rss.xml"},
    {"name": "Guardian", "url": "https://www.theguardian.com/uk/rss"},
]


class NewsModule:
    """Displays scrolling news headlines from RSS feeds."""

    def __init__(self, feeds=None, rotation_interval=15, max_headlines=8, **kwargs):
        """
        Args:
            feeds: list of dicts with 'name' and 'url' keys for RSS feeds.
            rotation_interval: seconds between headline rotation.
            max_headlines: maximum number of headlines to store.
        """
        self.feeds = feeds or DEFAULT_FEEDS
        self.rotation_interval = rotation_interval
        self.max_headlines = max_headlines
        self.headlines = []
        self._known_titles = set()
        self._notify = None
        self.current_index = 0
        self.last_rotation = time_module.time()
        self.last_fetch = datetime.min
        self.fetch_interval = timedelta(minutes=15)
        self.fade_alpha = 255
        self.transitioning = False

        self.title_font = None
        self.headline_font = None
        self.source_font = None

    def _init_fonts(self):
        if self.title_font is None:
            styling = CONFIG.get("module_styling", {})
            fonts = styling.get("fonts", {})
            title_size = fonts.get("title", {}).get("size", 18)
            body_size = fonts.get("body", {}).get("size", 14)
            small_size = fonts.get("small", {}).get("size", 12)
            self.title_font = pygame.font.SysFont(FONT_NAME, title_size)
            self.headline_font = pygame.font.SysFont(FONT_NAME, body_size)
            self.source_font = pygame.font.SysFont(FONT_NAME, small_size)

    def _fetch_headlines(self):
        """Fetch headlines from all configured RSS feeds."""
        try:
            import feedparser
        except ImportError:
            logger.warning("feedparser not installed, using fallback headlines")
            self.headlines = [
                {"title": "feedparser not installed -- run: pip install feedparser", "source": "System"},
            ]
            return

        new_headlines = []
        for feed_config in self.feeds:
            try:
                feed = feedparser.parse(feed_config["url"])
                for entry in feed.entries[:5]:
                    new_headlines.append({
                        "title": entry.get("title", "No title"),
                        "source": feed_config["name"],
                        "link": entry.get("link", ""),
                        "published": entry.get("published", ""),
                    })
            except Exception as e:
                logger.warning(f"Failed to fetch feed {feed_config['name']}: {e}")

        if new_headlines:
            # Push notification for truly new headlines
            if self._notify and self._known_titles:
                for h in new_headlines[:2]:
                    if h['title'] not in self._known_titles:
                        self._notify(h['title'], duration_ms=6000)
                        break  # One notification per fetch cycle

            self._known_titles = {h['title'] for h in new_headlines}
            self.headlines = new_headlines[:self.max_headlines]
            logger.info(f"Fetched {len(self.headlines)} headlines from {len(self.feeds)} feeds")
        else:
            logger.warning("No headlines fetched from any feed")

    def set_notification_callback(self, callback):
        """Register a callback for center-screen notifications."""
        self._notify = callback

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
        now = datetime.now()
        if now - self.last_fetch >= self.fetch_interval:
            self._fetch_headlines()
            self.last_fetch = now

        # Rotate headlines
        if self.headlines and (time_module.time() - self.last_rotation) >= self.rotation_interval:
            self.current_index = (self.current_index + 1) % len(self.headlines)
            self.last_rotation = time_module.time()

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

            align = position.get('align', 'left') if isinstance(position, dict) else 'left'

            from module_base import ModuleDrawHelper
            draw_y = ModuleDrawHelper.draw_module_title(
                screen, "News", x, y, width, align=align
            )

            if not self.headlines:
                empty = self.headline_font.render("Loading headlines...", True, COLOR_FONT_SMALL)
                ModuleDrawHelper.blit_aligned(screen, empty, x, draw_y, width, align)
                return

            # Draw current headline (large, wrapped)
            text_width = width - 20
            current = self.headlines[self.current_index]
            lines = self._word_wrap(current["title"], self.headline_font, text_width)

            for line in lines[:3]:  # Max 3 lines per headline
                line_surf = self.headline_font.render(line, True, COLOR_FONT_BODY)
                line_surf.set_alpha(TRANSPARENCY)
                ModuleDrawHelper.blit_aligned(screen, line_surf, x, draw_y, width, align)
                draw_y += 20

            # Source and position indicator
            draw_y += 5
            source_text = current["source"]
            pos_text = f"{self.current_index + 1}/{len(self.headlines)}"
            source_surf = self.source_font.render(f"{source_text}  |  {pos_text}", True, COLOR_FONT_SMALL)
            source_surf.set_alpha(TRANSPARENCY)
            ModuleDrawHelper.blit_aligned(screen, source_surf, x, draw_y, width, align)

            # Thin progress bar showing position in headlines
            draw_y += 15
            bar_width = min(width, 120)
            segment_w = bar_width // max(len(self.headlines), 1)
            bar_total_w = len(self.headlines) * (segment_w + 2) - 2
            bar_x = x + width - bar_total_w if align == 'right' else x
            for i in range(len(self.headlines)):
                color = (200, 200, 200) if i == self.current_index else (40, 40, 40)
                sx = bar_x + i * (segment_w + 2)
                pygame.draw.rect(screen, color, (sx, draw_y, segment_w, 2))

        except Exception as e:
            logger.error(f"Error drawing news module: {e}")

    def cleanup(self):
        pass
