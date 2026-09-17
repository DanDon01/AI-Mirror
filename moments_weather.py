"""Weather-spectacle Moments for the Director (event_director.py).

These are the rare, full-screen theatrical counterparts to the quiet,
always-on weather band in weather_animations.py -- a real lightning
strike gets a moment that whites out the whole mirror, not just the
top band; a real sunrise gets a slow warm curtain across the whole
screen, not just the sky-stage. See the project plan ("The Glo-Up")
for the full moment library and phasing.
"""

import math
import random

import pygame

from effects_kit import (
    glow_sprite, vertical_gradient, flash_alpha_envelope, jagged_bolt, ease_out_cubic,
)
from weather_animations import SUN_TINT, MOON_TINT, RAIN_TINT, PLATINUM
from config import COLOR_ACCENT_AMBER
from event_director import Moment


def _fade_in_hold_out(elapsed, duration, fade_in_frac=0.3, fade_out_frac=0.3):
    """Ease in over the first fraction, hold, ease out over the last."""
    if duration <= 0:
        return 0.0
    t = elapsed / duration
    if t < fade_in_frac:
        return ease_out_cubic(t / fade_in_frac)
    if t > 1.0 - fade_out_frac:
        return ease_out_cubic((1.0 - t) / fade_out_frac)
    return 1.0


# ---------------------------------------------------------------- storm

def _storm_takeover(screen, elapsed, ctx):
    w, h = screen.get_width(), screen.get_height()
    level = flash_alpha_envelope(elapsed)
    if level <= 0:
        return
    wash = pygame.Surface((w, h), pygame.SRCALPHA)
    wash.fill((*PLATINUM, int(60 * level)))
    screen.blit(wash, (0, 0))
    if level > 0.35:
        bolt = jagged_bolt(
            x_range=(w * 0.3, w * 0.7), y_range=(0, h * 0.94),
            width=w, segment_height_range=(h * 0.05, h * 0.09), jitter_x=int(w * 0.05),
        )
        pygame.draw.lines(screen, (*PLATINUM, int(235 * level)), False, bolt, 5)
        pygame.draw.lines(screen, (255, 255, 255, int(160 * level)), False, bolt, 2)


# --------------------------------------------------------- windscreen wiper

def _giant_wiper(screen, elapsed, ctx):
    w, h = screen.get_width(), screen.get_height()
    duration = 2.0
    t = max(0.0, min(1.0, elapsed / duration))
    angle = ease_out_cubic(t) * math.pi  # sweeps a half-circle, left to right
    base = (w * 0.5, h * 1.05)
    length = h * 1.05

    def blade_end(a):
        return (base[0] + math.cos(math.pi - a) * length,
                base[1] - math.sin(a) * length)

    # Fading smear trail behind the current angle.
    for i in range(6, 0, -1):
        trail_a = angle - i * 0.05
        if trail_a < 0:
            continue
        alpha = int(70 * (1.0 - i / 6.0))
        ex, ey = blade_end(trail_a)
        pygame.draw.line(screen, (*RAIN_TINT, alpha), base, (ex, ey), 10)

    ex, ey = blade_end(angle)
    pygame.draw.line(screen, (*PLATINUM, 190), base, (ex, ey), 14)
    pygame.draw.line(screen, (*RAIN_TINT, 140), base, (ex, ey), 6)


# ----------------------------------------------------- sunrise / sunset

def _sun_curtain(screen, elapsed, ctx):
    w, h = screen.get_width(), screen.get_height()
    duration = 12.0
    level = _fade_in_hold_out(elapsed, duration)
    if level <= 0.01:
        return
    wash = vertical_gradient(w, h, SUN_TINT, (8, 10, 18), top_alpha=int(42 * level), bottom_alpha=0)
    screen.blit(wash, (0, 0))


# ------------------------------------------------------- full moon spotlight

def _full_moon_spotlight(screen, elapsed, ctx):
    w, h = screen.get_width(), screen.get_height()
    breath = 0.5 + 0.5 * math.sin(elapsed * 0.6)
    cx, cy = w * 0.5, h * 0.16
    halo = glow_sprite(int(h * 0.22), MOON_TINT, int(60 + 40 * breath), core_frac=0.18)
    screen.blit(halo, (cx - halo.get_width() / 2, cy - halo.get_height() / 2))
    core = glow_sprite(int(h * 0.08), MOON_TINT, 200, core_frac=0.5)
    screen.blit(core, (cx - core.get_width() / 2, cy - core.get_height() / 2))

    beam_count = 4
    for i in range(beam_count):
        bx = cx + (i - (beam_count - 1) / 2.0) * w * 0.09
        beam = vertical_gradient(int(w * 0.05), int(h * 0.55), MOON_TINT, MOON_TINT,
                                 top_alpha=int(26 * breath), bottom_alpha=0)
        screen.blit(beam, (bx - beam.get_width() / 2, cy))


# --------------------------------------------------------- snow globe shake

def _snow_globe_shake(screen, elapsed, ctx):
    w, h = screen.get_width(), screen.get_height()
    duration = 3.0
    rng = random.Random(1234)
    count = 140
    shake_t = max(0.0, 1.0 - elapsed / 0.5)
    for i in range(count):
        seed_x = rng.uniform(0, w)
        seed_y = rng.uniform(0, h)
        speed = rng.uniform(40, 140)
        sway_phase = rng.uniform(0, math.tau)
        r = rng.choice((1, 1, 2, 2, 3))
        y = (seed_y + elapsed * speed) % h
        jitter_x = math.sin(elapsed * 40 + i) * (20 * shake_t)
        jitter_y = math.cos(elapsed * 37 + i) * (20 * shake_t)
        x = (seed_x + math.sin(elapsed * 0.8 + sway_phase) * 14 + jitter_x) % w
        alpha = 90 if elapsed < duration - 0.6 else int(90 * max(0.0, (duration - elapsed) / 0.6))
        pygame.draw.circle(screen, (*PLATINUM, alpha), (int(x), int(y + jitter_y)), r)


# ------------------------------------------------------------- fog reveal

def _fog_reveal(screen, elapsed, ctx):
    w, h = screen.get_width(), screen.get_height()
    duration = 4.0
    t = elapsed / duration
    # Peaks around 25% through, then clears -- like the mirror defogging.
    if t < 0.25:
        level = ease_out_cubic(t / 0.25)
    else:
        level = max(0.0, 1.0 - ease_out_cubic((t - 0.25) / 0.75))
    if level <= 0.01:
        return
    wash = pygame.Surface((w, h), pygame.SRCALPHA)
    wash.fill((*PLATINUM, int(110 * level)))
    screen.blit(wash, (0, 0))


# ------------------------------------------------------- rainbow after rain

_RAINBOW = [
    (230, 90, 90), (230, 160, 90), (230, 220, 90),
    (120, 210, 130), (100, 170, 230), (140, 120, 220),
]


def _rainbow_after_rain(screen, elapsed, ctx):
    w, h = screen.get_width(), screen.get_height()
    duration = 6.0
    level = _fade_in_hold_out(elapsed, duration, 0.3, 0.4)
    if level <= 0.01:
        return
    cx, cy = w * 0.5, h * 0.30
    base_r = h * 0.30
    for i, color in enumerate(_RAINBOW):
        r = base_r + i * (h * 0.018)
        alpha = int(55 * level)
        arc_surf = pygame.Surface((int(r * 2), int(r * 2)), pygame.SRCALPHA)
        rect = pygame.Rect(0, 0, int(r * 2), int(r * 2))
        pygame.draw.arc(arc_surf, (*color, alpha), rect, math.pi, math.tau, 4)
        screen.blit(arc_surf, (cx - r, cy - r))


# ------------------------------------------------------- heat haze shimmer

def _heat_haze(screen, elapsed, ctx):
    w, h = screen.get_width(), screen.get_height()
    duration = 4.0
    level = _fade_in_hold_out(elapsed, duration, 0.2, 0.35)
    if level <= 0.01:
        return
    base_y = h * 0.97
    for i in range(10):
        y = base_y - i * 7
        alpha = int(30 * level * (1.0 - i / 10.0))
        pts = []
        for x in range(0, int(w) + 1, 24):
            offset = math.sin(elapsed * 3.0 + x * 0.02 + i) * 5
            pts.append((x, y + offset))
        if len(pts) > 1:
            pygame.draw.lines(screen, (*COLOR_ACCENT_AMBER, alpha), False, pts, 2)


# ---------------------------------------------------------- gale gust

def _gale_gust(screen, elapsed, ctx):
    w, h = screen.get_width(), screen.get_height()
    duration = 0.6
    level = 1.0 - (elapsed / duration)
    if level <= 0:
        return
    rng = random.Random(777)
    for i in range(14):
        y = rng.uniform(0, h)
        length = rng.uniform(w * 0.08, w * 0.22)
        speed = rng.uniform(w * 1.6, w * 2.4)
        x_end = (elapsed * speed + rng.uniform(0, w)) % (w + length) - length
        alpha = int(50 * level)
        pygame.draw.line(screen, (*PLATINUM, alpha), (x_end, y), (x_end + length, y), 2)


# ---------------------------------------------------------- aurora night

_AURORA_COLORS = [(100, 220, 150), (170, 120, 220), (100, 190, 220)]


def _aurora_night(screen, elapsed, ctx):
    w, h = screen.get_width(), screen.get_height()
    duration = 10.0
    level = _fade_in_hold_out(elapsed, duration, 0.25, 0.3)
    if level <= 0.01:
        return
    band_h = int(h * 0.30)
    for i, color in enumerate(_AURORA_COLORS):
        flicker = 0.5 + 0.5 * math.sin(elapsed * (0.4 + i * 0.15) + i * 2.0)
        drift = math.sin(elapsed * 0.12 + i) * w * 0.08
        band_w = int(w * 0.55)
        band = vertical_gradient(band_w, band_h, color, (8, 10, 18),
                                 top_alpha=int(34 * level * flicker), bottom_alpha=0)
        x = (w * (0.15 + i * 0.28)) + drift - band_w / 2
        screen.blit(band, (x, 0))


_MOMENTS = [
    Moment("storm_takeover", "weather", _storm_takeover,
          duration_s=0.7, cooldown_s=90, weight=1.2, trigger_events=("lightning_strike",)),
    Moment("giant_windscreen_wiper", "weather", _giant_wiper,
          duration_s=2.0, cooldown_s=1800, weight=1.0, trigger_events=("rain_onset",)),
    Moment("sunrise_curtain", "weather", _sun_curtain,
          duration_s=12.0, cooldown_s=3600 * 20, weight=1.0, trigger_events=("sunrise",)),
    Moment("sunset_curtain", "weather", _sun_curtain,
          duration_s=12.0, cooldown_s=3600 * 20, weight=1.0, trigger_events=("sunset",)),
    Moment("full_moon_spotlight", "weather", _full_moon_spotlight,
          duration_s=8.0, cooldown_s=3600 * 20, weight=0.9, trigger_events=("full_moon_night",)),
    Moment("snow_globe_shake", "weather", _snow_globe_shake,
          duration_s=3.0, cooldown_s=3600 * 6, weight=1.0, trigger_events=("snow_onset",)),
    Moment("fog_reveal", "weather", _fog_reveal,
          duration_s=4.0, cooldown_s=3600 * 6, weight=0.9, trigger_events=("fog_onset",)),
    Moment("rainbow_after_rain", "weather", _rainbow_after_rain,
          duration_s=6.0, cooldown_s=3600 * 8, weight=1.0, trigger_events=("rain_stopped_sun_out",)),
    Moment("heat_haze_shimmer", "weather", _heat_haze,
          duration_s=4.0, cooldown_s=1800, weight=0.8, trigger_events=("heatwave",)),
    Moment("gale_warning_gust", "weather", _gale_gust,
          duration_s=0.6, cooldown_s=900, weight=0.8, trigger_events=("high_wind",)),
    Moment("aurora_night", "weather", _aurora_night,
          duration_s=10.0, cooldown_s=3600 * 40, weight=0.6, trigger_events=("aurora_chance",)),
]


def register(director):
    for m in _MOMENTS:
        director.register(m)
