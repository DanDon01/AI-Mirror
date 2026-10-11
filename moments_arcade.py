"""Retro arcade takeover Moments for AI-Mirror's Director.

Each of these briefly turns the whole mirror into a short "attract mode"
demo of a classic arcade game playing itself -- no input device exists,
so nothing here is actually player-controlled. Every render() is a pure
function of `elapsed` (seconds since the moment started): ball/paddle/
snake/invader positions are derived directly from elapsed via closed-form
wave/bounce formulas rather than accumulated frame-to-frame state, so
there is nothing to reset between plays and nothing that can drift.

These are the boldest, most build-heavy moments in the library -- see
the project plan's Phase 7. All five are ambient (no specific trigger),
rare, and weighted slightly below the library average so five full-
screen takeovers don't dominate a ~50-moment pool.
"""

import math
import random

import pygame

from effects_kit import ease_out_cubic
from event_director import Moment

_BG = (4, 6, 10)
_GREEN = (80, 255, 120)
_AMBER = (255, 190, 60)
_RED = (255, 90, 90)
_DIM = (60, 70, 80)

_font_cache = {}


def _font(size):
    f = _font_cache.get(size)
    if f is None:
        f = pygame.font.SysFont('consolas,dejavusansmono,monospace', size, bold=True)
        _font_cache[size] = f
    return f


def _intro_outro_alpha(elapsed, duration, fade=0.35):
    """0-1 envelope: eased fade in, hold, eased fade out."""
    if elapsed < fade:
        return ease_out_cubic(elapsed / fade)
    if elapsed > duration - fade:
        return ease_out_cubic(max(0.0, (duration - elapsed) / fade))
    return 1.0


def _triangle_wave(t, period):
    """0..1..0 triangle wave, period `period`."""
    phase = math.fmod(t, period) / period
    return 1.0 - abs(phase * 2.0 - 1.0)


def _fill_backdrop(screen, alpha):
    """Full-screen near-black backdrop with faint scanlines, alpha-faded
    for the intro/outro envelope."""
    w, h = screen.get_size()
    backdrop = pygame.Surface((w, h))
    backdrop.fill(_BG)
    for y in range(0, h, 4):
        pygame.draw.line(backdrop, (10, 14, 20), (0, y), (w, y))
    backdrop.set_alpha(int(255 * alpha))
    screen.blit(backdrop, (0, 0))


def _draw_text(screen, text, size, color, cx, y, alpha=255):
    surf = _font(size).render(text, True, color)
    surf.set_alpha(alpha)
    screen.blit(surf, (cx - surf.get_width() // 2, y))


# ---------------------------------------------------------------------
# Pong
# ---------------------------------------------------------------------

_PONG_DURATION = 10.0
_PONG_RALLY = 2.6


def _pong_ball_pos(t, w, h):
    court_l, court_r = w * 0.12, w * 0.88
    bx = court_l + (court_r - court_l) * _triangle_wave(t, _PONG_RALLY * 2)
    by = h * 0.5 + math.sin(t * 2.3) * (h * 0.16) + math.sin(t * 5.1) * (h * 0.04)
    return bx, by


def _render_pong(screen, elapsed, ctx):
    w, h = screen.get_size()
    alpha = _intro_outro_alpha(elapsed, _PONG_DURATION)
    _fill_backdrop(screen, alpha)

    court_top, court_bot = h * 0.30, h * 0.85
    for y in range(int(court_top), int(court_bot), 26):
        pygame.draw.line(screen, (*_DIM, int(180 * alpha)), (w // 2, y), (w // 2, y + 14), 3)

    bx, by = _pong_ball_pos(elapsed, w, h)
    by = max(court_top + 40, min(court_bot - 40, by))

    paddle_h, paddle_w = h * 0.10, 12
    lag = 0.18
    _, left_by = _pong_ball_pos(max(0.0, elapsed - lag), w, h)
    _, right_by = _pong_ball_pos(max(0.0, elapsed - lag * 0.6), w, h)
    left_by = max(court_top + paddle_h / 2, min(court_bot - paddle_h / 2, left_by))
    right_by = max(court_top + paddle_h / 2, min(court_bot - paddle_h / 2, right_by))

    left_x = w * 0.10
    right_x = w * 0.90 - paddle_w
    paddle_alpha = int(255 * alpha)
    pygame.draw.rect(screen, (*_GREEN, paddle_alpha),
                     (left_x, left_by - paddle_h / 2, paddle_w, paddle_h))
    pygame.draw.rect(screen, (*_GREEN, paddle_alpha),
                     (right_x, right_by - paddle_h / 2, paddle_w, paddle_h))
    pygame.draw.circle(screen, (*_GREEN, paddle_alpha), (int(bx), int(by)), 9)

    score = int(elapsed / (_PONG_RALLY * 2))
    _draw_text(screen, f"{score:02d}   {(score + 1) % 10:02d}", 40, _GREEN,
              w // 2, int(court_top - 70), alpha=int(255 * alpha))
    _draw_text(screen, "PONG", 20, _DIM, w // 2, int(court_top - 110), alpha=int(200 * alpha))


# ---------------------------------------------------------------------
# Breakout
# ---------------------------------------------------------------------

_BRK_DURATION = 11.0
_BRK_COLS, _BRK_ROWS = 8, 4
_BRK_COLORS = [_RED, _AMBER, _GREEN, (90, 160, 255)]
_brk_order = list(range(_BRK_COLS * _BRK_ROWS))
random.Random(1).shuffle(_brk_order)
_brk_pop_time = {idx: 0.7 + slot * (_BRK_DURATION * 0.75 / (_BRK_COLS * _BRK_ROWS))
                 for slot, idx in enumerate(_brk_order)}


def _breakout_ball_pos(t, w, h, top, bottom):
    bx = w * 0.15 + (w * 0.70) * _triangle_wave(t, 1.7)
    by = top + (bottom - top) * _triangle_wave(t, 2.9)
    return bx, by


def _render_breakout(screen, elapsed, ctx):
    w, h = screen.get_size()
    alpha = _intro_outro_alpha(elapsed, _BRK_DURATION)
    _fill_backdrop(screen, alpha)
    a255 = int(255 * alpha)

    grid_top, grid_bot = h * 0.14, h * 0.32
    cell_w = (w * 0.8) / _BRK_COLS
    cell_h = (grid_bot - grid_top) / _BRK_ROWS
    grid_x = w * 0.10

    for row in range(_BRK_ROWS):
        for col in range(_BRK_COLS):
            idx = row * _BRK_COLS + col
            if elapsed >= _brk_pop_time.get(idx, 999):
                continue
            bx = grid_x + col * cell_w + 3
            by = grid_top + row * cell_h + 3
            pygame.draw.rect(screen, (*_BRK_COLORS[row % len(_BRK_COLORS)], a255),
                             (bx, by, cell_w - 6, cell_h - 6))

    paddle_top, paddle_bot = grid_bot + h * 0.10, h * 0.80
    bx, by = _breakout_ball_pos(elapsed, w, h, grid_top + 20, paddle_bot - 20)

    lag = 0.12
    paddle_x, _ = _breakout_ball_pos(max(0.0, elapsed - lag), w, h, grid_top + 20, paddle_bot - 20)
    paddle_w, paddle_h = w * 0.14, 12
    paddle_x = max(w * 0.05, min(w * 0.95 - paddle_w, paddle_x - paddle_w / 2))
    pygame.draw.rect(screen, (*_GREEN, a255), (paddle_x, paddle_bot, paddle_w, paddle_h))
    pygame.draw.circle(screen, (*_AMBER, a255), (int(bx), int(by)), 8)

    _draw_text(screen, "BREAKOUT", 22, _DIM, w // 2, int(grid_top - 40), alpha=int(200 * alpha))


# ---------------------------------------------------------------------
# Missile Command
# ---------------------------------------------------------------------

_MC_DURATION = 9.0
_MC_COUNT = 6
_mc_rng = random.Random(2)
_mc_missiles = []
for _i in range(_MC_COUNT):
    start_t = 0.4 + _i * (_MC_DURATION - 2.0) / _MC_COUNT + _mc_rng.uniform(-0.2, 0.2)
    travel = _mc_rng.uniform(2.0, 3.2)
    _mc_missiles.append({
        'x': _mc_rng.uniform(0.12, 0.88),
        'gx': _mc_rng.uniform(0.20, 0.80),
        'start': start_t,
        'travel': travel,
        'intercept_frac': _mc_rng.uniform(0.45, 0.65),
    })


def _render_missile_command(screen, elapsed, ctx):
    w, h = screen.get_size()
    alpha = _intro_outro_alpha(elapsed, _MC_DURATION)
    _fill_backdrop(screen, alpha)
    a255 = int(255 * alpha)

    ground_y = h * 0.78
    pygame.draw.line(screen, (*_DIM, a255), (0, ground_y), (w, ground_y), 3)

    for m in _mc_missiles:
        t = elapsed - m['start']
        if t < 0:
            continue
        top_y = h * 0.10
        prog = min(1.0, t / m['travel'])
        mx = m['x'] * w
        my = top_y + (ground_y - top_y) * prog
        intercept_y = top_y + (ground_y - top_y) * m['intercept_frac']

        if my < intercept_y:
            tail_y = max(top_y, my - 40)
            pygame.draw.line(screen, (*_RED, a255), (mx, tail_y), (mx, my), 3)
            pygame.draw.circle(screen, (*_AMBER, a255), (int(mx), int(my)), 3)

            gx = m['gx'] * w
            trace_prog = min(1.0, t / (m['travel'] * m['intercept_frac']))
            tx = gx + (mx - gx) * trace_prog
            ty = ground_y - (ground_y - intercept_y) * trace_prog
            pygame.draw.line(screen, (*_GREEN, a255), (gx, ground_y), (tx, ty), 2)
        else:
            burst_age = t - m['travel'] * m['intercept_frac']
            if 0 <= burst_age < 0.6:
                r = int(6 + burst_age * 60)
                burst_alpha = int(a255 * max(0.0, 1.0 - burst_age / 0.6))
                pygame.draw.circle(screen, (*_AMBER, burst_alpha), (int(mx), int(intercept_y)), r, 2)

    _draw_text(screen, "MISSILE COMMAND", 22, _DIM, w // 2, int(h * 0.06), alpha=int(200 * alpha))


# ---------------------------------------------------------------------
# Snake
# ---------------------------------------------------------------------

_SNAKE_DURATION = 10.0
_SNAKE_SEGMENTS = 10
_SNAKE_FOOD = (0.5, 0.42)


def _snake_head(t, w, h):
    cx, cy = w * 0.5, h * 0.45
    ax, ay = w * 0.32, h * 0.18
    x = cx + ax * math.sin(t * 0.55)
    y = cy + ay * math.sin(t * 0.83 + 1.2)
    return x, y


def _render_snake(screen, elapsed, ctx):
    w, h = screen.get_size()
    alpha = _intro_outro_alpha(elapsed, _SNAKE_DURATION)
    _fill_backdrop(screen, alpha)
    a255 = int(255 * alpha)

    fx, fy = _SNAKE_FOOD[0] * w, _SNAKE_FOOD[1] * h
    pygame.draw.rect(screen, (*_RED, a255), (fx - 7, fy - 7, 14, 14))

    seg = 22
    for i in range(_SNAKE_SEGMENTS, -1, -1):
        sx, sy = _snake_head(max(0.0, elapsed - i * 0.10), w, h)
        shade = 255 - i * 12
        color = (max(0, min(255, int(_GREEN[0] * shade / 255))),
                 max(0, min(255, int(_GREEN[1] * shade / 255))),
                 max(0, min(255, int(_GREEN[2] * shade / 255))))
        pygame.draw.rect(screen, (*color, a255), (sx - seg / 2, sy - seg / 2, seg - 3, seg - 3))

    _draw_text(screen, "SNAKE", 22, _DIM, w // 2, int(h * 0.20), alpha=int(200 * alpha))


# ---------------------------------------------------------------------
# Space Invaders
# ---------------------------------------------------------------------

_SI_DURATION = 10.0
_SI_COLS, _SI_ROWS = 6, 3
_SI_STEP_DURATION = 0.35
_SI_MARCH_STEPS = 10


def _invader_rect(cx, cy, s, alpha):
    """A small blocky invader silhouette (two overlapping rects)."""
    return [
        pygame.Rect(cx - s * 0.5, cy - s * 0.2, s, s * 0.4),
        pygame.Rect(cx - s * 0.3, cy - s * 0.4, s * 0.6, s * 0.3),
    ]


def _render_space_invaders(screen, elapsed, ctx):
    w, h = screen.get_size()
    alpha = _intro_outro_alpha(elapsed, _SI_DURATION)
    _fill_backdrop(screen, alpha)
    a255 = int(255 * alpha)

    step = int(elapsed / _SI_STEP_DURATION)
    cycle = step % (_SI_MARCH_STEPS * 2)
    x_step = cycle if cycle <= _SI_MARCH_STEPS else _SI_MARCH_STEPS * 2 - cycle
    descend = step // (_SI_MARCH_STEPS * 2)

    grid_w, grid_h = w * 0.6, h * 0.02
    origin_x = w * 0.2 + (x_step - _SI_MARCH_STEPS / 2) * (w * 0.014)
    origin_y = h * 0.30 + descend * (h * 0.02)
    cell = min(grid_w / _SI_COLS, h * 0.05)

    for row in range(_SI_ROWS):
        for col in range(_SI_COLS):
            cx = origin_x + col * cell * 1.3
            cy = origin_y + row * cell * 1.3
            for rect in _invader_rect(cx, cy, cell * 0.8, a255):
                pygame.draw.rect(screen, (*_GREEN, a255), rect)

    _draw_text(screen, "SPACE INVADERS", 22, _DIM, w // 2, int(h * 0.20), alpha=int(200 * alpha))


# ---------------------------------------------------------------------

_MOMENTS = [
    Moment('pong_interlude', 'arcade', _render_pong,
          duration_s=_PONG_DURATION, cooldown_s=3600 * 18, weight=0.6),
    Moment('breakout_break', 'arcade', _render_breakout,
          duration_s=_BRK_DURATION, cooldown_s=3600 * 20, weight=0.6),
    Moment('missile_command_moment', 'arcade', _render_missile_command,
          duration_s=_MC_DURATION, cooldown_s=3600 * 22, weight=0.55),
    Moment('snake_cameo', 'arcade', _render_snake,
          duration_s=_SNAKE_DURATION, cooldown_s=3600 * 16, weight=0.65),
    Moment('space_invaders_march', 'arcade', _render_space_invaders,
          duration_s=_SI_DURATION, cooldown_s=3600 * 24, weight=0.5),
]


def register(director):
    for m in _MOMENTS:
        director.register(m)
