"""News Headlines module for AI-Mirror.

Displays scrolling news headlines from RSS feeds.
Uses feedparser (no API key needed). Falls back to built-in headlines.
"""

import pygame
import logging
import requests
import time as time_module
from datetime import datetime, timedelta
from config import (
    CONFIG, FONT_NAME, COLOR_FONT_DEFAULT,
    COLOR_FONT_BODY, COLOR_FONT_SMALL, TRANSPARENCY, COLOR_TEXT_DIM,
    COLOR_ACCENT_RED, COLOR_ACCENT_AMBER, COLOR_TEXT_SECONDARY,
)
from background_fetcher import BackgroundFetcher
from effects_kit import draw_flare
from module_base import FLARE_DURATION_S, InstrumentPanel

logger = logging.getLogger("News")

FEED_TIMEOUT = 10  # seconds; feedparser alone has no timeout at all

# Default RSS feeds (no API key needed)
DEFAULT_FEEDS = [
    {"name": "BBC", "url": "http://feeds.bbci.co.uk/news/rss.xml"},
    {"name": "Guardian", "url": "https://www.theguardian.com/uk/rss"},
]


class NewsModule(InstrumentPanel):
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
        self._moment_notify = None
        self._headline_changed_at = None
        self.current_index = 0
        self.last_rotation = time_module.time()
        self.last_fetch = datetime.min
        self.fetch_interval = timedelta(minutes=15)
        self.fade_alpha = 255
        self.transitioning = False

        self.title_font = None
        self.headline_font = None
        self.source_font = None
        self._fetcher = BackgroundFetcher("news")

        # Show last-good headlines immediately after a restart
        from data_cache import data_cache
        cached, age = data_cache.load("news", max_age_sec=86400)
        if cached:
            self.headlines = cached[:self.max_headlines]
            self._known_titles = {h.get("title") for h in self.headlines}
            logger.info(f"Restored {len(self.headlines)} cached headlines "
                        f"({int(age / 60)} min old)")

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

    def _fetch_headlines_blocking(self):
        """Download and parse all RSS feeds. Runs on a background thread.

        Feeds are downloaded with requests (which enforces a timeout) and
        the bytes handed to feedparser, because feedparser's own URL
        fetching can hang forever on a stalled host.
        """
        import feedparser

        new_headlines = []
        for feed_config in self.feeds:
            try:
                resp = requests.get(
                    feed_config["url"], timeout=FEED_TIMEOUT,
                    headers={"User-Agent": "AI-Mirror/1.0"},
                )
                resp.raise_for_status()
                feed = feedparser.parse(resp.content)
                for entry in feed.entries[:5]:
                    new_headlines.append({
                        "title": entry.get("title", "No title"),
                        "source": feed_config["name"],
                        "link": entry.get("link", ""),
                        "published": entry.get("published", ""),
                    })
            except Exception as e:
                logger.warning(f"Failed to fetch feed {feed_config['name']}: {e}")
        return new_headlines

    def _apply_headlines(self, new_headlines):
        if new_headlines:
            # Push notification for truly new headlines
            if self._notify and self._known_titles:
                for h in new_headlines[:2]:
                    if h['title'] not in self._known_titles:
                        self._notify(h['title'], duration_ms=6000)
                        self._headline_changed_at = time_module.time()
                        if self._moment_notify:
                            self._moment_notify('breaking_news', {'headline': h['title']})
                        break  # One notification per fetch cycle

            self._known_titles = {h['title'] for h in new_headlines}
            self.headlines = new_headlines[:self.max_headlines]
            from data_cache import data_cache
            data_cache.save("news", self.headlines)
            logger.info(f"Fetched {len(self.headlines)} headlines from {len(self.feeds)} feeds")
        else:
            logger.warning("No headlines fetched from any feed")

    def set_notification_callback(self, callback):
        """Register a callback for center-screen notifications."""
        self._notify = callback

    def set_moment_callback(self, callback):
        """Register a callback for Director moment triggers (event_director.py)."""
        self._moment_notify = callback

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
        result = self._fetcher.take_result()
        if result is not None:
            ok, value = result
            if ok:
                self._apply_headlines(value)
            elif isinstance(value, ImportError):
                logger.warning("feedparser not installed, using fallback headline")
                self.headlines = [{
                    "title": "feedparser not installed -- run: pip install feedparser",
                    "source": "System",
                }]
            else:
                logger.warning(f"Headline fetch failed: {value}")
            self.last_fetch = datetime.now()

        now = datetime.now()
        if now - self.last_fetch >= self.fetch_interval:
            self._fetcher.submit(self._fetch_headlines_blocking)

        # Rotate headlines
        if self.headlines and (time_module.time() - self.last_rotation) >= self.rotation_interval:
            self.current_index = (self.current_index + 1) % len(self.headlines)
            self.last_rotation = time_module.time()

    def _wrap(self, font_key, text, max_w):
        font = getattr(self, font_key)
        words, lines, line = text.split(), [], ""
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

    def draw(self, screen, position):
        """COMMS: inbound headline feed."""
        self.draw_instrument(screen, position, default=(300, 200))

    def _render_panel(self, surf, width, height, position=None):
        from effects_kit import draw_chamfer_frame
        import theme
        accent = theme.module_accent('news')
        pad = 6
        ix, iw = pad, width - pad * 2

        count = len(self.headlines or [])
        cur = self._panel_header(
            surf, ix, 0, iw, "Comms", accent, align='right',
            subtitle="INBOUND FEED",
            right_text=f"{count} ITEMS" if count else "NO SIGNAL",
            right_color=COLOR_TEXT_DIM if count else COLOR_ACCENT_AMBER)

        if not self.headlines:
            msg = self._text('f_small', "ACQUIRING FEED...", COLOR_TEXT_SECONDARY, spacing=1)
            surf.blit(msg, (ix + iw - msg.get_width(), cur + 8))
            return

        current = self.headlines[self.current_index % count]

        # Active transmission card
        body_lines = self._wrap('f_small', current.get('title', ''), iw - 20)[:4]
        card_h = 26 + len(body_lines) * 17 + 8
        card_h = min(card_h, max(50, height - cur - 60))
        draw_chamfer_frame(surf, ix, cur, iw, card_h, accent, alpha=55, cut=8)

        # Source chip plus a signal-strength tick group
        src = (current.get('source') or 'FEED').upper()[:14]
        chip = self._text('f_nano', src, accent, spacing=1)
        chip_w = chip.get_width() + 12
        pygame.draw.rect(surf, (*accent, 30), (ix + 8, cur + 6, chip_w, 13))
        pygame.draw.rect(surf, (*accent, 140), (ix + 8, cur + 6, chip_w, 13), 1)
        surf.blit(chip, (ix + 14, cur + 7))

        for i in range(4):
            bx = ix + iw - 10 - (3 - i) * 5
            bh = 3 + i * 2
            pygame.draw.rect(surf, (*accent, 220 if i < 3 else 70),
                             (bx, cur + 18 - bh, 3, bh))

        ty = cur + 24
        for line in body_lines:
            ls = self._text('f_small', line, COLOR_FONT_BODY)
            surf.blit(ls, (ix + 10, ty))
            ty += 17
        cur += card_h + 8

        # Rotation position: one cell per item in the feed
        # Capped so a two-item feed does not render as two huge slabs
        cell_w = max(3, min(26, int((iw - (count - 1) * 2) / max(1, count))))
        for i in range(count):
            cx = ix + i * (cell_w + 2)
            if cx + cell_w > ix + iw:
                break
            lit = (i == self.current_index % count)
            pygame.draw.rect(surf, (*accent, 235 if lit else 45),
                             (cx, cur, cell_w, 3 if lit else 2))
        cur += 10

        # Queued headlines
        if cur + 20 < height:
            ql = self._text('f_nano', "QUEUE", accent, spacing=2)
            surf.blit(ql, (ix + iw - ql.get_width(), cur))
            cur += ql.get_height() + 4
            for offset in range(1, min(4, count)):
                if cur + 14 > height:
                    break
                item = self.headlines[(self.current_index + offset) % count]
                title = item.get('title', '')
                trimmed = self._wrap('f_nano', title, iw - 16)[:1]
                if not trimmed:
                    continue
                text = trimmed[0]
                if len(text) < len(title):
                    text = text.rstrip() + ".."
                ts = self._text('f_nano', text, COLOR_TEXT_DIM, spacing=1)
                pygame.draw.circle(surf, (*accent, 150),
                                   (int(ix + iw - 4), int(cur + 5)), 2)
                surf.blit(ts, (ix + iw - 12 - ts.get_width(), cur))
                cur += 14

    def cleanup(self):
        pass
