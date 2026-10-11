"""Anatomical scan figure for the biometric monitor.

A hand-authored vector human, drawn as a translucent body with an
internal skeletal/organ trace and a scanning band sweeping down it -- the
centrepiece of fitbit_module's BIOMETRIC MONITOR composition.

The outline lives here as normalized coordinates (x is the offset from the
body centreline, y runs 0 at the crown to 1 at the soles, both in units of
total figure height) so the same figure renders correctly at any size. The
body is rasterized once per size/colour into a cached Surface; per frame
the module only blits that surface plus a thin bright band, which is what
keeps a detailed figure affordable at 30 FPS on a Pi 5.
"""

import math

import pygame

# Right-hand half of the silhouette, crown-to-crotch. The left half is
# mirrored from this at build time, so the figure is symmetrical by
# construction.
_HALF_OUTLINE = [
    (0.042, 0.118),  # neck base
    (0.075, 0.140),  # trapezius
    (0.140, 0.162),  # shoulder
    (0.178, 0.190),  # deltoid
    (0.192, 0.240),  # upper arm
    (0.196, 0.300),
    (0.200, 0.345),  # elbow
    (0.208, 0.400),  # forearm
    (0.216, 0.450),  # wrist
    (0.228, 0.492),  # hand
    (0.214, 0.520),  # fingertips
    (0.186, 0.512),
    (0.176, 0.452),  # wrist, inner
    (0.166, 0.400),
    (0.154, 0.345),  # elbow, inner
    (0.142, 0.285),
    (0.128, 0.226),  # armpit
    (0.112, 0.238),  # latissimus
    (0.103, 0.290),  # ribcage
    (0.086, 0.340),  # waist
    (0.092, 0.380),
    (0.112, 0.420),  # hip
    (0.116, 0.452),
    (0.106, 0.520),  # thigh
    (0.094, 0.590),
    (0.086, 0.640),  # knee
    (0.080, 0.690),
    (0.086, 0.730),  # calf
    (0.066, 0.815),
    (0.060, 0.878),  # ankle
    (0.082, 0.900),  # toe
    (0.020, 0.902),
    (0.024, 0.850),  # ankle, inner
    (0.032, 0.760),
    (0.040, 0.680),  # knee, inner
    (0.048, 0.590),
    (0.044, 0.500),
    (0.000, 0.468),  # crotch, centreline
]

_HEAD = (0.0, 0.058, 0.062, 0.073)  # cx, cy, rx, ry

# Chest node (heart), in the same normalized space. Sits just left of the
# centreline as seen by the viewer, matching how a scan diagram is drawn.
HEART_NODE = (-0.026, 0.252)
WRIST_NODE = (0.205, 0.468)
HEAD_NODE = (0.0, 0.058)


def _outline_points():
    mirrored = [(-x, y) for (x, y) in reversed(_HALF_OUTLINE[:-1])]
    return _HALF_OUTLINE + mirrored


def _internals():
    """Skeletal/organ trace lines as normalized polylines."""
    lines = []

    # Spine with vertebra ticks
    lines.append([(0.0, 0.132), (0.0, 0.300), (0.004, 0.380), (0.0, 0.432)])
    for i in range(9):
        y = 0.150 + i * 0.031
        lines.append([(-0.011, y), (0.011, y)])

    # Clavicle
    lines.append([(-0.092, 0.158), (-0.030, 0.150), (0.030, 0.150), (0.092, 0.158)])

    # Ribcage: paired arcs sweeping down and out from the spine
    for i in range(5):
        y = 0.192 + i * 0.030
        drop = 0.016 + i * 0.004
        reach = 0.084 - abs(i - 2) * 0.006
        for side in (-1, 1):
            lines.append([
                (side * 0.014, y),
                (side * reach * 0.55, y + drop * 0.55),
                (side * reach, y + drop),
            ])

    # Pelvis
    lines.append([
        (-0.086, 0.412), (-0.050, 0.452), (0.0, 0.462),
        (0.050, 0.452), (0.086, 0.412),
    ])

    # Arm bones
    for side in (-1, 1):
        lines.append([
            (side * 0.150, 0.186), (side * 0.172, 0.268),
            (side * 0.178, 0.344), (side * 0.196, 0.470),
        ])

    # Leg bones
    for side in (-1, 1):
        lines.append([
            (side * 0.058, 0.452), (side * 0.072, 0.560),
            (side * 0.064, 0.645), (side * 0.054, 0.760),
            (side * 0.044, 0.872),
        ])

    # Shoulder / hip joint marks
    return lines


_JOINTS = [
    (-0.152, 0.186), (0.152, 0.186),
    (-0.178, 0.344), (0.178, 0.344),
    (-0.058, 0.452), (0.058, 0.452),
    (-0.070, 0.645), (0.070, 0.645),
]

_cache = {}


def _build(w, h, color, intensity):
    """Rasterize the figure once for a given size/colour/brightness."""
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    cx = w / 2.0

    def pt(nx, ny):
        return (cx + nx * h, ny * h)

    fill_a = int(34 * intensity)
    line_a = int(120 * intensity)
    inner_a = int(108 * intensity)
    edge_a = int(235 * intensity)

    outline = [pt(x, y) for (x, y) in _outline_points()]
    pygame.draw.polygon(surf, (*color, fill_a), outline)

    hx, hy, hrx, hry = _HEAD
    head_rect = pygame.Rect(0, 0, int(hrx * 2 * h), int(hry * 2 * h))
    head_rect.center = pt(hx, hy)
    pygame.draw.ellipse(surf, (*color, fill_a), head_rect)

    for line in _internals():
        pts = [pt(x, y) for (x, y) in line]
        if len(pts) >= 2:
            pygame.draw.lines(surf, (*color, inner_a), False, pts, 1)

    for (jx, jy) in _JOINTS:
        pygame.draw.circle(surf, (*color, inner_a), pt(jx, jy), max(1, int(h * 0.006)))

    pygame.draw.polygon(surf, (*color, edge_a), outline, 1)
    pygame.draw.ellipse(surf, (*color, edge_a), head_rect, 1)

    # A faint ground ellipse anchors the figure instead of leaving it
    # floating in space.
    base_rect = pygame.Rect(0, 0, int(h * 0.30), int(h * 0.035))
    base_rect.center = (int(cx), int(h * 0.918))
    pygame.draw.ellipse(surf, (*color, line_a // 3), base_rect, 1)

    return surf


def get_figure(w, h, color, intensity=1.0):
    key = (w, h, color, round(intensity, 2))
    surf = _cache.get(key)
    if surf is None:
        if len(_cache) > 24:
            _cache.clear()
        surf = _build(w, h, color, intensity)
        _cache[key] = surf
    return surf


def node_pos(x, y, w, h, node):
    """Screen position of a normalized body node inside the figure box."""
    return (x + w / 2.0 + node[0] * h, y + node[1] * h)


def draw(screen, x, y, w, h, color, scan_frac, pulse=0.0, scan_color=None):
    """Draw the figure with a scanning band sweeping down it.

    scan_frac: 0-1 position of the scan band down the figure.
    pulse: 0-1 heart-node brightness, driven by real BPM by the caller.
    """
    base = get_figure(w, h, color, 1.0)
    screen.blit(base, (x, y))

    bright = get_figure(w, h, scan_color or (235, 250, 255), 1.0)
    band_h = max(6, int(h * 0.055))
    band_y = int(scan_frac * (h - band_h))
    band_y = max(0, min(h - band_h, band_y))

    # The highlight comes from the figure's own pixels, so the scan reads
    # as light passing through the body rather than a bar laid over it.
    # A full-width rule here (even a faint one, and especially a stack of
    # them) just paints a solid block across the chest.
    band = bright.subsurface(pygame.Rect(0, band_y, w, band_h)).copy()
    band.set_alpha(135)
    screen.blit(band, (x, y + band_y))

    line_y = y + band_y + band_h // 2
    sc = scan_color or (200, 240, 255)
    pygame.draw.line(screen, (*sc, 40), (x, line_y), (x + w, line_y), 1)

    # Heart node: a real-BPM pulse, the one thing on the figure that moves
    # to live data rather than on a fixed cycle.
    hx, hy = node_pos(x, y, w, h, HEART_NODE)
    r = max(2, int(h * 0.012))
    glow_r = int(r * (2.4 + 2.6 * pulse))
    glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
    for gr in range(glow_r, 0, -1):
        a = int(70 * pulse * (1.0 - gr / glow_r) ** 1.5)
        pygame.draw.circle(glow, (255, 90, 90, a), (glow_r, glow_r), gr)
    screen.blit(glow, (hx - glow_r, hy - glow_r))
    pygame.draw.circle(screen, (255, 120, 120, int(160 + 95 * pulse)),
                       (int(hx), int(hy)), r)
