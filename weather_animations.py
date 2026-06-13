"""Weather ambience for the AI-Mirror top zone.

The sky lives in a band at the top of the screen - taller than the clock
banner so it reads as a feature, not a hint - and dissolves before the
module columns below. Procedural soft-glow drawing only (no icon PNGs):
a radiant rayed sun, a crescent moon with drifting stars, layered cloud
banks, wind-slanted rain with splashes, drifting snow, and storm
lightning.

Design:
  - Confined to the top band (EFFECT_H), alpha-faded at the bottom so the
    mirror's centre stays clear.
  - Bolder than a hint but still behind the text: the clock/date draw on
    top afterwards.
  - All motion is dt-based (px/sec) for frame-rate independence.

Class names / constructors are unchanged; each accepts wind_speed (m/s).
"""

import math
import random
import time

import pygame

from config import LAYOUT_V2

BANNER_H = LAYOUT_V2.get('zones', {}).get('top_bar', {}).get('height', 95)
WINDY_THRESHOLD = 7.0    # m/s above which gust streaks appear

# Palette
PLATINUM = (228, 230, 235)
RAIN_TINT = (176, 198, 224)
SUN_TINT = (240, 216, 168)
MOON_TINT = (208, 216, 232)
CLOUD_TINT = (198, 202, 212)


def _effect_height(screen_height):
    """Top band height: a feature strip, ~3-4x the clock banner."""
    return max(BANNER_H * 2, min(int(screen_height * 0.16), 420))


def _glow_sprite(radius, color, core_alpha, core_frac=0.3):
    """Pre-render a smooth radial glow (built once, blitted per frame)."""
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
    """Pre-render a soft cloud from overlapping glow puffs (MAX-blended)."""
    height = int(width * 0.5)
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    puffs = random.randint(5, 8)
    for i in range(puffs):
        r = random.randint(int(width * 0.12), int(width * 0.20))
        puff = _glow_sprite(r, CLOUD_TINT, alpha, core_frac=0.5)
        px = int((i / max(puffs - 1, 1)) * (width - r * 2) + random.randint(-10, 10))
        py = random.randint(int(height * 0.2), height - r * 2)
        px = max(0, min(px, width - r * 2 - 2))
        py = max(0, min(py, height - r * 2 - 2))
        surf.blit(puff, (px, py), special_flags=pygame.BLEND_RGBA_MAX)
    return surf


class WeatherAnimation:
    """Base: top-band scene with a soft bottom fade-out."""

    def __init__(self, screen_width, screen_height, wind_speed=0.0):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.wind_speed = wind_speed or 0.0
        self.h = _effect_height(screen_height)
        self.fade_depth = int(self.h * 0.42)
        self._surf = pygame.Surface((screen_width, self.h), pygame.SRCALPHA)
        self._fade_mask = self._build_fade_mask()
        self._last = time.monotonic()
        self.t = 0.0

        self._gusts = []
        if self.wind_speed >= WINDY_THRESHOLD:
            self._gusts = [self._new_gust(seed_x=True) for _ in range(9)]

    def _build_fade_mask(self):
        mask = pygame.Surface((self.screen_width, self.h), pygame.SRCALPHA)
        mask.fill((255, 255, 255, 255))
        for i in range(self.fade_depth):
            a = int(255 * (1.0 - (i + 1) / self.fade_depth))
            y = self.h - self.fade_depth + i
            pygame.draw.line(mask, (255, 255, 255, a), (0, y), (self.screen_width, y))
        return mask

    def _new_gust(self, seed_x=False):
        return {
            'x': random.uniform(0, self.screen_width) if seed_x else -160.0,
            'y': random.uniform(10, self.h - self.fade_depth),
            'len': random.uniform(80, 180),
            'speed': random.uniform(140, 260),
            'alpha': random.randint(18, 40),
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
        self._surf.blit(self._fade_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        screen.blit(self._surf, (0, 0))


class _CloudLayerMixin:
    """Drifting cloud banks (parallax: far = slower + fainter). Clouds
    keep clear of the time digits at top-left."""

    def _init_clouds(self, count, alphas=(34, 48, 64)):
        self._cloud_band_x = int(self.screen_width * 0.28)
        self._clouds = []
        for i in range(count):
            depth = i % len(alphas)
            width = random.randint(int(self.screen_width * 0.18),
                                   int(self.screen_width * 0.34)) - depth * 24
            self._clouds.append({
                'surf': _make_cloud(max(120, width), alphas[depth]),
                'x': random.uniform(self._cloud_band_x, self.screen_width),
                'y': random.uniform(-20, self.h * 0.4),
                'speed': (5.0 + depth * 6.0) * (1.0 + self.wind_speed * 0.07),
            })

    def _step_clouds(self, dt):
        for c in self._clouds:
            c['x'] += c['speed'] * dt
            if c['x'] > self.screen_width:
                c['x'] = self._cloud_band_x - c['surf'].get_width()
                c['y'] = random.uniform(-20, self.h * 0.4)

    def _draw_clouds(self, surf):
        clip = surf.get_clip()
        surf.set_clip(pygame.Rect(self._cloud_band_x, 0,
                                  self.screen_width - self._cloud_band_x, self.h))
        for c in self._clouds:
            surf.blit(c['surf'], (int(c['x']), int(c['y'])))
        surf.set_clip(clip)


class SunAnimation(WeatherAnimation):
    """Radiant sun: big breathing glow with slowly rotating rays."""

    def __init__(self, screen_width, screen_height, wind_speed=0.0):
        super().__init__(screen_width, screen_height, wind_speed)
        self.cx = int(screen_width * 0.6)
        self.cy = int(self.h * 0.42)
        r = int(self.h * 0.34)
        self._halo = _glow_sprite(r, SUN_TINT, 40, core_frac=0.14)
        self._core = _glow_sprite(int(r * 0.34), SUN_TINT, 120, core_frac=0.55)
        self._rays = self._make_rays(int(self.h * 0.62))

    def _make_rays(self, reach):
        size = reach * 2 + 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        c = reach + 1
        for k in range(12):
            ang = (math.tau / 12) * k
            inner = reach * 0.42
            outer = reach * (0.78 + 0.22 * (k % 2))
            x1 = c + math.cos(ang) * inner
            y1 = c + math.sin(ang) * inner
            x2 = c + math.cos(ang) * outer
            y2 = c + math.sin(ang) * outer
            pygame.draw.line(surf, (*SUN_TINT, 34), (x1, y1), (x2, y2), 3)
        return surf

    def _draw_scene(self, surf):
        breath = 0.5 + 0.5 * math.sin(self.t * 0.5)

        # Rotating rays behind the glow
        rays = pygame.transform.rotate(self._rays, (self.t * 6) % 360)
        rr = rays.get_rect(center=(self.cx, self.cy))
        rscaled = rays.copy()
        rscaled.set_alpha(int(120 + 90 * breath))
        surf.blit(rscaled, rr)

        scale = 0.9 + breath * 0.2
        sz = int(self._halo.get_width() * scale)
        halo = pygame.transform.smoothscale(self._halo, (sz, sz))
        surf.blit(halo, (self.cx - sz // 2, self.cy - sz // 2))
        surf.blit(self._core, (self.cx - self._core.get_width() // 2,
                               self.cy - self._core.get_height() // 2))


class MoonAnimation(WeatherAnimation):
    """Crescent moon with a soft halo and drifting twinkling stars."""

    def __init__(self, screen_width, screen_height, cloudy=False, wind_speed=0.0):
        super().__init__(screen_width, screen_height, wind_speed)
        self.cx = int(screen_width * 0.6)
        self.cy = int(self.h * 0.4)
        r = int(self.h * 0.16)
        self._halo = _glow_sprite(int(r * 2.0), MOON_TINT, 26, core_frac=0.2)
        self._crescent = self._make_crescent(r)
        self._stars = [
            {'x': random.uniform(self.screen_width * 0.3, self.screen_width),
             'y': random.uniform(8, self.h - self.fade_depth),
             'phase': random.uniform(0, math.tau),
             'rate': random.uniform(0.4, 1.2),
             'r': random.choice((1, 1, 2))}
            for _ in range(14)
        ]
        self._cloud = _make_cloud(int(screen_width * 0.3), 30) if cloudy else None
        self._cloud_x = -float(screen_width)

    @staticmethod
    def _make_crescent(r):
        size = r * 2 + 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*MOON_TINT, 150), (r + 1, r + 1), r)
        punch = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(punch, (255, 255, 255, 150),
                           (r + 1 + int(r * 0.5), r + 1 - int(r * 0.18)), r)
        surf.blit(punch, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        return surf

    def _step(self, dt):
        for s in self._stars:
            s['x'] += (2.0 + self.wind_speed * 0.05) * dt
            if s['x'] > self.screen_width:
                s['x'] = self.screen_width * 0.3
        if self._cloud is not None:
            self._cloud_x += (8.0 + self.wind_speed * 0.1) * dt
            if self._cloud_x > self.screen_width:
                self._cloud_x = -self._cloud.get_width()

    def _draw_scene(self, surf):
        for s in self._stars:
            tw = 0.5 + 0.5 * math.sin(self.t * s['rate'] + s['phase'])
            a = int(30 + 90 * tw)
            pygame.draw.circle(surf, (*PLATINUM, a), (int(s['x']), int(s['y'])), s['r'])
        surf.blit(self._halo, (self.cx - self._halo.get_width() // 2,
                               self.cy - self._halo.get_height() // 2))
        surf.blit(self._crescent, (self.cx - self._crescent.get_width() // 2,
                                   self.cy - self._crescent.get_height() // 2))
        if self._cloud is not None:
            surf.blit(self._cloud, (int(self._cloud_x), int(self.h * 0.2)))


class CloudAnimation(_CloudLayerMixin, WeatherAnimation):
    """Layered drifting cloud banks; partly=True adds a sun glow behind."""

    def __init__(self, screen_width, screen_height, partly=False, wind_speed=0.0):
        super().__init__(screen_width, screen_height, wind_speed)
        self.partly = partly
        self._init_clouds(4 if partly else 7)
        self._sun_cx = int(screen_width * 0.62)
        self._sun_cy = int(self.h * 0.36)
        self._sun = _glow_sprite(int(self.h * 0.26), SUN_TINT, 60, core_frac=0.3) if partly else None

    def _step(self, dt):
        self._step_clouds(dt)

    def _draw_scene(self, surf):
        if self._sun is not None:
            breath = 0.5 + 0.5 * math.sin(self.t * 0.5)
            sz = int(self._sun.get_width() * (0.9 + breath * 0.18))
            sun = pygame.transform.smoothscale(self._sun, (sz, sz))
            surf.blit(sun, (self._sun_cx - sz // 2, self._sun_cy - sz // 2))
        self._draw_clouds(surf)


class RainAnimation(_CloudLayerMixin, WeatherAnimation):
    """Wind-slanted rain under a cloud bank, with splashes near the base."""

    def __init__(self, screen_width, screen_height, heavy=False, wind_speed=0.0):
        super().__init__(screen_width, screen_height, wind_speed)
        self.heavy = heavy
        self._init_clouds(5, alphas=(40, 56, 72))
        count = 150 if heavy else 95
        self._slant = min(0.08 + self.wind_speed * 0.04, 0.5)
        self._drops = [self._new_drop(seed=True) for _ in range(count)]
        self._splashes = []

    def _new_drop(self, seed=False):
        return {
            'x': random.uniform(0, self.screen_width),
            'y': random.uniform(0, self.h) if seed else random.uniform(-40, 0),
            'len': random.uniform(12, 26) * (1.3 if self.heavy else 1.0),
            'speed': random.uniform(620, 980) * (1.25 if self.heavy else 1.0),
            'alpha': random.randint(60, 140),
        }

    def _step(self, dt):
        self._step_clouds(dt)
        base = self.h - self.fade_depth * 0.5
        for d in self._drops:
            d['y'] += d['speed'] * dt
            d['x'] += d['speed'] * self._slant * dt
            if d['y'] > self.h:
                if random.random() < 0.25:
                    self._splashes.append(
                        {'x': d['x'], 'y': base, 'r': 1.0, 'a': 90})
                d.update(self._new_drop())
        for s in self._splashes:
            s['r'] += 36 * dt
            s['a'] -= 220 * dt
        self._splashes = [s for s in self._splashes if s['a'] > 0]

    def _draw_scene(self, surf):
        self._draw_clouds(surf)
        for d in self._drops:
            x2 = d['x'] - d['len'] * self._slant
            pygame.draw.line(
                surf, (*RAIN_TINT, d['alpha']),
                (int(x2), int(d['y'] - d['len'])),
                (int(d['x']), int(d['y'])),
                2 if self.heavy else 1,
            )
        for s in self._splashes:
            pygame.draw.circle(
                surf, (*RAIN_TINT, int(max(0, s['a']))),
                (int(s['x']), int(s['y'])), int(s['r']), 1)


class StormAnimation(RainAnimation):
    """Heavy rain plus dramatic lightning: a full-band flash and a bolt."""

    def __init__(self, screen_width, screen_height, wind_speed=0.0):
        super().__init__(screen_width, screen_height, heavy=True, wind_speed=wind_speed)
        self._next_flash = self.t + random.uniform(2.5, 6.0)
        self._flash_started = None
        self._bolt = None

    @staticmethod
    def _flash_alpha(age):
        if age < 0.08:
            return age / 0.08
        if age < 0.18:
            return 1.0 - (age - 0.08) / 0.10 * 0.6
        if age < 0.30:
            return 0.4 + (age - 0.18) / 0.12 * 0.5
        if age < 0.5:
            return 0.9 * (1.0 - (age - 0.30) / 0.20)
        return 0.0

    def _make_bolt(self):
        x = random.uniform(self.screen_width * 0.35, self.screen_width * 0.9)
        pts = [(x, 0)]
        y = 0
        while y < self.h * 0.8:
            y += random.uniform(self.h * 0.10, self.h * 0.2)
            x += random.uniform(-40, 40)
            pts.append((x, y))
        return pts

    def _step(self, dt):
        super()._step(dt)
        if self._flash_started is None and self.t >= self._next_flash:
            self._flash_started = self.t
            self._bolt = self._make_bolt()
        if self._flash_started is not None and self.t - self._flash_started > 0.5:
            self._flash_started = None
            self._bolt = None
            self._next_flash = self.t + random.uniform(2.5, 6.0)

    def _draw_scene(self, surf):
        if self._flash_started is not None:
            level = self._flash_alpha(self.t - self._flash_started)
            if level > 0:
                glow = pygame.Surface((self.screen_width, self.h), pygame.SRCALPHA)
                glow.fill((*PLATINUM, int(46 * level)))
                surf.blit(glow, (0, 0))
                if self._bolt and level > 0.4:
                    pygame.draw.lines(surf, (*PLATINUM, int(220 * level)),
                                      False, self._bolt, 2)
        super()._draw_scene(surf)


class SnowAnimation(_CloudLayerMixin, WeatherAnimation):
    """Soft flakes drifting down with a gentle sway; foreground flakes
    are larger for depth."""

    def __init__(self, screen_width, screen_height, wind_speed=0.0):
        super().__init__(screen_width, screen_height, wind_speed)
        self._init_clouds(3, alphas=(28, 40, 52))
        self._flakes = [self._new_flake(seed=True) for _ in range(95)]
        self._big = [_glow_sprite(r, PLATINUM, 150, core_frac=0.5) for r in (4, 6, 8)]

    def _new_flake(self, seed=False):
        depth = random.random()
        return {
            'x': random.uniform(0, self.screen_width),
            'y': random.uniform(0, self.h) if seed else random.uniform(-10, 0),
            'speed': 22 + depth * 70,
            'r': 1.0 + depth * 3.0,
            'alpha': int(70 + depth * 130),
            'phase': random.uniform(0, math.tau),
            'sway': 6 + depth * 16,
            'big': depth > 0.8,
        }

    def _step(self, dt):
        self._step_clouds(dt)
        for f in self._flakes:
            f['y'] += f['speed'] * dt
            f['x'] += self.wind_speed * 1.2 * dt
            if f['y'] > self.h or f['x'] > self.screen_width:
                f.update(self._new_flake())

    def _draw_scene(self, surf):
        self._draw_clouds(surf)
        for f in self._flakes:
            x = f['x'] + math.sin(self.t * 0.8 + f['phase']) * f['sway']
            if f['big']:
                spr = self._big[1]
                surf.blit(spr, (int(x) - spr.get_width() // 2,
                                int(f['y']) - spr.get_height() // 2))
            else:
                pygame.draw.circle(surf, (*PLATINUM, f['alpha']),
                                   (int(x), int(f['y'])), max(1, int(f['r'])))
