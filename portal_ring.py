"""The Portal Ring -- an always-on ambient frame around the mirror's
clear center zone, plus a full-canvas depth field behind everything.

Not a Moment (event_director.py) -- this is permanent, not triggered.
It's the answer to "the baseline is still just a plain dashboard": the
empty center itself reads as a portal aperture with real depth -- three
concentric instrument rings rotating at different speeds (motion
parallax is what actually sells depth in 2D; a real 3D engine is not
a real option in pygame on a Pi 5), a breathing energy core, orbiting
motes, and a sparse starfield drifting across the *entire* screen, not
just the weather band. It reacts to real conditions instead of sitting
there as static decoration: color follows day/night and the weather
condition, and it flares when a Moment (event_director.py) is playing,
so the ambient layer reads as aware of what's actually happening
rather than a decoration running on its own clock.

Deliberately never opaque and never fills the center; the reflection
stays the actual subject.
"""

import math
import random
import time

import numpy as np
import pygame

from effects_kit import glow_sprite

_STORM_COLOR = (210, 220, 255)
_RAIN_COLOR = (110, 200, 235)


def _weather_color(condition, is_night):
    """Day/night base comes from the active theme (theme.ring_colors()),
    so switching themes re-tints the ring; storm/rain still nudge it for
    real weather regardless of theme."""
    import theme
    colors = theme.ring_colors()
    if colors is None:
        return None
    day_color, night_color = colors
    if condition in ('storm', 'thunderstorm'):
        return _STORM_COLOR
    if condition in ('rain', 'drizzle'):
        return _RAIN_COLOR
    return night_color if is_night else day_color


class PortalRing:
    def __init__(self, screen_width, screen_height, is_night=False):
        self.w = screen_width
        self.h = screen_height
        self.cx = screen_width // 2
        self.cy = int(screen_height * 0.50)
        # Sized to the actual center zone (56% of width, LAYOUT_V2), not
        # the full screen -- bigger than that collides with the left/right
        # column text.
        center_zone_w = screen_width * 0.56
        self.radius = int(center_zone_w * 0.40)
        import theme
        colors = theme.ring_colors() or ((150, 220, 255), (110, 190, 255))
        self.color = colors[1] if is_night else colors[0]
        self._target_color = self.color
        self._t0 = time.time()
        self._moment_flare = 0.0  # eased toward 1.0 while a Moment plays

        self._outer_glow = self._build_outer_glow()
        core_r = max(8, int(self.radius * 0.46))
        self._core_glow = glow_sprite(core_r, self.color, 255, core_frac=0.15)
        self._mote_glow = glow_sprite(6, self.color, 220, core_frac=0.5)

        # A sparse depth field across the WHOLE canvas, not just the
        # weather band -- three parallax layers (far/mid/near: slower and
        # fainter the "further" a layer reads) so the mirror feels like a
        # window into real depth rather than flat black with UI on it.
        self._star_layers = [self._build_star_layer(n, speed, alpha_range, r_range)
                             for n, speed, alpha_range, r_range in (
                                 (70, 2.0, (16, 46), (0.6, 1.1)),
                                 (40, 5.0, (24, 60), (0.8, 1.4)),
                                 (18, 9.0, (34, 80), (1.0, 1.8)),
                             )]

    def _build_star_layer(self, count, speed, alpha_range, r_range):
        return [{
            'x': random.uniform(0, self.w),
            'y': random.uniform(0, self.h),
            'speed': speed,
            'alpha': random.uniform(*alpha_range),
            'r': random.uniform(*r_range),
            'phase': random.uniform(0, math.tau),
        } for _ in range(count)]

    def _build_outer_glow(self):
        """A soft ring-shaped glow (bright at self.radius, fading both in
        and out) computed directly as a per-pixel alpha field -- stamping
        ~68 overlapping circle outlines the naive way compounds alpha at
        every pixel two adjacent radii both touch (worst at the top/bottom
        of the circle, where consecutive radii's rasterized pixels overlap
        most), which bakes a solid blob into the "glow" instead of a
        gradient. The same class of bug as the early stamped-circle cloud
        attempts -- fixed the same way: build the falloff as real per-pixel
        alpha, not stacked draw calls."""
        size = int(self.radius * 2.5)
        band = 34
        yy, xx = np.mgrid[0:size, 0:size]
        c = size / 2.0
        dist = np.sqrt((xx - c) ** 2 + (yy - c) ** 2)
        d = np.abs(dist - self.radius)
        t = np.clip(1.0 - d / band, 0.0, 1.0)
        alpha = (65.0 * t ** 1.6).astype(np.uint8)

        rgba = np.empty((size, size, 4), dtype=np.uint8)
        rgba[..., 0] = self.color[0]
        rgba[..., 1] = self.color[1]
        rgba[..., 2] = self.color[2]
        rgba[..., 3] = alpha
        return pygame.image.frombuffer(rgba.tobytes(), (size, size), 'RGBA')

    def set_conditions(self, is_night, weather_condition=None):
        """Called once per frame by the caller with live state -- cheap
        (just picks a target color), the actual blending happens in draw()
        so a condition change eases in rather than snapping. Some themes
        (e.g. "Luxury") hide the ring entirely -- self.enabled tracks that."""
        color = _weather_color(weather_condition, is_night)
        self.enabled = color is not None
        if self.enabled:
            self._target_color = color

    def notify_moment_active(self, active):
        self._moment_wants_flare = active

    def _step_color(self, dt):
        # Ease current color toward target, ~2s to fully transition.
        rate = dt / 2.0
        self.color = tuple(
            int(c + (t - c) * min(1.0, rate))
            for c, t in zip(self.color, self._target_color)
        )

    def draw(self, screen, dt=1 / 30, moment_active=False):
        if not getattr(self, 'enabled', True):
            return
        t = time.time() - self._t0
        self._step_color(dt)

        # Flare toward 1.0 while a Moment plays, ease back down otherwise --
        # the ring visibly "notices" when something big is happening.
        target_flare = 1.0 if moment_active else 0.0
        self._moment_flare += (target_flare - self._moment_flare) * min(1.0, dt * 3.0)
        flare = self._moment_flare

        # Full-canvas parallax starfield, behind the ring and everything
        # else -- drawn first so modules/ring/moments all sit on top of it.
        for layer in self._star_layers:
            for s in layer:
                s['x'] -= s['speed'] * dt
                if s['x'] < -4:
                    s['x'] = self.w + 4
                    s['y'] = random.uniform(0, self.h)
                tw = 0.6 + 0.4 * math.sin(t * 0.8 + s['phase'])
                a = int(s['alpha'] * tw)
                if a > 0:
                    pygame.draw.circle(screen, (*self.color, a), (int(s['x']), int(s['y'])), max(1, int(s['r'])))

        gw = self._outer_glow.get_width()
        screen.blit(self._outer_glow, (self.cx - gw // 2, self.cy - gw // 2))

        # Three concentric instrument rings, each rotating at a different
        # speed -- motion parallax is what actually reads as depth in a
        # flat 2D render, not a single flat circle. Live-drawn each frame
        # (cheap: small primitives, the same pattern weather_animations
        # already runs at 30 FPS for star fields) rather than rotating a
        # large pre-rendered bitmap.
        ring_specs = (
            (self.radius, 0.28, 72, 1.0),
            (int(self.radius * 0.82), -0.19, 48, 0.75),
            (int(self.radius * 1.14), 0.12, 90, 0.5),
        )
        for radius, speed, ticks, weight in ring_specs:
            rot = t * speed
            boost = 1.0 + flare * 0.8
            for i in range(ticks):
                ang = (math.tau / ticks) * i + rot
                long_tick = (i % 6 == 0)
                inner = radius - (16 if long_tick else 7) * weight
                cos_a, sin_a = math.cos(ang), math.sin(ang)
                x1 = self.cx + cos_a * inner
                y1 = self.cy + sin_a * inner
                x2 = self.cx + cos_a * radius
                y2 = self.cy + sin_a * radius
                alpha = min(255, int((225 if long_tick else 100) * weight * boost))
                pygame.draw.line(screen, (*self.color, alpha), (x1, y1), (x2, y2), 2 if long_tick else 1)
            pygame.draw.circle(screen, (*self.color, min(255, int(180 * weight * boost))),
                               (self.cx, self.cy), radius, 2 if weight >= 1.0 else 1)

        # Orbiting motes, counter-rotating at a slightly wider radius.
        orbit_r = self.radius + 40
        for i in range(5):
            ang = -(t * 0.5) + (math.tau / 5) * i
            x = self.cx + math.cos(ang) * orbit_r
            y = self.cy + math.sin(ang) * orbit_r * 0.94
            spr = self._mote_glow
            screen.blit(spr, (int(x) - spr.get_width() // 2, int(y) - spr.get_height() // 2))

        # Breathing energy core -- alpha modulated via set_alpha (a blit-time
        # multiplier on the precomputed sprite, not a regeneration), so this
        # costs nothing extra per frame despite changing continuously.
        # Brightens noticeably while a Moment is active.
        breath = 0.5 + 0.5 * math.sin(t * 0.4)
        self._core_glow.set_alpha(min(255, int(70 + 60 * breath + 120 * flare)))
        cw = self._core_glow.get_width()
        screen.blit(self._core_glow, (self.cx - cw // 2, self.cy - cw // 2))

        # Radar sweep -- a bright leading edge with a fading wedge trail,
        # sonar-style. The single most recognizable "ship's computer" cue.
        sweep_ang = t * 0.9
        sweep_r = self.radius * 1.14
        for k in range(14):
            back = k * 0.045
            a = int(max(0, 150 * (1.0 - k / 14.0)) * (1.0 + flare * 0.5))
            if a <= 0:
                continue
            ang = sweep_ang - back
            x2 = self.cx + math.cos(ang) * sweep_r
            y2 = self.cy + math.sin(ang) * sweep_r
            pygame.draw.line(screen, (*self.color, min(255, a)), (self.cx, self.cy), (x2, y2), 1)

    def draw_hud_frame(self, screen):
        """Corner viewfinder brackets framing the whole screen -- the
        "you're looking through a ship's display" cue, cheap (8 short
        lines), independent of the center ring so it reads even when the
        ring itself is small relative to a big display. Hidden by the
        same theme toggle as the ring (see set_conditions)."""
        if not getattr(self, 'enabled', True):
            return
        w, h = screen.get_width(), screen.get_height()
        margin = 22
        arm = 46
        alpha = 130
        corners = (
            ((margin, margin), (1, 1)),
            ((w - margin, margin), (-1, 1)),
            ((margin, h - margin), (1, -1)),
            ((w - margin, h - margin), (-1, -1)),
        )
        for (cx, cy), (dx, dy) in corners:
            pygame.draw.line(screen, (*self.color, alpha), (cx, cy), (cx + arm * dx, cy), 2)
            pygame.draw.line(screen, (*self.color, alpha), (cx, cy), (cx, cy + arm * dy), 2)
