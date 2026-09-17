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


def safe_smoothscale(surf, size):
    """pygame.transform.smoothscale segfaults -- crashes the whole
    process, not a catchable exception -- when the source surface has a
    zero width or height (e.g. font.render('') on a missing/empty ctx
    value). Falls back to a plain (non-filtered) scale for a degenerate
    source, and clamps the target size to at least 1x1 either way."""
    w, h = max(1, size[0]), max(1, size[1])
    if surf.get_width() <= 0 or surf.get_height() <= 0:
        return pygame.transform.scale(surf, (w, h))
    return pygame.transform.smoothscale(surf, (w, h))


_glow_cache = {}


def glow_sprite(radius, color, core_alpha, core_frac=0.3):
    """A smooth radial glow, cached by its exact parameters -- callers
    that rebuild "the same" glow every frame (e.g. a hero-number glow
    whose intensity tracks a slowly-changing day/night curve) get a
    cache hit instead of repaying the render cost every frame."""
    key = (radius, color, core_alpha, core_frac)
    cached = _glow_cache.get(key)
    if cached is not None:
        return cached
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
    if len(_glow_cache) > 512:
        _glow_cache.clear()
    _glow_cache[key] = surf
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


def draw_dial_gauge(screen, cx, cy, radius, value, vmin, vmax, zones,
                    thickness=10, start_deg=125, end_deg=415, needle_color=None):
    """A speedometer-style arc dial: a colored-zone track plus a bright
    needle marking the current value. Live-drawn each frame (small line
    segments, same cheap pattern as the portal ring's ticks) rather than
    a pre-rendered bitmap, since `value` changes.

    zones: [(upper_bound, color), ...] ascending -- the zone a given point
    on the arc falls into is whichever is the first zone whose upper_bound
    it's under. The last zone's color covers everything above the
    second-to-last bound.
    """
    span = end_deg - start_deg
    steps = max(24, int(span / 3))
    frac_range = max(1e-6, vmax - vmin)

    def zone_color(v):
        for bound, color in zones:
            if v <= bound:
                return color
        return zones[-1][1] if zones else (200, 200, 200)

    for i in range(steps):
        t0 = i / steps
        t1 = (i + 1) / steps
        v_mid = vmin + ((t0 + t1) / 2) * frac_range
        ang0 = math.radians(start_deg + t0 * span)
        ang1 = math.radians(start_deg + t1 * span)
        x0, y0 = cx + math.cos(ang0) * radius, cy + math.sin(ang0) * radius
        x1, y1 = cx + math.cos(ang1) * radius, cy + math.sin(ang1) * radius
        pygame.draw.line(screen, (*zone_color(v_mid), 235), (x0, y0), (x1, y1), thickness)
        # A small round joint between segments -- pygame line segments
        # have square ends, so a jointless polyline at this thickness
        # shows visible notches at each seam.
        pygame.draw.circle(screen, (*zone_color(v_mid), 235), (int(x1), int(y1)), thickness // 2)

    # Rounded end caps at the very start/end of the track.
    a0 = math.radians(start_deg)
    a1 = math.radians(end_deg)
    p0 = (cx + math.cos(a0) * radius, cy + math.sin(a0) * radius)
    p1 = (cx + math.cos(a1) * radius, cy + math.sin(a1) * radius)
    pygame.draw.circle(screen, (*zone_color(vmin), 235), (int(p0[0]), int(p0[1])), thickness // 2)
    pygame.draw.circle(screen, (*zone_color(vmax), 235), (int(p1[0]), int(p1[1])), thickness // 2)

    # Needle: a bright line from center out past the track, plus a small hub.
    t = max(0.0, min(1.0, (value - vmin) / frac_range))
    ang = math.radians(start_deg + t * span)
    color = needle_color or (255, 255, 255)
    nx = cx + math.cos(ang) * (radius + thickness * 0.9)
    ny = cy + math.sin(ang) * (radius + thickness * 0.9)
    ix = cx + math.cos(ang) * (radius * 0.25)
    iy = cy + math.sin(ang) * (radius * 0.25)
    pygame.draw.line(screen, (*color, 255), (ix, iy), (nx, ny), 3)
    pygame.draw.circle(screen, (*color, 255), (int(cx), int(cy)), 5)


def draw_sparkline(screen, x, y, w, h, values, color, alpha=220, vmin=None, vmax=None):
    """A minimal trend line -- real data (however coarse) communicates a
    lot more than a single number, and costs almost nothing to draw."""
    if not values or len(values) < 2:
        return
    lo = vmin if vmin is not None else min(values)
    hi = vmax if vmax is not None else max(values)
    span = max(1e-6, hi - lo)
    n = len(values)
    pts = [
        (x + (i / (n - 1)) * w, y + h - ((v - lo) / span) * h)
        for i, v in enumerate(values)
    ]
    pygame.draw.lines(screen, (*color, alpha), False, pts, 2)
    for px, py in (pts[-1],):
        pygame.draw.circle(screen, (*color, 255), (int(px), int(py)), 3)


def draw_panel_frame(screen, x, y, w, h, color, alpha=70, corner_len=16):
    """A thin glowing card border -- not a filled background (the mirror
    stays see-through, no opaque boxes), just enough structure that a
    module reads as a panel instead of text floating with no edge. A
    faint full rounded-rect outline plus brighter corner accents, the
    same "HUD panel" language as the portal ring's screen-corner brackets."""
    if w <= 0 or h <= 0:
        return
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(surf, (*color, alpha), surf.get_rect(), width=1, border_radius=10)
    screen.blit(surf, (x, y))

    bright = min(255, alpha + 110)
    L = min(corner_len, w // 3, h // 3)
    for (px, py), (dx, dy) in (
        ((x, y), (1, 1)), ((x + w, y), (-1, 1)),
        ((x, y + h), (1, -1)), ((x + w, y + h), (-1, -1)),
    ):
        pygame.draw.line(screen, (*color, bright), (px, py), (px + L * dx, py), 2)
        pygame.draw.line(screen, (*color, bright), (px, py), (px, py + L * dy), 2)


def chamfer_points(x, y, w, h, cut):
    """The corner-cut octagon path used by every console panel in the
    biometric monitor -- an angled corner reads as machined hardware where
    a rounded rect reads as a web card."""
    return [
        (x + cut, y), (x + w - cut, y), (x + w, y + cut),
        (x + w, y + h - cut), (x + w - cut, y + h), (x + cut, y + h),
        (x, y + h - cut), (x, y + cut),
    ]


def draw_chamfer_frame(screen, x, y, w, h, color, alpha=60, cut=9,
                       corner_alpha=190, corner_len=14):
    """A chamfered instrument-panel outline: faint full border plus bright
    stubs running off each cut corner. Outline only -- the mirror stays
    see-through, so nothing ever gets a filled background."""
    if w <= 4 or h <= 4:
        return
    cut = int(max(3, min(cut, w // 3, h // 3)))
    surf = pygame.Surface((w + 1, h + 1), pygame.SRCALPHA)
    pygame.draw.polygon(surf, (*color, alpha), chamfer_points(0, 0, w, h, cut), 1)
    screen.blit(surf, (x, y))

    L = int(max(4, min(corner_len, w // 4, h // 4)))
    bright = (*color, corner_alpha)
    for (cx0, cy0), (dx, dy) in (
        ((x + cut, y), (1, 0)), ((x + w - cut, y), (-1, 0)),
        ((x + cut, y + h), (1, 0)), ((x + w - cut, y + h), (-1, 0)),
        ((x, y + cut), (0, 1)), ((x, y + h - cut), (0, -1)),
        ((x + w, y + cut), (0, 1)), ((x + w, y + h - cut), (0, -1)),
    ):
        pygame.draw.line(screen, bright, (cx0, cy0),
                         (cx0 + L * dx, cy0 + L * dy), 1)


def draw_segmented_ring(screen, cx, cy, radius, fraction, color, segments=36,
                        thickness=7, gap_deg=2.4, track_alpha=42, lit_alpha=240,
                        start_deg=-90, end_deg=270):
    """A radial gauge built from discrete lit segments rather than one
    smooth arc -- the difference between an instrument and a progress bar.
    The segment straddling the current value is partially lit so the gauge
    still reads continuously."""
    fraction = max(0.0, min(1.0, fraction))
    span = end_deg - start_deg
    seg_span = span / max(1, segments)
    lit_edge = fraction * segments
    sub = max(2, int(abs(seg_span) / 4))

    for i in range(segments):
        if i + 1 <= lit_edge:
            alpha = lit_alpha
        elif i < lit_edge:
            alpha = int(track_alpha + (lit_alpha - track_alpha) * (lit_edge - i))
        else:
            alpha = track_alpha
        a_start = start_deg + i * seg_span + gap_deg / 2.0
        a_end = start_deg + (i + 1) * seg_span - gap_deg / 2.0
        prev = None
        for s in range(sub + 1):
            ang = math.radians(a_start + (a_end - a_start) * (s / sub))
            pt = (cx + math.cos(ang) * radius, cy + math.sin(ang) * radius)
            if prev is not None:
                pygame.draw.line(screen, (*color, alpha), prev, pt, thickness)
            prev = pt


def draw_arc_segment(screen, cx, cy, radius, start_deg, end_deg, color,
                     thickness=2, alpha=200):
    """A plain bright arc -- the slow-rotating ambient accents flanking the
    body scan, and the sweep hands on the readiness gauges."""
    span = end_deg - start_deg
    steps = max(3, int(abs(span) / 4))
    prev = None
    for i in range(steps + 1):
        ang = math.radians(start_deg + span * (i / steps))
        pt = (cx + math.cos(ang) * radius, cy + math.sin(ang) * radius)
        if prev is not None:
            pygame.draw.line(screen, (*color, alpha), prev, pt, thickness)
        prev = pt


def draw_tick_scale(screen, x, y, w, color, count=20, major_every=5,
                    minor_h=3, major_h=6, alpha=110):
    """A measurement scale under a readout. Pure instrument grammar: it
    carries no data, it tells the eye this is a calibrated device."""
    if w <= 0 or count <= 0:
        return
    for i in range(count + 1):
        tx = x + (w * i / count)
        h = major_h if (i % major_every == 0) else minor_h
        a = alpha if (i % major_every == 0) else int(alpha * 0.55)
        pygame.draw.line(screen, (*color, a), (tx, y), (tx, y + h), 1)


def draw_flare(screen, x, y, w, h, flare_alpha, color=(196, 174, 128)):
    """A brief soft highlight behind a rect whose data just changed --
    the "loud change" half of "calm baseline, loud change" (see
    module_base.SurfaceCache.flare_alpha, which supplies flare_alpha).
    No-op when flare_alpha is 0, so calling this every frame for every
    module is cheap."""
    if flare_alpha <= 0:
        return
    radius = max(4, int(max(w, h) * 0.6))
    glow = glow_sprite(radius, color, int(flare_alpha * 0.55), core_frac=0.2)
    cx, cy = x + w // 2, y + h // 2
    screen.blit(glow, (cx - glow.get_width() // 2, cy - glow.get_height() // 2))


def vertical_gradient(width, height, top_color, bottom_color, top_alpha=255, bottom_alpha=255):
    """Precompute a linear top-to-bottom gradient (build once)."""
    surf = pygame.Surface((width, max(1, height)), pygame.SRCALPHA)
    for y in range(height):
        t = y / max(height - 1, 1)
        color = tuple(int(top_color[i] + (bottom_color[i] - top_color[i]) * t) for i in range(3))
        alpha = int(top_alpha + (bottom_alpha - top_alpha) * t)
        pygame.draw.line(surf, (*color, alpha), (0, y), (width, y))
    return surf


def draw_trace_progress(screen, x, y, w, h, fraction, color, thickness=3, alpha=230):
    """Trace a coloured line clockwise around a rectangle's outline as
    progress grows (top -> right -> bottom -> left), closing into a full
    frame at 1.0. The house progress idiom (originally Fitbit's step
    frame) -- generalized so any module can show a 0-1 value this way
    instead of a plain filled bar."""
    fraction = max(0.0, min(fraction, 1.0))
    if fraction <= 0:
        return
    t = thickness
    surf = pygame.Surface((w + t, h + t), pygame.SRCALPHA)
    inset = t / 2.0
    x0, y0 = inset, inset
    x1, y1 = w - inset, h - inset

    line_color = (*color, alpha)
    perim = 2 * ((x1 - x0) + (y1 - y0))
    remaining = fraction * perim
    edges = [
        ((x0, y0), (x1, y0)),
        ((x1, y0), (x1, y1)),
        ((x1, y1), (x0, y1)),
        ((x0, y1), (x0, y0)),
    ]
    for (ax, ay), (bx, by) in edges:
        if remaining <= 0:
            break
        seg = math.hypot(bx - ax, by - ay)
        if seg <= 0:
            continue
        if remaining >= seg:
            pygame.draw.line(surf, line_color, (ax, ay), (bx, by), t)
            remaining -= seg
        else:
            f = remaining / seg
            pygame.draw.line(
                surf, line_color, (ax, ay),
                (ax + (bx - ax) * f, ay + (by - ay) * f), t,
            )
            remaining = 0
    screen.blit(surf, (x, y))


def draw_hero_glow(screen, text_surf, x, y, color, intensity=1.0):
    """A soft ambient glow behind a hero number (clock time, temperature)
    -- built fresh each call but cheap (one glow_sprite at a size tied to
    the text), and scaled by `intensity` so callers can dim it in bright
    daylight and let it bloom at night."""
    if intensity <= 0.01:
        return
    radius = max(4, int(max(text_surf.get_width(), text_surf.get_height()) * 0.42))
    peak = int(70 * intensity)
    glow = glow_sprite(radius, color, peak, core_frac=0.35)
    cx = x + text_surf.get_width() // 2
    cy = y + text_surf.get_height() // 2
    screen.blit(glow, (cx - glow.get_width() // 2, cy - glow.get_height() // 2))


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
