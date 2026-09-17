"""Date-specific Moments -- calendar events that only make sense on a
particular day (New Year, Bonfire Night, a solstice), fired through the
Director so they get the same dedup/timing machinery as everything else.

check_calendar_moments(director) is called periodically (see AI-Mirror.py)
and calls director.notify(...) whenever today/now matches; the Director's
own per-moment cooldown (set here to ~a year) is what actually prevents
a second firing later the same day, not this checker.
"""

import math
import random
from datetime import datetime

import pygame

from effects_kit import glow_sprite, ease_out_cubic
from event_director import Moment

_YEAR = 3600 * 24 * 300


def _firework_burst(screen, elapsed, cx, cy, start, color, spread=340):
    age = elapsed - start
    if age < 0 or age > 1.8:
        return
    t = age / 1.8

    # A bright flash at the moment of detonation sells the "boom".
    if age < 0.12:
        flash = glow_sprite(int(spread * 0.35), (255, 250, 235),
                            int(220 * (1.0 - age / 0.12)), core_frac=0.5)
        screen.blit(flash, (int(cx) - flash.get_width() // 2, int(cy) - flash.get_height() // 2))

    n = 24
    for i in range(n):
        ang = (math.tau / n) * i + start * 3.0
        dist = spread * ease_out_cubic(min(1.0, t * 1.15))
        fall = (age ** 2) * 70
        alpha = max(0, int(255 * (1.0 - t) ** 1.4))
        if alpha <= 0:
            continue
        # A short fading trail behind each spark, not just a single dot.
        for k, back in enumerate((0.0, 0.06, 0.12)):
            a2 = elapsed - start - back
            if a2 < 0:
                continue
            t2 = a2 / 1.8
            d2 = spread * ease_out_cubic(min(1.0, t2 * 1.15))
            x = cx + math.cos(ang) * d2
            y = cy + math.sin(ang) * d2 + (a2 ** 2) * 70
            a = max(0, int(alpha * (1.0 - k * 0.4)))
            if a <= 0:
                continue
            r = 9 if k == 0 else 5
            spark = glow_sprite(r, color, a, core_frac=0.55)
            screen.blit(spark, (int(x) - spark.get_width() // 2, int(y) - spark.get_height() // 2))


def _render_fireworks(screen, elapsed, ctx):
    w, h = screen.get_width(), screen.get_height()
    rng = random.Random(7)
    palette = [(255, 210, 110), (130, 200, 255), (255, 130, 190),
               (150, 240, 180), (255, 160, 100), (200, 160, 255)]
    bursts = [
        (rng.uniform(w * 0.15, w * 0.85), rng.uniform(h * 0.12, h * 0.5),
         i * 0.45, rng.choice(palette))
        for i in range(10)
    ]
    for cx, cy, start, color in bursts:
        _firework_burst(screen, elapsed, cx, cy, start, color)


def _render_geeky_nod(screen, elapsed, ctx):
    duration = 3.0
    t = min(elapsed / duration, 1.0)
    alpha_t = math.sin(t * math.pi)
    font = pygame.font.SysFont('consolas,dejavusansmono,monospace', 120, bold=True)
    label = ctx.get('glyph', 'π') if ctx else 'π'
    surf = font.render(label, True, (242, 222, 172))
    surf.set_alpha(int(220 * alpha_t))
    w, h = screen.get_width(), screen.get_height()
    screen.blit(surf, (w // 2 - surf.get_width() // 2, int(h * 0.4)))


def _render_solstice_marker(screen, elapsed, ctx):
    duration = 5.0
    t = min(elapsed / duration, 1.0)
    alpha = int(70 * math.sin(t * math.pi))
    if alpha <= 0:
        return
    w, h = screen.get_width(), screen.get_height()
    label = (ctx or {}).get('label', 'Solstice')
    font = pygame.font.SysFont('consolas,dejavusansmono,monospace', 22)
    surf = font.render(label, True, (196, 174, 128))
    surf.set_alpha(alpha)
    screen.blit(surf, (w // 2 - surf.get_width() // 2, int(h * 0.06)))


def _render_friday_winddown(screen, elapsed, ctx):
    duration = 6.0
    t = min(elapsed / duration, 1.0)
    alpha = int(26 * math.sin(t * math.pi))
    if alpha <= 0:
        return
    w, h = screen.get_width(), screen.get_height()
    wash = pygame.Surface((w, h), pygame.SRCALPHA)
    wash.fill((246, 190, 120, alpha))
    screen.blit(wash, (0, 0))


_MOMENTS = [
    Moment('new_year_fireworks', 'seasonal', _render_fireworks,
           duration_s=7.0, cooldown_s=_YEAR, weight=3.0,
           trigger_events=('new_year',)),
    Moment('bonfire_night_fireworks', 'seasonal', _render_fireworks,
           duration_s=7.0, cooldown_s=_YEAR, weight=3.0,
           trigger_events=('fireworks_night',)),
    Moment('geeky_calendar_nod', 'seasonal', _render_geeky_nod,
           duration_s=3.0, cooldown_s=_YEAR, weight=1.0,
           trigger_events=('geeky_date',)),
    Moment('solstice_marker', 'seasonal', _render_solstice_marker,
           duration_s=5.0, cooldown_s=_YEAR / 4, weight=1.0,
           trigger_events=('solstice_equinox',)),
    Moment('friday_winddown', 'seasonal', _render_friday_winddown,
           duration_s=6.0, cooldown_s=3600 * 20, weight=1.0,
           trigger_events=('friday_evening',)),
]


def register(director):
    for m in _MOMENTS:
        director.register(m)


_last_check_key = None


def check_calendar_moments(director, now=None):
    """Call periodically (once a minute is plenty) from the main loop."""
    global _last_check_key
    now = now or datetime.now()
    key = (now.year, now.month, now.day, now.hour, now.minute)
    if key == _last_check_key:
        return
    _last_check_key = key

    if now.month == 1 and now.day == 1 and now.hour == 0 and now.minute == 0:
        director.notify('new_year')
    if now.month == 11 and now.day == 5 and 18 <= now.hour <= 21:
        director.notify('fireworks_night')
    if now.month == 3 and now.day == 14:
        director.notify('geeky_date', {'glyph': 'π'})
    if (now.month, now.day) in ((3, 20), (6, 21), (9, 22), (12, 21)):
        director.notify('solstice_equinox', {'label': 'Solstice'})
    if now.weekday() == 4 and 16 <= now.hour <= 19:
        director.notify('friday_evening')
