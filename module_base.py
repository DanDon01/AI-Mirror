"""Shared drawing utilities for AI-Mirror modules.

Provides consistent typography (bundled Lato light/regular weights),
tracked uppercase module labels with hairline accent rules, text
rendering helpers, and surface caching. All modules use these helpers
for a unified minimal-luxury visual style.
"""

import pygame
from config import (
    CONFIG, FONT_NAME, FONT_SIZE_TITLE, FONT_SIZE_BODY, FONT_SIZE_SMALL,
    FONT_SIZE_LABEL, FONT_SIZE_HERO, LABEL_TRACKING, load_font,
    COLOR_TEXT_DIM, COLOR_ACCENT_PRIMARY, COLOR_SEPARATOR, TRANSPARENCY,
)


class SurfaceCache:
    """Cache rendered text surfaces to avoid per-frame font.render() calls.

    Only re-renders when the source data actually changes.
    """

    def __init__(self):
        self._cache = {}

    def get_or_render(self, key, render_func, data_hash):
        """Return cached surface if data_hash unchanged, else re-render."""
        entry = self._cache.get(key)
        if entry and entry[1] == data_hash:
            return entry[0]
        surface = render_func()
        self._cache[key] = (surface, data_hash)
        return surface

    def invalidate(self, key=None):
        """Clear specific key or entire cache."""
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()


class ModuleDrawHelper:
    """Mixin providing standardized draw methods for mirror modules."""

    _fonts_initialized = False
    _title_font = None
    _body_font = None
    _small_font = None
    _label_font = None

    @classmethod
    def _ensure_fonts(cls):
        """Lazy-init shared fonts: light body, regular small, tracked label."""
        if cls._fonts_initialized:
            return
        styling = CONFIG.get('module_styling', {})
        fonts = styling.get('fonts', {})
        title_size = fonts.get('title', {}).get('size', FONT_SIZE_TITLE)
        body_size = fonts.get('body', {}).get('size', FONT_SIZE_BODY)
        small_size = fonts.get('small', {}).get('size', FONT_SIZE_SMALL)
        cls._title_font = load_font('regular', title_size)
        cls._body_font = load_font('regular', body_size)
        cls._small_font = load_font('regular', small_size)
        cls._label_font = load_font('bold', FONT_SIZE_LABEL)
        cls._fonts_initialized = True

    @staticmethod
    def get_font(weight, size):
        """Bundled Lato in 'light' | 'regular' | 'bold' at any size."""
        return load_font(weight, size)

    @staticmethod
    def render_tracked(font, text, color, tracking=LABEL_TRACKING):
        """Render text with letterspacing (pygame has none natively).

        Used for the uppercase module labels; cache the result, do not
        call per frame for long strings.
        """
        glyphs = [font.render(ch, True, color) for ch in text]
        if not glyphs:
            return pygame.Surface((1, 1), pygame.SRCALPHA)
        width = sum(g.get_width() for g in glyphs) + tracking * (len(glyphs) - 1)
        height = max(g.get_height() for g in glyphs)
        surf = pygame.Surface((max(width, 1), height), pygame.SRCALPHA)
        x = 0
        for g in glyphs:
            surf.blit(g, (x, 0))
            x += g.get_width() + tracking
        return surf

    # Per-class cache of rendered title labels (they rarely change)
    _title_cache = {}

    @staticmethod
    def draw_module_title(screen, text, x, y, width, align='left'):
        """Draw a module label: tracked uppercase with a short hairline
        rule in the champagne accent underneath.

        Returns the y-offset below the label for content to start.
        """
        ModuleDrawHelper._ensure_fonts()

        key = (text, align)
        label = ModuleDrawHelper._title_cache.get(key)
        if label is None:
            label = ModuleDrawHelper.render_tracked(
                ModuleDrawHelper._label_font, text.upper(), COLOR_ACCENT_PRIMARY
            )
            label.set_alpha(235)
            ModuleDrawHelper._title_cache[key] = label

        rule_w = 26
        if align == 'right':
            lx = x + width - label.get_width()
        else:
            lx = x
        screen.blit(label, (lx, y))

        rule_y = y + label.get_height() + 5
        rule = pygame.Surface((rule_w, 1), pygame.SRCALPHA)
        rule.fill((*COLOR_ACCENT_PRIMARY, 170))
        if align == 'right':
            screen.blit(rule, (x + width - rule_w, rule_y))
        else:
            screen.blit(rule, (x, rule_y))

        return rule_y + 10

    @staticmethod
    def blit_aligned(screen, surf, x, y, width, align='left'):
        """Blit a surface with left or right alignment within a column."""
        if align == 'right':
            screen.blit(surf, (x + width - surf.get_width(), y))
        else:
            screen.blit(surf, (x, y))

    @staticmethod
    def draw_separator(screen, x, y, width, alpha=255):
        """Draw a thin horizontal separator line."""
        line_w = int(width * 0.85)
        sep = pygame.Surface((line_w, 1), pygame.SRCALPHA)
        sep.fill((*COLOR_SEPARATOR, min(alpha, 120)))
        screen.blit(sep, (x, y))

    @staticmethod
    def get_fonts():
        """Return (title_font, body_font, small_font) tuple."""
        ModuleDrawHelper._ensure_fonts()
        return (
            ModuleDrawHelper._title_font,
            ModuleDrawHelper._body_font,
            ModuleDrawHelper._small_font,
        )
