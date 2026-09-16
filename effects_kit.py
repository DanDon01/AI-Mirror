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
import random

import pygame


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


def soft_blob(width, color, alpha, puff_range=(5, 8), height_ratio=0.5):
    """Pre-render a soft lumpy blob from overlapping glow puffs
    (MAX-blended) -- clouds, smoke, fog, or any organic glow shape."""
    height = max(1, int(width * height_ratio))
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    puffs = random.randint(*puff_range)
    for i in range(puffs):
        r = max(1, random.randint(int(width * 0.12), int(width * 0.20)))
        puff = glow_sprite(r, color, alpha, core_frac=0.5)
        px = int((i / max(puffs - 1, 1)) * (width - r * 2) + random.randint(-10, 10))
        py = random.randint(int(height * 0.2), max(1, height - r * 2))
        px = max(0, min(px, width - r * 2 - 2))
        py = max(0, min(py, height - r * 2 - 2))
        surf.blit(puff, (px, py), special_flags=pygame.BLEND_RGBA_MAX)
    return surf


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
