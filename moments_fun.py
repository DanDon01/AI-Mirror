"""Pop-culture homages and whimsical easter eggs for the Moments Director.

Every moment here is pure ambient whimsy -- no `trigger_events`, so each
one just enters the Director's idle random pool (see event_director.py)
and fires on its own rare schedule rather than waiting on a module to
report something. Nothing here needs any wiring elsewhere.

Homages are stylistic nods only: silhouettes, color language, motion
feel. No reproduced character art, logos, or verbatim quoted lines.
"""

import math
import random

import pygame

from config import (
    load_font, FONT_SIZE_CLOCK,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_DIM,
    COLOR_ACCENT_PRIMARY, COLOR_ACCENT_BLUE, COLOR_ACCENT_GREEN,
    COLOR_ACCENT_RED, COLOR_ACCENT_AMBER,
)
from effects_kit import glow_sprite, ease_out_cubic
from event_director import Moment

HOUR = 3600.0

_mono_cache = {}


def _mono_font(size):
    font = _mono_cache.get(size)
    if font is None:
        font = pygame.font.SysFont('consolas,dejavusansmono,monospace', size)
        _mono_cache[size] = font
    return font


# ---------------------------------------------------------------- HAL's Red Eye

_HAL_RED = (220, 40, 40)
_HAL_CORE = (255, 100, 75)


def _render_hal_eye(screen, elapsed, ctx):
    duration = 7.0
    t = elapsed / duration
    if t < 0.15:
        alpha_t = ease_out_cubic(t / 0.15)
    elif t > 0.85:
        alpha_t = 1.0 - ease_out_cubic((t - 0.85) / 0.15)
    else:
        alpha_t = 1.0

    sw, sh = screen.get_width(), screen.get_height()
    cx = sw * 0.5 + math.sin(t * math.tau) * sw * 0.14
    cy = sh * 0.46

    radius = max(6, int(min(sw, sh) * 0.05))
    halo = glow_sprite(int(radius * 2.4), _HAL_RED, int(90 * alpha_t), core_frac=0.22)
    core = glow_sprite(radius, _HAL_CORE, int(235 * alpha_t), core_frac=0.5)
    screen.blit(halo, (int(cx - halo.get_width() / 2), int(cy - halo.get_height() / 2)))
    screen.blit(core, (int(cx - core.get_width() / 2), int(cy - core.get_height() / 2)))


# ---------------------------------------------------------------- The Matrix Hack

_MATRIX_CHARS = "01ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_matrix_glyphs = {'head': None, 'tail': None}
_matrix_state = {'cols': None, 'last_elapsed': -1.0}


def _get_matrix_glyphs(glyph_size):
    if _matrix_glyphs['head'] is None:
        font = _mono_font(glyph_size)
        _matrix_glyphs['head'] = [font.render(ch, True, (205, 255, 215)) for ch in _MATRIX_CHARS]
        _matrix_glyphs['tail'] = [font.render(ch, True, (40, 200, 90)) for ch in _MATRIX_CHARS]
    return _matrix_glyphs


def _init_matrix_columns(sw, sh, glyph_size):
    n = max(1, sw // glyph_size)
    # This effect only runs ~3s -- a column seeded a full screen-height
    # above the top (as a naive "start off-screen" seed would) never
    # scrolls into view in time. Most start already falling somewhere
    # in frame; speed is tuned for a portrait screen's full height to
    # matter within that short window, not a slow ambient drift.
    return [{
        'x': i * glyph_size,
        'y': random.uniform(-sh * 0.3, sh),
        'speed': random.uniform(650, 1100),
        'len': random.randint(6, 16),
    } for i in range(n)]


def _draw_matrix_rain(screen, local_elapsed, glyph_size=22):
    sw, sh = screen.get_width(), screen.get_height()
    state = _matrix_state
    if local_elapsed < state['last_elapsed'] or state['cols'] is None:
        state['cols'] = _init_matrix_columns(sw, sh, glyph_size)
    dt = max(0.0, min(0.1, local_elapsed - state['last_elapsed']))
    state['last_elapsed'] = local_elapsed

    glyphs = _get_matrix_glyphs(glyph_size)
    for c in state['cols']:
        c['y'] += c['speed'] * dt
        if c['y'] - c['len'] * glyph_size > sh:
            c['y'] = random.uniform(-200, 0)
            c['speed'] = random.uniform(650, 1100)
            c['len'] = random.randint(6, 16)
        for j in range(c['len']):
            gy = c['y'] - j * glyph_size
            if gy < -glyph_size or gy > sh:
                continue
            pool = glyphs['head'] if j == 0 else glyphs['tail']
            glyph = random.choice(pool)
            if j > 0:
                glyph.set_alpha(int(220 * (1.0 - j / c['len'])))
            else:
                glyph.set_alpha(255)
            screen.blit(glyph, (c['x'], int(gy)))


def _draw_glitch_lines(screen, seed):
    rng = random.Random(seed)
    sw, sh = screen.get_width(), screen.get_height()
    overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
    for _ in range(14):
        y = rng.randint(0, sh)
        h = rng.randint(1, 4)
        shade = rng.randint(120, 220)
        pygame.draw.rect(overlay, (shade, shade, shade, 90), (0, y, sw, h))
    screen.blit(overlay, (0, 0))


def _render_matrix_hack(screen, elapsed, ctx):
    sw, sh = screen.get_width(), screen.get_height()
    glitch_end = 0.22
    rain_end = 3.4

    if elapsed < glitch_end:
        _draw_glitch_lines(screen, int(elapsed / 0.06))
    elif elapsed < rain_end:
        _draw_matrix_rain(screen, elapsed - glitch_end)
        if elapsed > rain_end - 0.4:
            fade = (elapsed - (rain_end - 0.4)) / 0.4
            overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
            overlay.fill((8, 10, 18, int(255 * fade)))
            screen.blit(overlay, (0, 0))
    else:
        age = elapsed - rain_end
        flash = 0.0
        for start in (0.0, 0.18):
            local = age - start
            if 0 <= local < 0.08:
                flash = max(flash, 1.0 - local / 0.08)
        if flash > 0:
            overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
            overlay.fill((230, 240, 255, int(200 * flash)))
            screen.blit(overlay, (0, 0))


# ---------------------------------------------------------------- Terminator Vision

_TERM_RED = (220, 60, 60)


def _render_terminator(screen, elapsed, ctx):
    duration = 1.5
    t = elapsed / duration
    if t < 0.15:
        alpha_t = ease_out_cubic(t / 0.15)
    elif t > 0.75:
        alpha_t = 1.0 - ease_out_cubic((t - 0.75) / 0.25)
    else:
        alpha_t = 1.0

    sw, sh = screen.get_width(), screen.get_height()
    overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
    converge = ease_out_cubic(min(1.0, t / 0.4)) * 24
    bracket_len = 46
    inset = 30 + converge
    corners = [
        (inset, inset, 1, 1),
        (sw - inset, inset, -1, 1),
        (inset, sh - inset, 1, -1),
        (sw - inset, sh - inset, -1, -1),
    ]
    col = (*_TERM_RED, int(200 * alpha_t))
    for cx, cy, dx, dy in corners:
        pygame.draw.line(overlay, col, (cx, cy), (cx + dx * bracket_len, cy), 3)
        pygame.draw.line(overlay, col, (cx, cy), (cx, cy + dy * bracket_len), 3)
    scan_y = int(sh * min(1.0, t * 1.1))
    pygame.draw.line(overlay, (*_TERM_RED, int(140 * alpha_t)), (0, scan_y), (sw, scan_y), 2)
    screen.blit(overlay, (0, 0))


# ---------------------------------------------------------------- Star Field Jump

_starfield_state = {'streaks': None}


def _render_star_field(screen, elapsed, ctx):
    duration = 1.2
    sw, sh = screen.get_width(), screen.get_height()
    cx, cy = sw / 2, sh / 2

    if elapsed < 0.03 or _starfield_state['streaks'] is None:
        _starfield_state['streaks'] = [
            {'ang': random.uniform(0, math.tau), 'delay': random.uniform(0, 0.3)}
            for _ in range(60)
        ]

    t = max(0.0, min(1.0, elapsed / duration))
    fade = 1.0 if t <= 0.8 else max(0.0, 1.0 - (t - 0.8) / 0.2)

    overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
    for s in _starfield_state['streaks']:
        span = max(0.001, duration - s['delay'])
        local_t = max(0.0, min(1.0, (elapsed - s['delay']) / span))
        if local_t <= 0:
            continue
        speed_t = local_t ** 2
        dist = speed_t * max(sw, sh) * 0.75
        length = 10 + speed_t * 140
        x1 = cx + math.cos(s['ang']) * dist
        y1 = cy + math.sin(s['ang']) * dist
        x0 = cx + math.cos(s['ang']) * max(0, dist - length)
        y0 = cy + math.sin(s['ang']) * max(0, dist - length)
        alpha = int(220 * fade)
        if alpha > 0:
            pygame.draw.line(overlay, (230, 236, 245, alpha), (x0, y0), (x1, y1), 2)
    screen.blit(overlay, (0, 0))


# ---------------------------------------------------------------- KITT Scanner

_KITT_RED = (230, 40, 40)


def _render_kitt(screen, elapsed, ctx):
    duration = 3.0
    sw, sh = screen.get_width(), screen.get_height()
    t = elapsed / duration
    if t < 0.08:
        alpha_t = t / 0.08
    elif t > 0.9:
        alpha_t = max(0.0, 1.0 - (t - 0.9) / 0.1)
    else:
        alpha_t = 1.0

    cycles = 2.5
    x = sw / 2 + math.sin(elapsed * (cycles * math.tau / duration)) * (sw * 0.42)
    y = sh - 6

    glow = glow_sprite(16, _KITT_RED, int(220 * alpha_t), core_frac=0.4)
    screen.blit(glow, (int(x - glow.get_width() / 2), int(y - glow.get_height() / 2)))
    bar = pygame.Surface((60, 4), pygame.SRCALPHA)
    bar.fill((*_KITT_RED, int(200 * alpha_t)))
    screen.blit(bar, (int(x - 30), int(y - 2)))


# ---------------------------------------------------------------- Sound-off Disco

_DISCO_COLORS = [COLOR_ACCENT_BLUE, COLOR_ACCENT_AMBER, COLOR_ACCENT_GREEN,
                  COLOR_ACCENT_RED, COLOR_ACCENT_PRIMARY]


def _render_disco(screen, elapsed, ctx):
    duration = 5.0
    sw, sh = screen.get_width(), screen.get_height()
    t = elapsed / duration
    if t < 0.1:
        fade = t / 0.1
    elif t > 0.85:
        fade = max(0.0, 1.0 - (t - 0.85) / 0.15)
    else:
        fade = 1.0

    overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
    n = 6
    for i in range(n):
        y = sh * (0.12 + i * 0.15)
        color = _DISCO_COLORS[i % len(_DISCO_COLORS)]
        pulse = 0.5 + 0.5 * math.sin(elapsed * 3.2 + i * 1.1)
        alpha = int(90 * fade * pulse)
        if alpha <= 0:
            continue
        band = pygame.Surface((sw, 3), pygame.SRCALPHA)
        band.fill((*color, alpha))
        overlay.blit(band, (0, int(y)))
    screen.blit(overlay, (0, 0))


# ---------------------------------------------------------------- Shooting Star

def _render_shooting_star(screen, elapsed, ctx):
    duration = 1.5
    sw, sh = screen.get_width(), screen.get_height()
    t = max(0.0, min(1.0, elapsed / duration))

    band_bot = sh * 0.25
    x0, y0 = sw * 0.15, band_bot * 0.15
    x1, y1 = sw * 0.85, band_bot * 0.85

    overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
    trail_len = 8
    for i in range(trail_len):
        tt = t - i * 0.02
        if tt < 0:
            break
        px = x0 + (x1 - x0) * tt
        py = y0 + (y1 - y0) * tt
        alpha = int(255 * (1 - i / trail_len))
        r = max(1, 3 - i // 3)
        if alpha > 0:
            pygame.draw.circle(overlay, (236, 242, 248, alpha), (int(px), int(py)), r)
    screen.blit(overlay, (0, 0))


# ---------------------------------------------------------------- UFO Flyby

def _render_ufo(screen, elapsed, ctx):
    duration = 3.0
    sw, sh = screen.get_width(), screen.get_height()
    t = elapsed / duration
    x = -80 + t * (sw + 160)
    y = sh * 0.16
    if t < 0.08:
        fade = t / 0.08
    elif t > 0.92:
        fade = max(0.0, 1.0 - (t - 0.92) / 0.08)
    else:
        fade = 1.0

    trail = glow_sprite(26, (150, 170, 190), int(40 * fade), core_frac=0.3)
    screen.blit(trail, (int(x - trail.get_width() / 2), int(y + 6 - trail.get_height() / 2)))

    craft = pygame.Surface((80, 30), pygame.SRCALPHA)
    pygame.draw.ellipse(craft, (120, 128, 140, int(230 * fade)), (5, 14, 70, 12))
    pygame.draw.ellipse(craft, (180, 210, 230, int(200 * fade)), (28, 2, 24, 16))
    for i, dx in enumerate((16, 40, 64)):
        blink = 0.5 + 0.5 * math.sin(elapsed * 6 + i * 2)
        pygame.draw.circle(craft, (255, 220, 120, int(220 * fade * blink)), (dx, 24), 2)
    screen.blit(craft, (int(x - 40), int(y - 15)))


# ---------------------------------------------------------------- Clock Glitch

def _render_clock_glitch(screen, elapsed, ctx):
    frame = int(elapsed / 0.08)
    rng = random.Random(frame)
    digits = ''.join(rng.choice('0123456789') for _ in range(4))
    font = load_font('light', FONT_SIZE_CLOCK)
    surf = font.render(f"{digits[:2]}:{digits[2:]}", True, COLOR_TEXT_PRIMARY)
    screen.blit(surf, (22, 20))


# ---------------------------------------------------------------- Retro Cameo

def _render_retro_cameo(screen, elapsed, ctx):
    duration = 2.5
    sw, sh = screen.get_width(), screen.get_height()
    t = elapsed / duration
    x = -60 + t * (sw + 120)
    y = sh * 0.5
    color = (90, 230, 230)

    body = pygame.Surface((28, 40), pygame.SRCALPHA)
    pygame.draw.rect(body, color, (8, 0, 12, 14))
    pygame.draw.rect(body, color, (2, 14, 24, 16))
    pygame.draw.rect(body, color, (2, 30, 8, 10))
    pygame.draw.rect(body, color, (18, 30, 8, 10))
    screen.blit(body, (int(x), int(y - 20)))


# ---------------------------------------------------------------- Weather Banter

_BANTER_LINES = [
    "the mirror has opinions today",
    "looking good, as always",
    "a fine day for a reflection",
    "your secret's safe with this mirror",
    "plot twist: it's still just you",
]
_banter_state = {'line': None}


def _render_weather_banter(screen, elapsed, ctx):
    duration = 4.0
    if elapsed < 0.05 or _banter_state['line'] is None:
        _banter_state['line'] = random.choice(_BANTER_LINES)

    t = elapsed / duration
    if t < 0.25:
        alpha = ease_out_cubic(t / 0.25)
    elif t > 0.75:
        alpha = max(0.0, 1.0 - ease_out_cubic((t - 0.75) / 0.25))
    else:
        alpha = 1.0

    font = load_font('light', 22)
    surf = font.render(_banter_state['line'], True, COLOR_ACCENT_PRIMARY)
    surf.set_alpha(int(255 * alpha))
    sh = screen.get_height()
    screen.blit(surf, (24, int(sh * 0.12)))


# ---------------------------------------------------------------- Mirror Blink

def _render_mirror_blink(screen, elapsed, ctx):
    duration = 0.25
    if duration * 0.33 <= elapsed <= duration * 0.67:
        sw, sh = screen.get_width(), screen.get_height()
        black = pygame.Surface((sw, sh))
        black.fill((0, 0, 0))
        screen.blit(black, (0, 0))


# ---------------------------------------------------------------- Ghost Reflection

_ghost_state = {'x': None, 'y': None, 'w': None, 'h': None}


def _render_ghost(screen, elapsed, ctx):
    duration = 3.0
    sw, sh = screen.get_width(), screen.get_height()
    if elapsed < 0.05 or _ghost_state['x'] is None:
        _ghost_state['x'] = random.uniform(sw * 0.15, sw * 0.6)
        _ghost_state['y'] = random.uniform(sh * 0.25, sh * 0.6)
        _ghost_state['w'] = random.uniform(120, 220)
        _ghost_state['h'] = random.uniform(60, 120)

    t = elapsed / duration
    fade = max(0.0, 1.0 - t)
    drift = t * 14
    rect = pygame.Rect(
        int(_ghost_state['x'] + drift), int(_ghost_state['y'] + drift * 0.4),
        int(_ghost_state['w']), int(_ghost_state['h']),
    )
    overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
    pygame.draw.rect(overlay, (200, 210, 225, int(38 * fade)), rect, 1)
    screen.blit(overlay, (0, 0))


# ---------------------------------------------------------------- Fake Loading

def _render_fake_loading(screen, elapsed, ctx):
    duration = 1.8
    if elapsed >= duration:
        return
    sw, sh = screen.get_width(), screen.get_height()
    cx, cy = sw // 2, int(sh * 0.46)
    r = 26
    angle = (elapsed * 480) % 360
    rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
    pygame.draw.arc(screen, COLOR_TEXT_SECONDARY, rect, math.radians(angle), math.radians(angle + 90), 3)

    bar_w, bar_h = 160, 4
    bx, by = cx - bar_w // 2, cy + r + 18
    pygame.draw.rect(screen, (60, 64, 72), (bx, by, bar_w, bar_h))
    fill_w = int(bar_w * min(1.0, elapsed / duration))
    pygame.draw.rect(screen, COLOR_ACCENT_PRIMARY, (bx, by, fill_w, bar_h))

    font = load_font('regular', 14)
    label = font.render("Loading...", True, COLOR_TEXT_DIM)
    screen.blit(label, (cx - label.get_width() // 2, by + 12))


# ---------------------------------------------------------------- Konami Nod

def _render_konami(screen, elapsed, ctx):
    duration = 0.6
    if elapsed >= duration:
        return
    sw, sh = screen.get_width(), screen.get_height()
    font = _mono_font(16)
    surf = font.render("↑ ↑ ↓ ↓ ← → ← → B A", True, COLOR_ACCENT_GREEN)
    screen.blit(surf, (sw - surf.get_width() - 20, sh - surf.get_height() - 20))


# ---------------------------------------------------------------- Fourth Wall Wink

_WINK_LINES = ["...hi.", "still here.", "nice haircut.", "you're up early."]
_wink_state = {'line': None}


def _render_fourth_wall(screen, elapsed, ctx):
    duration = 3.0
    if elapsed < 0.05 or _wink_state['line'] is None:
        _wink_state['line'] = random.choice(_WINK_LINES)

    t = elapsed / duration
    if t < 0.2:
        alpha = ease_out_cubic(t / 0.2)
    elif t > 0.8:
        alpha = max(0.0, 1.0 - ease_out_cubic((t - 0.8) / 0.2))
    else:
        alpha = 1.0

    font = load_font('light', 20)
    surf = font.render(_wink_state['line'], True, COLOR_TEXT_SECONDARY)
    surf.set_alpha(int(255 * alpha))
    sw, sh = screen.get_width(), screen.get_height()
    screen.blit(surf, (sw // 2 - surf.get_width() // 2, int(sh * 0.75)))


# ---------------------------------------------------------------- registry

_MOMENTS = [
    Moment("hal_red_eye", "fun", _render_hal_eye,
           duration_s=7.0, cooldown_s=HOUR * 30, weight=0.6),
    Moment("matrix_hack", "fun", _render_matrix_hack,
           duration_s=4.0, cooldown_s=HOUR * 20, weight=0.5),
    Moment("terminator_vision", "fun", _render_terminator,
           duration_s=1.5, cooldown_s=HOUR * 15, weight=0.6),
    Moment("star_field_jump", "fun", _render_star_field,
           duration_s=1.2, cooldown_s=HOUR * 15, weight=0.6),
    Moment("kitt_scanner", "fun", _render_kitt,
           duration_s=3.0, cooldown_s=HOUR * 15, weight=0.6),
    Moment("sound_off_disco", "fun", _render_disco,
           duration_s=5.0, cooldown_s=HOUR * 10, weight=0.5),
    Moment("shooting_star", "fun", _render_shooting_star,
           duration_s=1.5, cooldown_s=1800.0, weight=0.8),
    Moment("ufo_flyby", "fun", _render_ufo,
           duration_s=3.0, cooldown_s=HOUR * 15, weight=0.4),
    Moment("clock_glitch", "fun", _render_clock_glitch,
           duration_s=0.4, cooldown_s=1800.0, weight=0.7),
    Moment("retro_cameo", "fun", _render_retro_cameo,
           duration_s=2.5, cooldown_s=HOUR * 10, weight=0.5),
    Moment("weather_banter", "fun", _render_weather_banter,
           duration_s=4.0, cooldown_s=1800.0, weight=0.7),
    Moment("mirror_blink", "fun", _render_mirror_blink,
           duration_s=0.25, cooldown_s=HOUR * 8, weight=0.5),
    Moment("ghost_reflection", "fun", _render_ghost,
           duration_s=3.0, cooldown_s=HOUR * 10, weight=0.4),
    Moment("fake_loading", "fun", _render_fake_loading,
           duration_s=1.8, cooldown_s=HOUR * 10, weight=0.5),
    Moment("konami_nod", "fun", _render_konami,
           duration_s=0.6, cooldown_s=HOUR * 15, weight=0.3),
    Moment("fourth_wall_wink", "fun", _render_fourth_wall,
           duration_s=3.0, cooldown_s=HOUR * 20, weight=0.3),
]


def register(director):
    for m in _MOMENTS:
        director.register(m)
