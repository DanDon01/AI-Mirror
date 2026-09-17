"""Vector condition glyphs for the ENVIRONMENT panel.

Line-art weather symbols drawn to match the rest of the habitat
instrumentation: outlined silhouettes with a faint interior wash rather
than filled cartoon shapes. Silhouettes are built once per size/colour
and cached; only the moving parts (falling drops, flakes, drifting
cloud, rotating sun rays) are drawn per frame.

The outline trick: a shape's union is rasterized twice, once at full
size and once eroded by the line thickness, and the eroded copy is
subtracted. That yields a single clean silhouette edge for overlapping
circles, which drawing each circle's own outline would not.
"""

import math

import pygame

_cache = {}


def _union_surfaces(w, h, shapes, color, thickness=2):
    """(outline, fill) surfaces for a union of circles and rects."""
    full = pygame.Surface((w, h), pygame.SRCALPHA)
    inner = pygame.Surface((w, h), pygame.SRCALPHA)
    for kind, args in shapes:
        if kind == 'circle':
            cx, cy, r = args
            pygame.draw.circle(full, (*color, 255), (int(cx), int(cy)), int(r))
            if r - thickness > 0:
                pygame.draw.circle(inner, (*color, 255), (int(cx), int(cy)),
                                   int(r - thickness))
        else:
            rx, ry, rw, rh = args
            pygame.draw.rect(full, (*color, 255), (int(rx), int(ry), int(rw), int(rh)))
            if rw > 2 * thickness and rh > 2 * thickness:
                pygame.draw.rect(inner, (*color, 255),
                                 (int(rx + thickness), int(ry),
                                  int(rw - 2 * thickness), int(rh - thickness)))
    outline = full.copy()
    outline.blit(inner, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
    return outline, full


def _cloud_surface(size, color, thickness=2):
    key = ('cloud', size, color, thickness)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    s = float(size)
    w, h = int(s), int(s * 0.66)
    shapes = [
        ('circle', (s * 0.30, s * 0.44, s * 0.155)),
        ('circle', (s * 0.50, s * 0.33, s * 0.205)),
        ('circle', (s * 0.72, s * 0.45, s * 0.145)),
        ('rect', (s * 0.30, s * 0.44, s * 0.42, s * 0.155)),
    ]
    outline, fill = _union_surfaces(w, h, shapes, color, thickness)
    fill.set_alpha(26)
    if len(_cache) > 48:
        _cache.clear()
    _cache[key] = (outline, fill)
    return outline, fill


def _draw_cloud(surf, cx, cy, size, color, drift=0.0, alpha=235):
    outline, fill = _cloud_surface(int(size), color)
    x = int(cx - outline.get_width() / 2 + drift)
    y = int(cy - outline.get_height() / 2)
    surf.blit(fill, (x, y))
    outline.set_alpha(alpha)
    surf.blit(outline, (x, y))
    return x, y, outline.get_width(), outline.get_height()


def sun(surf, cx, cy, size, color, t=0.0):
    r = size * 0.21
    spin = (t * 9.0) % 360
    for i in range(8):
        ang = math.radians(spin + i * 45)
        x0 = cx + math.cos(ang) * r * 1.42
        y0 = cy + math.sin(ang) * r * 1.42
        x1 = cx + math.cos(ang) * r * 1.92
        y1 = cy + math.sin(ang) * r * 1.92
        pygame.draw.line(surf, (*color, 190), (x0, y0), (x1, y1), 2)
    pygame.draw.circle(surf, (*color, 34), (int(cx), int(cy)), int(r))
    pygame.draw.circle(surf, (*color, 240), (int(cx), int(cy)), int(r), 2)


def moon(surf, cx, cy, size, color, t=0.0, phase=0.5):
    """Crescent shaped by the real moon phase (0/1 new, 0.5 full)."""
    r = int(size * 0.24)
    if r < 3:
        return
    pad = 2
    box = r * 2 + pad * 2
    key = ('moon', r, color, round(phase, 3))
    hit = _cache.get(key)
    if hit is None:
        disc = pygame.Surface((box, box), pygame.SRCALPHA)
        pygame.draw.circle(disc, (*color, 40), (r + pad, r + pad), r)
        pygame.draw.circle(disc, (*color, 245), (r + pad, r + pad), r, 2)
        illum = 1.0 - 2.0 * abs(phase - 0.5)
        if illum < 0.985:
            cut = pygame.Surface((box, box), pygame.SRCALPHA)
            offset = 2.0 * r * illum
            direction = -1 if phase < 0.5 else 1
            pygame.draw.circle(cut, (255, 255, 255, 255),
                               (int(r + pad + direction * offset), r + pad), r)
            disc.blit(cut, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        if len(_cache) > 48:
            _cache.clear()
        _cache[key] = disc
        hit = disc
    surf.blit(hit, (int(cx - box / 2), int(cy - box / 2)))


def clouds(surf, cx, cy, size, color, t=0.0):
    drift = math.sin(t * 0.5) * size * 0.02
    _draw_cloud(surf, cx, cy, size * 0.92, color, drift=drift)


def partly(surf, cx, cy, size, color, t=0.0, is_day=True, phase=0.5):
    if is_day:
        sun(surf, cx + size * 0.20, cy - size * 0.17, size * 0.72, color, t)
    else:
        moon(surf, cx + size * 0.20, cy - size * 0.17, size * 0.80, color, t, phase)
    drift = math.sin(t * 0.5) * size * 0.02
    _draw_cloud(surf, cx - size * 0.06, cy + size * 0.10, size * 0.80, color, drift=drift)


def _precip_column(t, count, period, spread):
    """Evenly spaced falling items with a stable per-item phase."""
    for i in range(count):
        yield i, ((t / period) + i / count) % 1.0, (i / max(1, count - 1) - 0.5) * spread


def rain(surf, cx, cy, size, color, t=0.0, heavy=False):
    _draw_cloud(surf, cx, cy - size * 0.10, size * 0.86, color)
    top = cy + size * 0.19
    span = size * 0.24
    count = 5 if heavy else 3
    for _, frac, dx in _precip_column(t, count, 0.75, size * 0.42):
        sx = cx + dx + frac * size * 0.05
        sy = top + frac * span
        fade = int(210 * (1.0 - abs(frac - 0.5) * 0.9))
        pygame.draw.line(surf, (*color, max(40, fade)),
                         (sx, sy), (sx - size * 0.03, sy + size * 0.09), 2)


def snow(surf, cx, cy, size, color, t=0.0):
    _draw_cloud(surf, cx, cy - size * 0.10, size * 0.86, color)
    top = cy + size * 0.19
    span = size * 0.24
    for i, frac, dx in _precip_column(t, 3, 2.2, size * 0.40):
        sx = cx + dx + math.sin(t * 1.5 + i) * size * 0.03
        sy = top + frac * span
        r = size * 0.035
        fade = int(215 * (1.0 - abs(frac - 0.5) * 0.8))
        for k in range(3):
            ang = math.radians(k * 60 + t * 20)
            pygame.draw.line(surf, (*color, max(45, fade)),
                             (sx - math.cos(ang) * r, sy - math.sin(ang) * r),
                             (sx + math.cos(ang) * r, sy + math.sin(ang) * r), 1)


def storm(surf, cx, cy, size, color, t=0.0):
    _draw_cloud(surf, cx, cy - size * 0.10, size * 0.86, color)
    flash = 0.45 + 0.55 * (math.sin(t * 5.0) > 0.86)
    bolt_color = (255, 226, 140)
    s = size
    pts = [
        (cx + s * 0.03, cy + s * 0.16), (cx - s * 0.10, cy + s * 0.30),
        (cx - s * 0.01, cy + s * 0.30), (cx - s * 0.06, cy + s * 0.44),
        (cx + s * 0.12, cy + s * 0.26), (cx + s * 0.02, cy + s * 0.26),
    ]
    pygame.draw.polygon(surf, (*bolt_color, int(90 + 150 * flash)), pts)


def fog(surf, cx, cy, size, color, t=0.0):
    _draw_cloud(surf, cx, cy - size * 0.14, size * 0.80, color, alpha=150)
    for i in range(3):
        yy = cy + size * (0.16 + i * 0.11)
        phase = math.sin(t * 0.8 + i * 1.1)
        half = size * (0.30 - i * 0.03)
        off = phase * size * 0.05
        pygame.draw.line(surf, (*color, 170 - i * 35),
                         (cx - half + off, yy), (cx + half + off, yy), 2)


def icon_droplet(surf, cx, cy, s, color):
    pygame.draw.polygon(surf, (*color, 200), [
        (cx, cy - s), (cx + s * 0.72, cy + s * 0.25), (cx, cy + s * 0.95),
        (cx - s * 0.72, cy + s * 0.25)], 1)


def icon_wind(surf, cx, cy, s, color):
    for i, (yy, ww) in enumerate(((-0.55, 0.95), (0.05, 1.15), (0.62, 0.75))):
        y = cy + s * yy
        pygame.draw.line(surf, (*color, 200),
                         (cx - s * 0.85, y), (cx + s * ww - s * 0.85, y), 1)


def icon_gauge(surf, cx, cy, s, color):
    pygame.draw.circle(surf, (*color, 200), (int(cx), int(cy)), int(s * 0.9), 1)
    ang = math.radians(-125)
    pygame.draw.line(surf, (*color, 220), (cx, cy),
                     (cx + math.cos(ang) * s * 0.6, cy + math.sin(ang) * s * 0.6), 1)


def icon_eye(surf, cx, cy, s, color):
    pygame.draw.lines(surf, (*color, 200), False, [
        (cx - s, cy), (cx - s * 0.45, cy - s * 0.62), (cx + s * 0.45, cy - s * 0.62),
        (cx + s, cy)], 1)
    pygame.draw.lines(surf, (*color, 200), False, [
        (cx - s, cy), (cx - s * 0.45, cy + s * 0.62), (cx + s * 0.45, cy + s * 0.62),
        (cx + s, cy)], 1)
    pygame.draw.circle(surf, (*color, 220), (int(cx), int(cy)), max(1, int(s * 0.3)), 1)


def icon_uv(surf, cx, cy, s, color):
    pygame.draw.circle(surf, (*color, 210), (int(cx), int(cy)), int(s * 0.42), 1)
    for i in range(6):
        ang = math.radians(i * 60)
        pygame.draw.line(surf, (*color, 170),
                         (cx + math.cos(ang) * s * 0.62, cy + math.sin(ang) * s * 0.62),
                         (cx + math.cos(ang) * s * 0.92, cy + math.sin(ang) * s * 0.92), 1)


def wind_compass(surf, cx, cy, r, color, deg=None):
    """A real compass rose with the needle on the reported bearing."""
    pygame.draw.circle(surf, (*color, 55), (int(cx), int(cy)), int(r), 1)
    for i in range(16):
        ang = math.radians(i * 22.5 - 90)
        major = (i % 4 == 0)
        inner = r - (6 if major else 3)
        pygame.draw.line(surf, (*color, 130 if major else 55),
                         (cx + math.cos(ang) * inner, cy + math.sin(ang) * inner),
                         (cx + math.cos(ang) * r, cy + math.sin(ang) * r), 1)
    if deg is None:
        return
    # Meteorological bearing is the direction the wind blows FROM.
    ang = math.radians(float(deg) - 90)
    tip = (cx + math.cos(ang) * r * 0.66, cy + math.sin(ang) * r * 0.66)
    back = math.radians(float(deg) + 90)
    tail = (cx + math.cos(back) * r * 0.30, cy + math.sin(back) * r * 0.30)
    left = math.radians(float(deg) + 150)
    right = math.radians(float(deg) - 210)
    pygame.draw.polygon(surf, (*color, 235), [
        tip,
        (cx + math.cos(left) * r * 0.26, cy + math.sin(left) * r * 0.26),
        tail,
        (cx + math.cos(right) * r * 0.26, cy + math.sin(right) * r * 0.26),
    ])


def compass_label(deg):
    if deg is None:
        return ""
    points = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
              "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
    return points[int((float(deg) % 360) / 22.5 + 0.5) % 16]


def code_condition(code):
    """WMO code -> (condition, description) for the outlook glyphs."""
    code = int(code or 0)
    if code <= 1:
        return 'clear', 'clear'
    if code <= 2:
        return 'clouds', 'partly cloudy'
    if code == 3:
        return 'clouds', 'overcast'
    if code in (45, 48):
        return 'fog', 'fog'
    if 51 <= code <= 67 or 80 <= code <= 82:
        return 'rain', 'heavy rain' if code in (65, 82) else 'rain'
    if 71 <= code <= 77 or code in (85, 86):
        return 'snow', 'snow'
    if code >= 95:
        return 'thunderstorm', 'thunderstorm'
    return 'clouds', 'cloudy'


_DISPATCH = {
    'clear': None,          # handled by day/night branch
    'clouds': clouds,
    'rain': rain,
    'drizzle': rain,
    'snow': snow,
    'thunderstorm': storm,
    'fog': fog,
    'mist': fog,
    'haze': fog,
}


def draw_condition(surf, cx, cy, size, color, condition, description="",
                   is_day=True, t=0.0, phase=0.5):
    """Draw the glyph for a normalized condition string."""
    cond = (condition or "").lower()
    desc = (description or "").lower()

    if 'clear' in cond:
        if is_day:
            sun(surf, cx, cy, size, color, t)
        else:
            moon(surf, cx, cy, size, color, t, phase)
        return
    if 'cloud' in cond:
        if 'partly' in desc or 'mainly clear' in desc or 'broken' in desc:
            partly(surf, cx, cy, size, color, t, is_day, phase)
        elif 'fog' in desc or 'mist' in desc:
            fog(surf, cx, cy, size, color, t)
        else:
            clouds(surf, cx, cy, size, color, t)
        return
    if 'rain' in cond or 'drizzle' in cond:
        rain(surf, cx, cy, size, color, t, heavy='heavy' in desc)
        return

    fn = _DISPATCH.get(cond)
    if fn is not None:
        fn(surf, cx, cy, size, color, t)
    else:
        clouds(surf, cx, cy, size, color, t)
