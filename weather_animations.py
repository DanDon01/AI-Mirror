"""Weather ambience for the AI-Mirror sky-stage.

The weather is an atmospheric scene rather than an icon beside a number.
It uses procedural soft-glow drawing only (no icon PNGs): a radiant rayed
sun, a calendar-aware moon with drifting stars, deep cloud banks, rain on
the glass, drifting snow, and storm lightning.

Design:
  - Occupies the upper half of the mirror and dissolves into the reflection.
  - The scene draws before text, so the information remains highly legible.
  - All motion is dt-based (px/sec) for frame-rate independence.

Class names / constructors are unchanged; each accepts wind_speed (m/s).
"""

import math
import random
import time

import pygame

from config import LAYOUT_V2
from effects_kit import glow_sprite, soft_blob, vertical_gradient, flash_alpha_envelope, jagged_bolt

BANNER_H = LAYOUT_V2.get('zones', {}).get('top_bar', {}).get('height', 95)
WINDY_THRESHOLD = 7.0    # m/s above which gust streaks appear

# Palette
PLATINUM = (236, 242, 248)
RAIN_TINT = (128, 194, 242)
SUN_TINT = (255, 209, 112)
MOON_TINT = (201, 222, 255)
CLOUD_TINT = (157, 187, 218)
SKY_TINT = (32, 93, 151)


def _effect_height(screen_height):
    """The ambient sky-stage for ordinary glances -- kept modest so the
    center stays clear day to day. Storm/etc. "moments" are the ones
    allowed to take over the full screen, briefly and rarely."""
    return max(BANNER_H * 3, min(int(screen_height * 0.20), 480))


def _glow_sprite(radius, color, core_alpha, core_frac=0.3):
    """Back-compat wrapper -- glow_sprite now lives in effects_kit so the
    Moments Director can reuse it for full-screen takeovers."""
    return glow_sprite(radius, color, core_alpha, core_frac)


def _make_cloud(width, alpha):
    """A real cloud puff texture, tinted and scaled (see effects_kit.py)."""
    return soft_blob(width, CLOUD_TINT, alpha)


class WeatherAnimation:
    """Base: top-band scene with a soft bottom fade-out."""

    def __init__(self, screen_width, screen_height, wind_speed=0.0):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.wind_speed = wind_speed or 0.0
        self.h = _effect_height(screen_height)
        self.fade_depth = int(self.h * 0.38)
        self._surf = pygame.Surface((screen_width, self.h), pygame.SRCALPHA)
        self._fade_mask = self._build_fade_mask()
        self._sky_wash = self._build_sky_wash()
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

    def _build_sky_wash(self):
        """A soft blue atmospheric wash behind the scene -- built once
        (the curve never changes frame to frame) rather than redrawn every
        frame, since it depends only on y, not time. Precomputing it once
        means a smooth per-row gradient costs nothing, instead of the
        visibly banded 8px steps a per-frame version would need to stay cheap."""
        wash = pygame.Surface((self.screen_width, self.h), pygame.SRCALPHA)
        for yy in range(self.h):
            progress = yy / max(self.h, 1)
            alpha = int(28 * (1.0 - progress) ** 1.8)
            pygame.draw.line(wash, (*SKY_TINT, alpha), (0, yy), (self.screen_width, yy))
        return wash

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
        # A very soft blue atmospheric wash gives the scene depth without
        # turning the mirror into an opaque TV panel (precomputed once).
        self._surf.blit(self._sky_wash, (0, 0))
        self._draw_scene(self._surf)
        self._draw_gusts(self._surf)
        self._surf.blit(self._fade_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        screen.blit(self._surf, (0, 0))


class _CloudLayerMixin:
    """Drifting cloud banks (parallax: far = slower + fainter). Clouds
    keep clear of the time digits at top-left."""

    def _init_clouds(self, count, alphas=(48, 70, 96)):
        self._cloud_band_x = int(self.screen_width * 0.18)
        # Clouds composite onto this shared, transparent layer (MAX blend,
        # same trick as the puffs within one cloud) before it's blitted
        # onto the scene once -- MAX-blending straight onto the scene
        # surface would corrupt colors, since that surface already has
        # the (non-transparent) sky wash under it.
        self._cloud_layer = pygame.Surface((self.screen_width, self.h), pygame.SRCALPHA)
        self._clouds = []
        for i in range(count):
            depth = i % len(alphas)
            # Sized off the band height, not raw screen width -- a cloud
            # that fit a tall 900px band reads as a solid box once the
            # band is a modest 480px; keep it proportionate instead.
            width = max(90, random.randint(int(self.h * 0.38), int(self.h * 0.68)) - depth * 18)
            surf = _make_cloud(width, alphas[depth])
            # Seed fully on-screen -- a cloud seeded already hanging off
            # the screen edge gets hard-clipped by the screen boundary
            # itself mid-shape, which reads as a rectangle, not a cloud.
            max_x = max(self._cloud_band_x, self.screen_width - surf.get_width())
            self._clouds.append({
                'surf': surf,
                'x': random.uniform(self._cloud_band_x, max_x),
                'y': random.uniform(10, max(10, self.h * 0.55 - surf.get_height())),
                'speed': (6.0 + depth * 8.0) * (1.0 + self.wind_speed * 0.07),
            })

    def _step_clouds(self, dt):
        for c in self._clouds:
            c['x'] += c['speed'] * dt
            if c['x'] > self.screen_width:
                # Re-enters fully off-screen-left, so it drifts smoothly
                # into view rather than popping in already clipped.
                c['x'] = self._cloud_band_x - c['surf'].get_width()
                c['y'] = random.uniform(10, max(10, self.h * 0.55 - c['surf'].get_height()))

    def _draw_clouds(self, surf):
        layer = self._cloud_layer
        layer.fill((0, 0, 0, 0))
        for c in self._clouds:
            layer.blit(c['surf'], (int(c['x']), int(c['y'])), special_flags=pygame.BLEND_RGBA_MAX)

        clip = surf.get_clip()
        surf.set_clip(pygame.Rect(self._cloud_band_x, 0,
                                  self.screen_width - self._cloud_band_x, self.h))
        surf.blit(layer, (0, 0))
        surf.set_clip(clip)


class SunAnimation(WeatherAnimation):
    """Radiant sun: big breathing glow with slowly rotating rays."""

    def __init__(self, screen_width, screen_height, wind_speed=0.0, sky_progress=0.5):
        super().__init__(screen_width, screen_height, wind_speed)
        # Follow a shallow daylight arc using the forecast's actual sunrise
        # and sunset. The slow motion is visible over a day, not a loop.
        progress = max(0.0, min(float(sky_progress), 1.0))
        self.cx = int(screen_width * (0.33 + progress * 0.42))
        self.cy = int(self.h * (0.64 - math.sin(progress * math.pi) * 0.40))
        r = int(self.h * 0.22)
        self._halo = _glow_sprite(int(r * 1.65), SUN_TINT, 96, core_frac=0.10)
        self._core = _glow_sprite(int(r * 0.62), SUN_TINT, 235, core_frac=0.50)
        self._rays = self._make_rays(int(self.h * 0.42))

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
            pygame.draw.line(surf, (*SUN_TINT, 92), (x1, y1), (x2, y2), 3)
        return surf

    def _draw_scene(self, surf):
        breath = 0.5 + 0.5 * math.sin(self.t * 0.5)

        # Rotating rays behind the glow
        rays = pygame.transform.rotate(self._rays, (self.t * 6) % 360)
        rr = rays.get_rect(center=(self.cx, self.cy))
        rscaled = rays.copy()
        rscaled.set_alpha(int(150 + 95 * breath))
        surf.blit(rscaled, rr)

        scale = 0.9 + breath * 0.2
        sz = int(self._halo.get_width() * scale)
        halo = pygame.transform.smoothscale(self._halo, (sz, sz))
        surf.blit(halo, (self.cx - sz // 2, self.cy - sz // 2))
        surf.blit(self._core, (self.cx - self._core.get_width() // 2,
                               self.cy - self._core.get_height() // 2))
        pygame.draw.circle(surf, (255, 248, 210, 235), (self.cx, self.cy), max(8, int(self.h * 0.028)))


class MoonAnimation(WeatherAnimation):
    """Crescent moon with a soft halo and drifting twinkling stars."""

    def __init__(self, screen_width, screen_height, cloudy=False, wind_speed=0.0,
                 phase=0.5, sky_progress=0.5):
        super().__init__(screen_width, screen_height, wind_speed)
        progress = max(0.0, min(float(sky_progress), 1.0))
        self.cx = int(screen_width * (0.35 + progress * 0.40))
        self.cy = int(self.h * (0.62 - math.sin(progress * math.pi) * 0.36))
        r = int(self.h * 0.13)
        self._halo = _glow_sprite(int(r * 2.4), MOON_TINT, 86, core_frac=0.16)
        self._crescent = self._make_moon(r, phase)
        self._stars = [
            {'x': random.uniform(self.screen_width * 0.3, self.screen_width),
             'y': random.uniform(8, self.h - self.fade_depth),
             'phase': random.uniform(0, math.tau),
             'rate': random.uniform(0.4, 1.2),
             'r': random.choice((1, 1, 1, 2, 2, 3))}
            for _ in range(54)
        ]
        self._cloud = _make_cloud(int(screen_width * 0.3), 30) if cloudy else None
        self._cloud_x = -float(screen_width)

    @staticmethod
    def _make_moon(r, phase):
        """Render the real calendar phase rather than a perpetual crescent."""
        size = r * 2 + 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        # Bright fraction rises from new -> full -> new.  The offset's side
        # changes after full moon, creating a simple waxing/waning cue.
        bright = 0.5 - 0.5 * math.cos(math.tau * phase)
        pygame.draw.circle(surf, (*MOON_TINT, int(45 + 125 * bright)), (r + 1, r + 1), r)
        if bright < 0.98:
            punch = pygame.Surface((size, size), pygame.SRCALPHA)
            offset = int((1.0 - 2.0 * bright) * r * (1 if phase < 0.5 else -1))
            pygame.draw.circle(punch, (255, 255, 255, 150),
                               (r + 1 + offset, r + 1 - int(r * 0.10)), r)
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
            a = int(42 + 150 * tw)
            pygame.draw.circle(surf, (*PLATINUM, a), (int(s['x']), int(s['y'])), s['r'])
            if s['r'] >= 2 and tw > 0.75:
                pygame.draw.line(surf, (*MOON_TINT, a // 2), (int(s['x']) - 4, int(s['y'])), (int(s['x']) + 4, int(s['y'])), 1)
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
        self._init_clouds(5 if partly else 8)
        self._sun_cx = int(screen_width * 0.62)
        self._sun_cy = int(self.h * 0.36)
        self._sun = _glow_sprite(int(self.h * 0.30), SUN_TINT, 100, core_frac=0.22) if partly else None

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
        self._init_clouds(6, alphas=(60, 84, 112))
        count = 150 if heavy else 95
        self._slant = min(0.08 + self.wind_speed * 0.04, 0.5)
        self._drops = [self._new_drop(seed=True) for _ in range(count)]
        self._splashes = []
        # Slow, heavy droplets in the foreground make rain feel like it is
        # running down the mirror glass rather than falling behind it.
        glass_count = 42 if heavy else 28
        self._glass_drops = [self._new_glass_drop(seed=True) for _ in range(glass_count)]
        # Preallocated once and cleared per frame -- a fresh full-screen
        # SRCALPHA surface every frame was a real Pi 5 frame-time cost.
        self._glass_surf = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)

    def _new_drop(self, seed=False):
        return {
            'x': random.uniform(0, self.screen_width),
            'y': random.uniform(0, self.h) if seed else random.uniform(-40, 0),
            'len': random.uniform(12, 26) * (1.3 if self.heavy else 1.0),
            'speed': random.uniform(620, 980) * (1.25 if self.heavy else 1.0),
            'alpha': random.randint(60, 140),
        }

    def _new_glass_drop(self, seed=False):
        return {
            'x': random.uniform(0, self.screen_width),
            'y': random.uniform(-40, self.screen_height) if seed else random.uniform(-120, -8),
            'len': random.uniform(22, 90) * (1.35 if self.heavy else 1.0),
            'speed': random.uniform(45, 140) * (1.35 if self.heavy else 1.0),
            'width': random.choice((1, 1, 1, 2, 2, 3)),
            'alpha': random.randint(48, 115),
            'wobble': random.uniform(0.8, 2.0),
            'phase': random.uniform(0, math.tau),
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
        for d in self._glass_drops:
            d['y'] += d['speed'] * dt
            d['x'] += math.sin(self.t * d['wobble'] + d['phase']) * 6 * dt
            if d['y'] - d['len'] > self.screen_height:
                d.update(self._new_glass_drop())

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

    def draw(self, screen):
        super().draw(screen)
        glass = self._glass_surf
        glass.fill((0, 0, 0, 0))
        for d in self._glass_drops:
            x = int(d['x'])
            y = int(d['y'])
            tail_y = int(y - d['len'])
            pygame.draw.line(glass, (*RAIN_TINT, max(12, d['alpha'] // 3)), (x, tail_y), (x, y), d['width'] + 2)
            pygame.draw.line(glass, (232, 246, 255, d['alpha']), (x, tail_y + 2), (x, y), d['width'])
            pygame.draw.circle(glass, (226, 244, 255, min(180, d['alpha'] + 35)), (x, y), max(1, d['width']))
        screen.blit(glass, (0, 0))


class StormAnimation(RainAnimation):
    """Heavy rain plus dramatic lightning: a full-band flash and a bolt."""

    def __init__(self, screen_width, screen_height, wind_speed=0.0):
        super().__init__(screen_width, screen_height, heavy=True, wind_speed=wind_speed)
        self._next_flash = self.t + random.uniform(2.5, 6.0)
        self._flash_started = None
        self._bolt = None

    def _make_bolt(self):
        return jagged_bolt(
            x_range=(self.screen_width * 0.35, self.screen_width * 0.9),
            y_range=(0, self.h * 0.8),
            width=self.screen_width,
            segment_height_range=(self.h * 0.10, self.h * 0.2),
        )

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
            level = flash_alpha_envelope(self.t - self._flash_started)
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
