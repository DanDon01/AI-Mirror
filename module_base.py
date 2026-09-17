"""Shared drawing utilities for AI-Mirror modules.

Provides consistent typography (bundled Lato light/regular weights),
tracked uppercase module labels with hairline accent rules, text
rendering helpers, and surface caching. All modules use these helpers
for a unified minimal-luxury visual style.
"""

import time

import pygame
from config import (
    CONFIG, FONT_NAME, FONT_SIZE_TITLE, FONT_SIZE_BODY, FONT_SIZE_SMALL,
    FONT_SIZE_LABEL, FONT_SIZE_HERO, LABEL_TRACKING, load_font,
    COLOR_TEXT_DIM, COLOR_ACCENT_PRIMARY, COLOR_SEPARATOR, TRANSPARENCY,
)

FLARE_DURATION_S = 1.4


class SurfaceCache:
    """Cache rendered text surfaces to avoid per-frame font.render() calls.

    Only re-renders when the source data actually changes -- and remembers
    *when* it last changed, so callers can flash a brief "flare" (see
    effects_kit.draw_flare) to draw the eye to what's new. Calm baseline,
    loud change: static data stays quiet, changed data gets a moment.
    """

    def __init__(self):
        self._cache = {}
        self._changed_at = {}

    def get_or_render(self, key, render_func, data_hash):
        """Return cached surface if data_hash unchanged, else re-render."""
        entry = self._cache.get(key)
        if entry and entry[1] == data_hash:
            return entry[0]
        surface = render_func()
        self._cache[key] = (surface, data_hash)
        # A key's first render (entry is None) doesn't count as a "change"
        # worth flaring -- that's just the module appearing on boot.
        if entry is not None:
            self._changed_at[key] = time.time()
        return surface

    def flare_alpha(self, key, duration=FLARE_DURATION_S):
        """0-255, peaking right after `key` last changed and easing to 0
        over `duration` seconds. 0 if it's never changed (or boot-rendered)."""
        changed_at = self._changed_at.get(key)
        if changed_at is None:
            return 0
        age = time.time() - changed_at
        if age >= duration:
            return 0
        t = 1.0 - (age / duration)
        return int(255 * (t * t))

    def invalidate(self, key=None):
        """Clear specific key or entire cache."""
        if key:
            self._cache.pop(key, None)
            self._changed_at.pop(key, None)
        else:
            self._cache.clear()
            self._changed_at.clear()


class InstrumentPanel:
    """Shared plumbing for the habitat instrument modules.

    Every redesigned module needs the same two things:

    1. An SRCALPHA compositing layer. `pygame.draw.*` ignores the alpha
       channel of its colour when it writes to the display surface, so a
       dim "track" and a bright "value" drawn straight to screen come out
       identically solid -- a segmented gauge ends up showing no value at
       all. Drawing into a layer and blitting once makes alpha mean
       something, and costs one allocation per module size.
    2. A cached tracked-text renderer, since pygame has no letterspacing
       and these panels are dense with small tracked labels.

    Modules mix this in, implement `_render_panel(surf, width, height,
    position)`, and call `draw_instrument()` from their own `draw()`.
    """

    INSTRUMENT_FONTS = {
        'f_hero': ('light', 40),
        'f_big': ('light', 28),
        'f_title': ('light', 25),
        'f_value': ('light', 21),
        'f_small': ('light', 14),
        'f_micro': ('regular', 10),
        'f_nano': ('regular', 8),
    }

    def _panel_init(self):
        if getattr(self, '_panel_ready', False):
            return
        for key, (weight, size) in self.INSTRUMENT_FONTS.items():
            setattr(self, key, load_font(weight, size))
        self._text_cache = {}
        self._layer = None
        self._panel_ready = True

    def _text(self, font_key, text, color, spacing=0):
        """Cached text render with optional letter-spacing."""
        key = (font_key, text, color, spacing)
        cached = self._text_cache.get(key)
        if cached is not None:
            return cached
        font = getattr(self, font_key)
        if spacing <= 0:
            surf = font.render(text, True, color)
        else:
            glyphs = [font.render(ch, True, color) for ch in text]
            width = sum(g.get_width() for g in glyphs) + spacing * max(0, len(glyphs) - 1)
            surf = pygame.Surface((max(1, width), font.get_height()), pygame.SRCALPHA)
            gx = 0
            for g in glyphs:
                surf.blit(g, (gx, 0))
                gx += g.get_width() + spacing
        if len(self._text_cache) > 600:
            self._text_cache.clear()
        self._text_cache[key] = surf
        return surf

    def _layer_for(self, width, height):
        layer = getattr(self, '_layer', None)
        if layer is None or layer.get_size() != (width, height):
            layer = pygame.Surface((max(1, width), max(1, height)), pygame.SRCALPHA)
            self._layer = layer
        return layer

    def _cached_panel(self, key, width, height, data_hash, render_fn):
        """Cache an expensive but static sub-panel, rebuilding only when
        its data changes. A forecast strip redraws dozens of vector glyphs
        and a full curve; doing that 30 times a second for data that moves
        twice an hour is the single easiest thing to stop paying for."""
        store = getattr(self, '_subpanels', None)
        if store is None:
            store = self._subpanels = {}
        entry = store.get(key)
        if entry is not None and entry[1] == data_hash and entry[0].get_size() == (width, height):
            return entry[0]
        surf = pygame.Surface((max(1, width), max(1, height)), pygame.SRCALPHA)
        render_fn(surf)
        store[key] = (surf, data_hash)
        return surf

    @staticmethod
    def _panel_geometry(position, default=(300, 200)):
        if isinstance(position, dict):
            return (position['x'], position['y'],
                    position.get('width', default[0]),
                    position.get('height', default[1]))
        x, y = position
        return x, y, default[0], default[1]

    def draw_instrument(self, screen, position, default=(300, 200)):
        """Render `_render_panel` into the alpha layer and blit it once."""
        import logging
        import traceback
        try:
            x, y, width, height = self._panel_geometry(position, default)
            self._panel_init()
            layer = self._layer_for(width, height)
            layer.fill((0, 0, 0, 0))
            self._render_panel(layer, width, height, position)
            screen.blit(layer, (x, y))
        except Exception as exc:
            logging.error(f"{type(self).__name__} draw failed: {exc}")
            logging.error(traceback.format_exc())

    def _panel_header(self, surf, x, y, w, title, accent, align='left',
                      right_text=None, right_color=None, subtitle=None):
        """Tracked uppercase title over a hairline rule with a bright lead
        segment -- the common anchor that ties every instrument together.
        Returns the y offset content should start at."""
        label = self._text('f_micro', title.upper(), accent, spacing=2)
        lx = x + w - label.get_width() if align == 'right' else x
        surf.blit(label, (lx, y))
        cur = y + label.get_height() + 2

        if subtitle:
            sub = self._text('f_nano', subtitle.upper(), COLOR_TEXT_DIM, spacing=2)
            sx = x + w - sub.get_width() if align == 'right' else x
            surf.blit(sub, (sx, cur))
            cur += sub.get_height() + 2

        if right_text:
            # The status tag goes opposite the title, or it lands on top of
            # it in a right-aligned column.
            rt = self._text('f_nano', right_text.upper(),
                            right_color or COLOR_TEXT_DIM, spacing=1)
            surf.blit(rt, (x if align == 'right' else x + w - rt.get_width(), y + 1))

        lead = int(w * 0.30)
        if align == 'right':
            pygame.draw.line(surf, (*accent, 45), (x, cur + 2), (x + w - lead, cur + 2), 1)
            pygame.draw.line(surf, (*accent, 165),
                             (x + w - lead, cur + 2), (x + w, cur + 2), 1)
        else:
            pygame.draw.line(surf, (*accent, 165), (x, cur + 2), (x + lead, cur + 2), 1)
            pygame.draw.line(surf, (*accent, 45), (x + lead, cur + 2), (x + w, cur + 2), 1)
        return cur + 9


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
    def draw_module_title(screen, text, x, y, width, align='left', accent_color=None):
        """Draw a module label: tracked uppercase with a short hairline
        rule in the given accent underneath (champagne by default, but
        every module now gets its own category color -- see MODULE_ACCENTS
        in config.py -- so the mirror reads as more than one flat look).

        Returns the y-offset below the label for content to start.
        """
        ModuleDrawHelper._ensure_fonts()
        if accent_color is not None:
            accent = accent_color
        else:
            import theme
            accent = theme.primary()

        key = (text, align, accent)
        label = ModuleDrawHelper._title_cache.get(key)
        if label is None:
            label = ModuleDrawHelper.render_tracked(
                ModuleDrawHelper._label_font, text.upper(), accent
            )
            label.set_alpha(TRANSPARENCY)
            ModuleDrawHelper._title_cache[key] = label

        # A short keyline in the module's own accent gives each one a
        # distinct anchor without placing an opaque card over the mirror.
        rule_w = 42
        if align == 'right':
            lx = x + width - label.get_width()
        else:
            lx = x
        screen.blit(label, (lx, y))

        import theme
        rule_y = y + label.get_height() + 5
        rule = pygame.Surface((rule_w, 2), pygame.SRCALPHA)
        rule.fill((*theme.separator(), min(TRANSPARENCY, 190)))
        rule.fill((*accent, TRANSPARENCY), (0, 0, 7, 2))
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
