"""Seasonal/holiday theming for AI-Mirror.

Unlike Moments (event_director.py -- rare, triggered, a few seconds),
themes are persistent moods: a date range swaps the accent color and
adds a light continuous overlay (string lights, drifting fog, petals)
for as long as that window lasts. Checked once per frame but cheap
(a date comparison plus a handful of cached-position draws).

Date-driven "moment" triggers that only make sense on a specific day
(New Year fireworks, Pi Day) live in moments_seasonal.py and are fired
from here via check_calendar_moments(), since they need the Director's
timing/dedup machinery, not a continuous overlay.
"""

import math
import random
from datetime import date

import pygame

from effects_kit import soft_blob, glow_sprite

CLOUD_TINT = (157, 187, 218)


def current_theme(today=None):
    """The active seasonal skin for today's date, or 'default'."""
    d = today or date.today()
    m, day = d.month, d.day
    if (m == 10 and day >= 20) or (m == 11 and day <= 2):
        return 'halloween'
    if (m == 12 and day >= 1) or (m == 1 and day <= 6):
        return 'christmas'
    if m in (3, 4, 5):
        return 'spring'
    return 'default'


def accent_override(theme):
    """An alternate hairline/label accent for the active theme, or None
    to keep the house champagne (config.COLOR_ACCENT_PRIMARY)."""
    return {
        'halloween': (255, 140, 60),
        'christmas': (210, 60, 70),
    }.get(theme)


class _ThemeOverlay:
    """Owns the lazily-built, cached particle state for whichever theme
    is active -- rebuilt only when the theme or screen size changes."""

    def __init__(self):
        self._theme = None
        self._w = self._h = 0
        self._fog = []
        self._lights = []
        self._petals = []
        self._t = 0.0

    def _ensure(self, theme, w, h):
        if theme == self._theme and w == self._w and h == self._h:
            return
        self._theme, self._w, self._h = theme, w, h
        self._fog = []
        self._lights = []
        self._petals = []

        if theme == 'halloween':
            for _ in range(4):
                width = random.randint(int(w * 0.25), int(w * 0.45))
                self._fog.append({
                    'surf': soft_blob(width, (140, 140, 150), 46, height_ratio=0.30),
                    'x': random.uniform(-width * 0.3, w),
                    'y': random.uniform(h * 0.75, h * 0.96),
                    'speed': random.uniform(5.0, 12.0),
                })

        elif theme == 'christmas':
            count = max(10, w // 90)
            colors = [(210, 60, 70), (70, 170, 90), (240, 210, 130)]
            for i in range(count):
                x = (i + 0.5) / count * w
                self._lights.append({
                    'x': x, 'y': 2, 'color': random.choice(colors),
                    'phase': random.uniform(0, math.tau),
                })
                self._lights.append({
                    'x': x, 'y': h - 3, 'color': random.choice(colors),
                    'phase': random.uniform(0, math.tau),
                })

        elif theme == 'spring':
            for _ in range(14):
                self._petals.append({
                    'x': random.uniform(0, w),
                    'y': random.uniform(-h, 0),
                    'speed': random.uniform(14.0, 30.0),
                    'sway': random.uniform(10.0, 26.0),
                    'phase': random.uniform(0, math.tau),
                    'r': random.uniform(2.0, 4.0),
                })

    def update(self, dt):
        self._t += dt
        for f in self._fog:
            f['x'] += f['speed'] * dt
            if f['x'] > self._w:
                f['x'] = -f['surf'].get_width()
        for p in self._petals:
            p['y'] += p['speed'] * dt
            if p['y'] > self._h:
                p['y'] = random.uniform(-40, 0)
                p['x'] = random.uniform(0, self._w)

    def draw(self, screen, theme, wind_speed=0.0):
        w, h = screen.get_width(), screen.get_height()
        self._ensure(theme, w, h)

        if theme == 'halloween':
            for f in self._fog:
                screen.blit(f['surf'], (int(f['x']), int(f['y'])))

        elif theme == 'christmas':
            for lamp in self._lights:
                tw = 0.5 + 0.5 * math.sin(self._t * 1.6 + lamp['phase'])
                glow = glow_sprite(7, lamp['color'], int(90 + 120 * tw), core_frac=0.4)
                screen.blit(glow, (int(lamp['x']) - glow.get_width() // 2,
                                   int(lamp['y']) - glow.get_height() // 2))

        elif theme == 'spring':
            for p in self._petals:
                x = p['x'] + math.sin(self._t * 0.6 + p['phase']) * p['sway']
                pygame.draw.circle(screen, (244, 196, 210),
                                   (int(x), int(p['y'])), int(p['r']))


_overlay = _ThemeOverlay()


def update(dt):
    _overlay.update(dt)


def draw(screen):
    theme = current_theme()
    if theme != 'default':
        _overlay.draw(screen, theme)
