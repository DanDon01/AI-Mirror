"""Shared drawing utilities for AI-Mirror modules.

Provides consistent font initialization, text rendering, separators,
and surface caching for the mirror UI. All modules use these helpers
for a unified visual style.
"""

import pygame
from config import (
    CONFIG, FONT_NAME, FONT_SIZE_TITLE, FONT_SIZE_BODY, FONT_SIZE_SMALL,
    COLOR_TEXT_DIM, COLOR_TITLE_BLUE, COLOR_SEPARATOR, TRANSPARENCY,
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

    @classmethod
    def _ensure_fonts(cls):
        """Lazy-init shared fonts from config."""
        if cls._fonts_initialized:
            return
        styling = CONFIG.get('module_styling', {})
        fonts = styling.get('fonts', {})
        title_size = fonts.get('title', {}).get('size', FONT_SIZE_TITLE)
        body_size = fonts.get('body', {}).get('size', FONT_SIZE_BODY)
        small_size = fonts.get('small', {}).get('size', FONT_SIZE_SMALL)
        cls._title_font = pygame.font.SysFont(FONT_NAME, title_size)
        cls._body_font = pygame.font.SysFont(FONT_NAME, body_size)
        cls._small_font = pygame.font.SysFont(FONT_NAME, small_size)
        cls._fonts_initialized = True

    @staticmethod
    def draw_module_title(screen, text, x, y, width):
        """Draw a subtle module title label -- dim text, no background.

        Returns the y-offset below the title for content to start.
        """
        ModuleDrawHelper._ensure_fonts()
        title_surf = ModuleDrawHelper._small_font.render(
            text.upper(), True, COLOR_TITLE_BLUE
        )
        title_surf.set_alpha(TRANSPARENCY)
        screen.blit(title_surf, (x, y))
        return y + title_surf.get_height() + 6

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
