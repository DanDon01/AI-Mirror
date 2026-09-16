"""Shared visual-effects primitives for AI-Mirror.

Precompute-once, blit-cheap building blocks originally grown inside
weather_animations.py -- soft radial glows, puffy blob shapes, gradient
washes, and lightning-style flash/bolt curves. Anything that draws a
theatrical "moment" (event_director.py) reuses these instead of
reinventing them per effect, and anything expensive is built once and
cached rather than rebuilt every frame -- the discipline that keeps
30 FPS affordable on a Raspberry Pi 5.
"""

import math
import os
import random

import numpy as np
import pygame
from PIL import Image


def glow_sprite(radius, color, core_alpha, core_frac=0.3):
    """Pre-render a smooth radial glow (build once, blit many times)."""
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


_CLOUD_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'clouds')
_cloud_sources = None


def _load_cloud_sources():
    """Real cloud puff textures (CC0, Kenney "Smoke Particles" pack --
    see assets/clouds/LICENSE.txt), loaded once and reused. Procedurally
    stamped circles or blurred ellipses read as computer graphics no
    matter how much you tune them; a hand-painted irregular puff with
    real detail in its silhouette reads as an actual cloud."""
    global _cloud_sources
    if _cloud_sources is None:
        _cloud_sources = []
        for fname in sorted(os.listdir(_CLOUD_ASSET_DIR)):
            if fname.lower().endswith('.png'):
                path = os.path.join(_CLOUD_ASSET_DIR, fname)
                _cloud_sources.append(Image.open(path).convert('RGBA'))
    return _cloud_sources


def soft_blob(width, color, alpha, height_ratio=0.42, seed=None):
    """A real cloud texture, tinted and scaled -- clouds, smoke, fog, or
    any organic glow shape. Built once per shape (not per frame); the
    caller keeps the returned Surface for as long as that shape is on
    screen."""
    sources = _load_cloud_sources()
    rng = random.Random(seed)
    src = rng.choice(sources)

    height = max(1, int(width * height_ratio))
    resized = src.resize((width, height), Image.LANCZOS)

    a = np.asarray(resized.split()[-1], dtype=np.float32) / 255.0
    rgba = np.empty((height, width, 4), dtype=np.uint8)
    rgba[..., 0] = color[0]
    rgba[..., 1] = color[1]
    rgba[..., 2] = color[2]
    rgba[..., 3] = (a * alpha).astype(np.uint8)
    return pygame.image.frombuffer(rgba.tobytes(), (width, height), 'RGBA')


def vertical_gradient(width, height, top_color, bottom_color, top_alpha=255, bottom_alpha=255):
    """Precompute a linear top-to-bottom gradient (build once)."""
    surf = pygame.Surface((width, max(1, height)), pygame.SRCALPHA)
    for y in range(height):
        t = y / max(height - 1, 1)
        color = tuple(int(top_color[i] + (bottom_color[i] - top_color[i]) * t) for i in range(3))
        alpha = int(top_alpha + (bottom_alpha - top_alpha) * t)
        pygame.draw.line(surf, (*color, alpha), (0, y), (width, y))
    return surf


def flash_alpha_envelope(age):
    """Camera-flash-style alpha curve over elapsed seconds: quick punch,
    brief settle, fade out. Used for lightning and any other "bang" moment."""
    if age < 0.08:
        return age / 0.08
    if age < 0.18:
        return 1.0 - (age - 0.08) / 0.10 * 0.6
    if age < 0.30:
        return 0.4 + (age - 0.18) / 0.12 * 0.5
    if age < 0.5:
        return 0.9 * (1.0 - (age - 0.30) / 0.20)
    return 0.0


def jagged_bolt(x_range, y_range, width, segment_height_range, jitter_x=40):
    """A random jagged polyline (e.g. a lightning bolt) from y_range[0]
    down to y_range[1], clamped to stay on screen."""
    x = random.uniform(*x_range)
    y0, y1 = y_range
    pts = [(x, y0)]
    y = y0
    while y < y1:
        y += random.uniform(*segment_height_range)
        x += random.uniform(-jitter_x, jitter_x)
        x = max(0, min(x, width))
        pts.append((x, y))
    return pts


def ease_out_cubic(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_out_back(t, overshoot=1.70158):
    """A little "pop" past 1.0 before settling -- good for arrivals
    (banners, notifications) that should feel snappy rather than gentle."""
    t = max(0.0, min(1.0, t)) - 1
    return 1 + (overshoot + 1) * t ** 3 + overshoot * t ** 2
