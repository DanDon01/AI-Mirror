"""Ambient weather for the AI-Mirror top banner.

The banner quietly reflects the sky: a breathing sun glow, layered
parallax clouds, wind-slanted rain streaks, drifting snow, a crescent
moon with faint stars, and a soft lightning pulse for storms.

Design rules (minimal luxury):
  - Everything is procedural soft-glow drawing - no icon PNGs.
  - Confined to the top banner; a vertical alpha gradient dissolves the
    scene before the hairline rule so the mirror space stays clear.
  - Near-monochrome platinum with a hint of warmth for the sun; all
    alphas low so the time and date always dominate.
  - All motion is dt-based (px/sec), slow enough to feel atmospheric.

Class names and constructors are kept compatible with the original
implementation; all accept an optional wind_speed (m/s) which adds
gust streaks and slants the rain.
"""

import math
import random
import time

import pygame

from config import LAYOUT_V2

BANNER_H = LAYOUT_V2.get('zones', {}).get('top_bar', {}).get('height', 95)
FADE_DEPTH = 34          # px at the bottom of the banner that dissolve
WINDY_THRESHOLD = 8.0    # m/s above which gust streaks appear

# Palette (kept local: ambience, not UI text)
PLATINUM = (226, 228, 232)
RAIN_TINT = (186, 200, 218)
SUN_TINT = (236, 222, 188)
MOON_TINT = (214, 220, 232)
CLOUD_TINT = (200, 203, 210)


def _glow_sprite(radius, color, core_alpha, core_frac=0.3):
    """Pre-render a smooth radial glow: bright core, quadratic falloff.

    One circle per pixel of radius, largest first, so the gradient is
    perfectly smooth (no concentric ring banding). Build once, blit
    per frame - never call this in a draw loop.
    """
    size = radius * 2 + 2
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    center = (radius + 1, radius + 1)
    for r in range(radius, 0, -1):
        t = r / radius
        if t <= core_frac:
            a = core_alpha
        else:
            a = core_alpha * ((1.0 - t) / (1.0 - core_frac)) ** 2
        pygame.draw.circle(surf, (*color, int(a)), center, r)
    return surf


def _make_cloud(width, alpha):
    """Pre-render a soft cotton cloud from overlapping glow puffs.

    Puffs are merged with BLEND_RGBA_MAX so overlaps blend into one
    smooth silhouette instead of leaving overwrite seams.
    """
    height = int(width * 0.5)
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    puffs = random.randint(5, 7)
    for i in range(puffs):
        r = random.randint(int(width * 0.11), int(width * 0.18))
        puff = _glow_sprite(r, CLOUD_TINT, alpha, core_frac=0.45)
        px = int((i / max(puffs - 1, 1)) * (width - r * 2)
                 + random.randint(-8, 8))
        py = random.randint(int(height * 0.2), height - r * 2)
        px = max(0, min(px, width - r * 2 - 2))
        py = max(0, min(py, height - r * 2 - 2))
        surf.blit(puff, (px, py), special_flags=pygame.BLEND_RGBA_MAX)
    return surf


class WeatherAnimation:
    """Base: banner-confined scene with bottom fade-out."""

    def __init__(self, screen_width, screen_height, wind_speed=0.0):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.wind_speed = wind_speed or 0.0
        self.banner_h = BANNER_H
        self._surf = pygame.Surface((screen_width, self.banner_h), pygame.SRCALPHA)
        self._fade_mask = self._build_fade_mask()
        self._last = time.monotonic()
        self.t = 0.0

        # Gust streaks for windy conditions (any scene)
        self._gusts = []
        if self.wind_speed >= WINDY_THRESHOLD:
            self._gusts = [self._new_gust(seed_x=True) for _ in range(6)]

    def _build_fade_mask(self):
        mask = pygame.Surface((self.screen_width, self.banner_h), pygame.SRCALPHA)
        mask.fill((255, 255, 255, 255))
        for i in range(FADE_DEPTH):
            a = int(255 * (1.0 - (i + 1) / FADE_DEPTH))
            row_y = self.banner_h - FADE_DEPTH + i
            pygame.draw.line(mask, (255, 255, 255, a), (0, row_y),
                             (self.screen_width, row_y))
        return mask

    def _new_gust(self, seed_x=False):
        return {
            'x': random.uniform(0, self.screen_width) if seed_x else -100.0,
            'y': random.uniform(10, self.banner_h - FADE_DEPTH),
            'len': random.uniform(50, 110),
            'speed': random.uniform(90, 170),
            'alpha': random.randint(14, 30),
        }

    def _update_gusts(self, dt):
        for g in self._gusts:
            g['x'] += g['speed'] * dt
            if g['x'] - g['len'] > self.screen_width:
                g.update(self._new_gust())
                g['x'] = -g['len']

    def _draw_gusts(self, surf):
        for g in self._gusts:
            pygame.draw.line(
                surf, (*PLATINUM, g['alpha']),
                (int(g['x'] - g['len']), int(g['y'])),
                (int(g['x']), int(g['y'])), 1,
            )

    def update(self):
        now = time.monotonic()
        dt = min(now - self._last, 0.1)
        self._last = now
        self.t += dt
        self._update_gusts(dt)
        self._step(dt)

    def _step(self, dt):
        pass

    def _draw_scene(self, surf):
        pass

    def draw(self, screen):
        self._surf.fill((0, 0, 0, 0))
        self._draw_scene(self._surf)
        self._draw_gusts(self._surf)
        self._surf.blit(self._fade_mask, (0, 0),
                        special_flags=pygame.BLEND_RGBA_MULT)
        screen.blit(self._surf, (0, 0))


class _CloudLayerMixin:
    """Shared drifting cloud layers (parallax: far = slower + fainter).

    Clouds live in a band starting right of the big time digits so the
    clock anchor stays clean; they wrap within that band.
    """

    def _init_clouds(self, count, alphas=(16, 24, 32)):
        self._cloud_band_x = int(self.screen_width * 0.30)
        self._clouds = []
        for i in range(count):
            depth = i % len(alphas)
            width = random.randint(150, 280) - depth * 30
            self._clouds.append({
                'surf': _make_cloud(width, alphas[depth]),
                'x': random.uniform(self._cloud_band_x, self.screen_width),
                'y': random.uniform(-14, self.banner_h * 0.25),
                'speed': (3.0 + depth * 3.5) * (1.0 + self.wind_speed * 0.08),
            })

    def _step_clouds(self, dt):
        for c in self._clouds:
            c['x'] += c['speed'] * dt
            if c['x'] > self.screen_width:
                c['x'] = self._cloud_band_x - c['surf'].get_width() * 0.5
                c['y'] = random.uniform(-14, self.banner_h * 0.25)

    def _draw_clouds(self, surf):
        clip = surf.get_clip()
        surf.set_clip(pygame.Rect(self._cloud_band_x, 0,
                                  self.screen_width - self._cloud_band_x,
                                  self.banner_h))
        for c in self._clouds:
            surf.blit(c['surf'], (int(c['x']), int(c['y'])))
        surf.set_clip(clip)


class SunAnimation(WeatherAnimation):
    """Stationary sun: warm glow disc with a slowly breathing halo."""

    def __init__(self, screen_width, screen_height, wind_speed=0.0):
        super().__init__(screen_width, screen_height, wind_speed)
        self.cx = int(screen_width * 0.58)
        self.cy = int(self.banner_h * 0.46)
        self._halo = _glow_sprite(46, SUN_TINT, 30, core_frac=0.16)
        self._core = _glow_sprite(15, SUN_TINT, 95, core_frac=0.55)

    def _draw_scene(self, surf):
        breath = 0.5 + 0.5 * math.sin(self.t * 0.45)
        scale = 0.86 + breath * 0.22
        size = int(self._halo.get_width() * scale)
        halo = pygame.transform.smoothscale(self._halo, (size, size))
        surf.blit(halo, (self.cx - size // 2, self.cy - size // 2))
        surf.blit(self._core,
                  (self.cx - self._core.get_width() // 2,
                   self.cy - self._core.get_height() // 2))


class MoonAnimation(WeatherAnimation):
    """Crescent moon with a soft halo and a few twinkling stars."""

    def __init__(self, screen_width, screen_height, cloudy=False, wind_speed=0.0):
        super().__init__(screen_width, screen_height, wind_speed)
        self.cx = int(screen_width * 0.58)
        self.cy = int(self.banner_h * 0.44)
        self._halo = _glow_sprite(30, MOON_TINT, 20, core_frac=0.2)
        self._crescent = self._make_crescent(13)
        self._stars = [
            {'x': self.cx + random.randint(-180, 180),
             'y': random.randint(8, self.banner_h - FADE_DEPTH - 6),
             'phase': random.uniform(0, math.tau),
             'rate': random.uniform(0.4, 1.1)}
            for _ in range(4)
        ]
        self._cloud = _make_cloud(170, 20) if cloudy else None
        self._cloud_x = -170.0

    @staticmethod
    def _make_crescent(r):
        size = r * 2 + 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*MOON_TINT, 95), (r + 1, r + 1), r)
        punch = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(punch, (255, 255, 255, 95),
                           (r + 1 + int(r * 0.55), r + 1 - int(r * 0.2)), r)
        surf.blit(punch, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        return surf

    def _step(self, dt):
        if self._cloud is not None:
            self._cloud_x += (4.0 + self.wind_speed * 0.1) * dt
            if self._cloud_x > self.screen_width:
                self._cloud_x = -self._cloud.get_width()

    def _draw_scene(self, surf):
        surf.blit(self._halo,
                  (self.cx - self._halo.get_width() // 2,
                   self.cy - self._halo.get_height() // 2))
        surf.blit(self._crescent,
                  (self.cx - self._crescent.get_width() // 2,
                   self.cy - self._crescent.get_height() // 2))
        for s in self._stars:
            tw = 0.5 + 0.5 * math.sin(self.t * s['rate'] + s['phase'])
            a = int(20 + 60 * tw)
            pygame.draw.circle(surf, (*PLATINUM, a), (s['x'], s['y']), 1)
        if self._cloud is not None:
            surf.blit(self._cloud, (int(self._cloud_x), int(self.banner_h * 0.18)))


class CloudAnimation(_CloudLayerMixin, WeatherAnimation):
    """Layered drifting clouds; partly=True adds the sun glow behind."""

    def __init__(self, screen_width, screen_height, partly=False, wind_speed=0.0):
        super().__init__(screen_width, screen_height, wind_speed)
        self.partly = partly
        self._init_clouds(3 if partly else 5)
        self._sun_cx = int(screen_width * 0.58)
        self._sun_cy = int(self.banner_h * 0.42)
        self._sun = _glow_sprite(34, SUN_TINT, 46, core_frac=0.3) if partly else None

    def _step(self, dt):
        self._step_clouds(dt)

    def _draw_scene(self, surf):
        if self._sun is not None:
            breath = 0.5 + 0.5 * math.sin(self.t * 0.45)
            scale = 0.88 + breath * 0.18
            size = int(self._sun.get_width() * scale)
            sun = pygame.transform.smoothscale(self._sun, (size, size))
            surf.blit(sun, (self._sun_cx - size // 2, self._sun_cy - size // 2))
        self._draw_clouds(surf)


class RainAnimation(_CloudLayerMixin, WeatherAnimation):
    """Thin rain streaks under a cloud layer; wind slants the fall."""

    def __init__(self, screen_width, screen_height, heavy=False, wind_speed=0.0):
        super().__init__(screen_width, screen_height, wind_speed)
        self.heavy = heavy
        self._init_clouds(3, alphas=(18, 26, 34))
        count = 70 if heavy else 42
        self._slant = min(self.wind_speed * 0.05, 0.45)
        self._drops = [self._new_drop(seed=True) for _ in range(count)]

    def _new_drop(self, seed=False):
        return {
            'x': random.uniform(0, self.screen_width),
            'y': random.uniform(0, self.banner_h) if seed else random.uniform(-10, 0),
            'len': random.uniform(7, 15) * (1.25 if self.heavy else 1.0),
            'speed': random.uniform(160, 250) * (1.3 if self.heavy else 1.0),
            'alpha': random.randint(34, 72),
        }

    def _step(self, dt):
        self._step_clouds(dt)
        for d in self._drops:
            d['y'] += d['speed'] * dt
            d['x'] += d['speed'] * self._slant * dt
            if d['y'] - d['len'] > self.banner_h:
                d.update(self._new_drop())

    def _draw_scene(self, surf):
        self._draw_clouds(surf)
        for d in self._drops:
            x2 = d['x'] - d['len'] * self._slant
            pygame.draw.line(
                surf, (*RAIN_TINT, d['alpha']),
                (int(x2), int(d['y'] - d['len'])),
                (int(d['x']), int(d['y'])), 1,
            )


class StormAnimation(RainAnimation):
    """Heavy rain plus an occasional soft double lightning pulse."""

    def __init__(self, screen_width, screen_height, wind_speed=0.0):
        super().__init__(screen_width, screen_height, heavy=True,
                         wind_speed=wind_speed)
        self._next_flash = self.t + random.uniform(4.0, 10.0)
        self._flash_started = None

    # Pulse envelope: two quick peaks over ~0.45s, like sheet lightning
    @staticmethod
    def _flash_alpha(age):
        if age < 0.10:
            return age / 0.10
        if age < 0.20:
            return 1.0 - (age - 0.10) / 0.10 * 0.7
        if age < 0.30:
            return 0.3 + (age - 0.20) / 0.10 * 0.5
        if age < 0.45:
            return 0.8 * (1.0 - (age - 0.30) / 0.15)
        return 0.0

    def _step(self, dt):
        super()._step(dt)
        if self._flash_started is None and self.t >= self._next_flash:
            self._flash_started = self.t
        if self._flash_started is not None and self.t - self._flash_started > 0.45:
            self._flash_started = None
            self._next_flash = self.t + random.uniform(4.0, 10.0)

    def _draw_scene(self, surf):
        if self._flash_started is not None:
            level = self._flash_alpha(self.t - self._flash_started)
            if level > 0:
                glow = pygame.Surface((self.screen_width, self.banner_h),
                                      pygame.SRCALPHA)
                glow.fill((*PLATINUM, int(34 * level)))
                surf.blit(glow, (0, 0))
        super()._draw_scene(surf)


class SnowAnimation(_CloudLayerMixin, WeatherAnimation):
    """Soft flakes drifting down with a gentle sway."""

    def __init__(self, screen_width, screen_height, wind_speed=0.0):
        super().__init__(screen_width, screen_height, wind_speed)
        self._init_clouds(2, alphas=(14, 20, 26))
        self._flakes = [self._new_flake(seed=True) for _ in range(34)]

    def _new_flake(self, seed=False):
        return {
            'x': random.uniform(0, self.screen_width),
            'y': random.uniform(0, self.banner_h) if seed else random.uniform(-6, 0),
            'speed': random.uniform(14, 30),
            'r': random.uniform(1.0, 2.4),
            'alpha': random.randint(40, 95),
            'phase': random.uniform(0, math.tau),
            'sway': random.uniform(4, 11),
        }

    def _step(self, dt):
        self._step_clouds(dt)
        for f in self._flakes:
            f['y'] += f['speed'] * dt
            if f['y'] > self.banner_h:
                f.update(self._new_flake())

    def _draw_scene(self, surf):
        self._draw_clouds(surf)
        for f in self._flakes:
            x = f['x'] + math.sin(self.t * 0.8 + f['phase']) * f['sway']
            pygame.draw.circle(
                surf, (*PLATINUM, f['alpha']), (int(x), int(f['y'])),
                max(1, int(f['r'])),
            )
