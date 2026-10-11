"""Real-data themed Moments: achievement, news, financial, smarthome.

Each render(screen, elapsed, ctx) is called every frame of a moment's
lifetime with a fresh `elapsed` (seconds since it started) -- there is
no persistent per-play object, so any randomized motion (particles,
sparks) must be a deterministic function of elapsed, seeded once per
play and cached on the ctx dict itself (see `_seed_for`). ctx may be
None or missing expected keys -- trigger wiring lands in a later pass,
so every render function has a sane fallback.
"""

import math
import random

import pygame

from config import (
    COLOR_ACCENT_BLUE, COLOR_ACCENT_AMBER, COLOR_ACCENT_GREEN, COLOR_ACCENT_RED,
    COLOR_ACCENT_PRIMARY, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_DIM,
    load_font,
)
from effects_kit import (
    glow_sprite, draw_trace_progress, ease_out_cubic, ease_out_back,
    flash_alpha_envelope, safe_smoothscale,
)
from event_director import Moment

DEEP_RED = (200, 60, 60)
GOLD = (235, 195, 110)


# ----- shared helpers -----

def _seed_for(ctx):
    """A random seed that's stable across every render() call within one
    moment's play (ctx is the same object for the whole play) but varies
    play to play."""
    if isinstance(ctx, dict):
        if '_seed' not in ctx:
            ctx['_seed'] = random.randint(0, 2 ** 31 - 1)
        return ctx['_seed']
    return 12345


def _pick_once(ctx, key, options):
    if isinstance(ctx, dict):
        if key not in ctx:
            ctx[key] = random.choice(options)
        return ctx[key]
    return options[0]


_fonts = {}


def _font(weight, size):
    key = (weight, size)
    f = _fonts.get(key)
    if f is None:
        f = load_font(weight, size)
        _fonts[key] = f
    return f


def _text(text, weight, size, color, alpha=255):
    surf = _font(weight, size).render(text, True, color)
    if alpha < 255:
        surf.set_alpha(alpha)
    return surf


def _blit_centered(screen, surf, cx, cy):
    screen.blit(surf, (cx - surf.get_width() // 2, cy - surf.get_height() // 2))


def _ease_in_out(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


# ============================================================
# Achievement
# ============================================================

def _catherine_wheel(screen, elapsed, ctx):
    duration = 4.0
    w, h = screen.get_width(), screen.get_height()
    settle_start = duration * 0.85

    if elapsed < settle_start:
        t = elapsed / settle_start
        loops = 2.2
        window = 0.20  # fraction of perimeter the bright trace covers
        pos = (t * loops) % 1.0
        # draw_trace_progress only grows from 0 -- fake a moving window by
        # drawing the bright trace from 0 up to the window's leading edge,
        # then masking the trailing part (0 .. pos) back down to the dim
        # base color so only the [pos, pos+window] slice reads as bright.
        dim = (90, 70, 30)
        draw_trace_progress(screen, 0, 0, w, h, 1.0, dim, thickness=2, alpha=60)
        frac_end = min(1.0, pos + window)
        draw_trace_progress(screen, 0, 0, w, h, frac_end, GOLD, thickness=4, alpha=235)
        if pos > 0.005:
            draw_trace_progress(screen, 0, 0, w, h, pos, dim, thickness=4, alpha=200)
        if pos + window > 1.0:
            wrap_frac = (pos + window) - 1.0
            draw_trace_progress(screen, 0, 0, w, h, wrap_frac, GOLD, thickness=4, alpha=235)

        # sparks peeling off the leading edge
        seed = _seed_for(ctx)
        rng = random.Random(seed)
        leading = (pos + window) % 1.0
        px, py = _perim_point(leading, w, h)
        for i in range(6):
            a = rng.uniform(0, math.tau)
            life = rng.uniform(0.15, 0.35)
            phase = (elapsed * 3 + i * 0.37) % 1.0
            dist = phase * 40
            fade = max(0, 1 - phase)
            sx = px + math.cos(a) * dist
            sy = py + math.sin(a) * dist
            pygame.draw.circle(screen, (*GOLD, int(200 * fade)), (int(sx), int(sy)), 2)
    else:
        t = (elapsed - settle_start) / max(0.001, duration - settle_start)
        alpha = int(160 * (1.0 - t))
        draw_trace_progress(screen, 0, 0, w, h, 1.0, GOLD, thickness=2, alpha=max(0, alpha))


def _perim_point(t, w, h):
    perim = 2 * (w + h)
    d = (t % 1.0) * perim
    if d < w:
        return d, 0
    d -= w
    if d < h:
        return w, d
    d -= h
    if d < w:
        return w - d, h
    d -= w
    return 0, h - d


def _level_up_banner(screen, elapsed, ctx):
    ctx = ctx or {}
    label = ctx.get('label', 'LEVEL UP')
    value = ctx.get('value')
    w, h = screen.get_width(), screen.get_height()
    cy = h // 2

    land_time = 0.55
    shake_until = land_time + 0.15
    t = min(1.0, elapsed / land_time)
    e = ease_out_back(t)
    cx = int(w * 0.5 - (1.0 - e) * w * 0.6)
    jx = 0
    if elapsed < shake_until:
        jx = random.randint(-4, 4)

    banner = _text(label, 'bold', 64, COLOR_ACCENT_AMBER)
    fade = min(1.0, elapsed / 0.15)
    banner.set_alpha(int(255 * fade))
    _blit_centered(screen, banner, cx + jx, cy)

    if value is not None:
        tick_t = _ease_in_out(min(1.0, max(0.0, (elapsed - 0.2) / 0.8)))
        try:
            target = float(value)
        except (TypeError, ValueError):
            target = 0
        shown = int(target * tick_t)
        num = _text(str(shown), 'light', 36, COLOR_TEXT_SECONDARY)
        _blit_centered(screen, num, cx + jx, cy + 56)


def _countdown_zero_burst(screen, elapsed, ctx):
    ctx = ctx or {}
    w, h = screen.get_width(), screen.get_height()
    ox, oy = ctx.get('origin', (w // 2, h // 2))
    seed = _seed_for(ctx)
    rng = random.Random(seed)
    colors = [COLOR_ACCENT_AMBER, COLOR_ACCENT_BLUE, COLOR_ACCENT_GREEN, COLOR_ACCENT_PRIMARY]
    n = 48
    for i in range(n):
        a = (i / n) * math.tau + rng.uniform(-0.1, 0.1)
        speed = rng.uniform(140, 320)
        life = rng.uniform(1.2, 1.9)
        if elapsed > life:
            continue
        fade = 1.0 - (elapsed / life)
        vx = math.cos(a) * speed
        vy = math.sin(a) * speed
        x = ox + vx * elapsed
        y = oy + vy * elapsed + 0.5 * 260 * elapsed * elapsed
        color = colors[i % len(colors)]
        pygame.draw.circle(screen, (*color, max(0, int(230 * fade))), (int(x), int(y)), 3)


def _personal_best_fanfare(screen, elapsed, ctx):
    ctx = ctx or {}
    value = ctx.get('value', '')
    w = screen.get_width()
    top_y = int(screen.get_height() * 0.22)
    band_h = 90

    t = min(1.0, elapsed / 0.6)
    band_w = int(w * ease_out_cubic(t))
    if band_w > 0:
        band = pygame.Surface((band_w, band_h), pygame.SRCALPHA)
        band.fill((*DEEP_RED, 210))
        screen.blit(band, (w // 2 - band_w // 2, top_y))

    label_alpha = int(255 * min(1.0, max(0.0, (elapsed - 0.3) / 0.3)))
    if label_alpha > 0:
        label = _text("PERSONAL BEST", 'bold', 40, (255, 255, 255), label_alpha)
        _blit_centered(screen, label, w // 2, top_y + band_h // 2)

    if value and elapsed > 0.7:
        val_alpha = int(255 * min(1.0, (elapsed - 0.7) / 0.3))
        val = _text(str(value), 'light', 30, COLOR_TEXT_SECONDARY, val_alpha)
        _blit_centered(screen, val, w // 2, top_y + band_h + 30)


def _streak_fire(screen, elapsed, ctx):
    ctx = ctx or {}
    days = ctx.get('days', '?')
    w, h = screen.get_width(), screen.get_height()
    fx, fy = w - 90, h - 140

    duration = 6.0
    fade = 1.0
    if elapsed < 0.3:
        fade = elapsed / 0.3
    elif elapsed > duration - 0.5:
        fade = max(0.0, (duration - elapsed) / 0.5)

    layers = [
        ((235, 100, 40), 26, 0.0),
        ((245, 150, 50), 19, 0.6),
        ((250, 200, 90), 12, 1.3),
    ]
    for color, base_r, phase in layers:
        flick = 0.85 + 0.15 * math.sin(elapsed * 8 + phase)
        r = base_r * flick
        pts = [
            (fx, fy - r * 1.6),
            (fx - r * 0.55, fy - r * 0.2),
            (fx - r * 0.35, fy + r * 0.5),
            (fx, fy + r * 0.65),
            (fx + r * 0.35, fy + r * 0.5),
            (fx + r * 0.55, fy - r * 0.2),
        ]
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.polygon(surf, (*color, int(220 * fade)), pts)
        screen.blit(surf, (0, 0))

    label = _text(f"{days} DAY STREAK", 'regular', 18, COLOR_ACCENT_AMBER, int(255 * fade))
    _blit_centered(screen, label, fx, fy + 40)


# ============================================================
# News
# ============================================================

def _news_flash(screen, elapsed, ctx):
    ctx = ctx or {}
    headline = ctx.get('headline', 'BREAKING')
    duration = 2.8
    w, h = screen.get_width(), screen.get_height()
    bar_h = 70

    in_t = min(1.0, elapsed / 0.4)
    out_start = duration - 0.5
    if elapsed < out_start:
        reach = ease_out_cubic(in_t) * w
    else:
        out_t = min(1.0, (elapsed - out_start) / 0.5)
        reach = (1.0 - ease_out_cubic(out_t)) * w

    if reach > 0:
        top_bar = pygame.Surface((int(reach), bar_h), pygame.SRCALPHA)
        top_bar.fill((*DEEP_RED, 235))
        screen.blit(top_bar, (0, 0))
        bot_bar = pygame.Surface((int(reach), bar_h), pygame.SRCALPHA)
        bot_bar.fill((*DEEP_RED, 235))
        screen.blit(bot_bar, (w - int(reach), h - bar_h))

    label_t = min(1.0, max(0.0, (elapsed - 0.3) / 0.3))
    if elapsed < out_start - 0.2 and label_t > 0:
        tag = _text("NEWS FLASH", 'bold', 22, (255, 255, 255), int(255 * label_t))
        _blit_centered(screen, tag, w // 2, bar_h // 2)
        headline_surf = _font('bold', 46).render(headline or 'BREAKING', True, (255, 255, 255))
        scale = 0.7 + 0.3 * ease_out_cubic(label_t)
        sw, sh = max(1, int(headline_surf.get_width() * scale)), max(1, int(headline_surf.get_height() * scale))
        scaled = safe_smoothscale(headline_surf, (sw, sh))
        scaled.set_alpha(int(255 * label_t))
        _blit_centered(screen, scaled, w // 2, h // 2)


def _breaking_ticker_klaxon(screen, elapsed, ctx):
    duration = 1.0
    w, h = screen.get_width(), screen.get_height()
    band_y = h - 40
    t = elapsed / duration
    x = int(t * w)
    pulse = 0.5 + 0.5 * math.sin(elapsed * 30)
    glow = glow_sprite(90, COLOR_ACCENT_AMBER, int(120 * pulse), core_frac=0.2)
    screen.blit(glow, (x - glow.get_width() // 2, band_y - glow.get_height() // 2))


def _wire_service_static(screen, elapsed, ctx):
    w, h = screen.get_width(), screen.get_height()
    frame = int(elapsed / 0.08)
    rng = random.Random(frame * 7919)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for _ in range(28):
        y = rng.randint(0, h - 1)
        shade = rng.randint(120, 255)
        a = rng.randint(30, 120)
        pygame.draw.line(surf, (shade, shade, shade, a), (0, y), (w, y), rng.choice((1, 1, 2)))
    screen.blit(surf, (0, 0))


# ============================================================
# Financial
# ============================================================

def _coin(surf, x, y, r, rot):
    color = GOLD
    pygame.draw.ellipse(surf, (*color, 235), (x - r, y - r * 0.6, r * 2, r * 1.2))
    pygame.draw.ellipse(surf, (255, 235, 190, 180), (x - r * 0.5, y - r * 0.35, r, r * 0.5), 1)


def _money_rain(screen, elapsed, ctx):
    w, h = screen.get_width(), screen.get_height()
    duration = 3.0
    base_speed = h / duration
    seed = _seed_for(ctx)
    rng = random.Random(seed)
    n = 30
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for i in range(n):
        delay = rng.uniform(0, duration * 0.35)
        x0 = rng.uniform(0, w)
        speed = rng.uniform(base_speed * 0.8, base_speed * 1.2)
        drift = rng.uniform(-30, 30)
        r = rng.uniform(9, 15)
        t = elapsed - delay
        if t < 0:
            continue
        y = -20 + speed * t
        if y > h + 20:
            continue
        x = x0 + drift * t
        rot = t * rng.uniform(2, 5)
        _coin(surf, x, y, r, rot)
    screen.blit(surf, (0, 0))


def _crash_klaxon(screen, elapsed, ctx):
    lines = [
        "well, that happened",
        "to the moon! ...the other way",
        "buy the dip?",
        "it's just a paper loss",
        "diamond hands, i guess",
    ]
    line = _pick_once(ctx, '_line', lines)
    w, h = screen.get_width(), screen.get_height()
    pulse = flash_alpha_envelope(elapsed % 0.9) if elapsed < 1.2 else max(0, 1.0 - (elapsed - 1.2) / 0.8)
    wash = pygame.Surface((w, h), pygame.SRCALPHA)
    wash.fill((*DEEP_RED, int(45 * pulse)))
    screen.blit(wash, (0, 0))
    if elapsed > 0.3:
        cap_alpha = int(220 * min(1.0, (elapsed - 0.3) / 0.3))
        cap = _text(line, 'regular', 22, COLOR_TEXT_SECONDARY, cap_alpha)
        _blit_centered(screen, cap, w // 2, int(h * 0.5) + 60)


def _crypto_millionaire(screen, elapsed, ctx):
    ctx = ctx or {}
    price = ctx.get('price') or 'NEW HIGH'
    w, h = screen.get_width(), screen.get_height()
    duration = 3.5
    base_speed = h / duration
    seed = _seed_for(ctx)
    rng = random.Random(seed)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for i in range(26):
        delay = rng.uniform(0, duration * 0.35)
        x0 = rng.uniform(0, w)
        speed = rng.uniform(base_speed * 0.75, base_speed * 1.15)
        t = elapsed - delay
        if t < 0:
            continue
        y = -30 + speed * t
        if y > h + 20:
            continue
        color = GOLD if i % 2 == 0 else COLOR_ACCENT_GREEN
        glyph = _font('bold', 22).render("₿", True, color)
        glyph.set_alpha(220)
        surf.blit(glyph, (int(x0), int(y)))
    screen.blit(surf, (0, 0))

    t = min(1.0, elapsed / 0.5)
    scale = ease_out_back(t)
    label = _font('bold', 58).render(f"{price}", True, GOLD)
    if scale > 0:
        sw, sh = max(1, int(label.get_width() * scale)), max(1, int(label.get_height() * scale))
        scaled = safe_smoothscale(label, (sw, sh))
        _blit_centered(screen, scaled, w // 2, h // 2)


def _rocket_launch(screen, elapsed, ctx):
    duration = 3.0
    w, h = screen.get_width(), screen.get_height()
    t = min(1.0, elapsed / duration)
    prog = ease_out_cubic(t)
    y = h + 40 - prog * (h + 120)
    x = w * 0.5

    seed = _seed_for(ctx)
    rng = random.Random(seed + int(elapsed * 20))
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for _ in range(int(6 + prog * 14)):
        ex = x + rng.uniform(-6, 6)
        ey = y + 22 + rng.uniform(0, 30 + prog * 40)
        er = rng.uniform(2, 5)
        color = COLOR_ACCENT_AMBER if rng.random() < 0.6 else (255, 120, 60)
        pygame.draw.circle(surf, (*color, rng.randint(90, 200)), (int(ex), int(ey)), int(er))

    body_w, body_h = 22, 60
    pygame.draw.rect(surf, (225, 228, 232, 255), (x - body_w / 2, y - body_h / 2, body_w, body_h), border_radius=6)
    pygame.draw.polygon(surf, (225, 228, 232, 255), [
        (x - body_w / 2, y - body_h / 2), (x + body_w / 2, y - body_h / 2), (x, y - body_h / 2 - 26),
    ])
    fin_color = (*COLOR_ACCENT_BLUE, 255)
    pygame.draw.polygon(surf, fin_color, [
        (x - body_w / 2, y + body_h / 2 - 6), (x - body_w / 2 - 14, y + body_h / 2 + 16),
        (x - body_w / 2, y + body_h / 2 + 10),
    ])
    pygame.draw.polygon(surf, fin_color, [
        (x + body_w / 2, y + body_h / 2 - 6), (x + body_w / 2 + 14, y + body_h / 2 + 16),
        (x + body_w / 2, y + body_h / 2 + 10),
    ])
    screen.blit(surf, (0, 0))


def _market_open_bell(screen, elapsed, ctx):
    duration = 1.2
    w, h = screen.get_width(), screen.get_height()
    band_y = h - 40
    fade = flash_alpha_envelope(elapsed / duration * 0.5)
    glow = glow_sprite(int(w * 0.4), COLOR_ACCENT_GREEN, int(140 * fade), core_frac=0.15)
    screen.blit(glow, (w // 2 - glow.get_width() // 2, band_y - glow.get_height() // 2))
    alpha = int(255 * min(1.0, elapsed / 0.3) * max(0.0, 1.0 - max(0.0, (elapsed - 0.7) / 0.5)))
    if alpha > 0:
        label = _text("MARKET OPEN", 'bold', 24, COLOR_ACCENT_GREEN, max(0, min(255, alpha)))
        _blit_centered(screen, label, w // 2, band_y - 50)


# ============================================================
# Smarthome
# ============================================================

def _lockdown_sweep(screen, elapsed, ctx):
    duration = 2.5
    w, h = screen.get_width(), screen.get_height()
    t = elapsed / duration
    y = int(t * h)
    band = pygame.Surface((w, 140), pygame.SRCALPHA)
    for i in range(140):
        d = abs(i - 70) / 70.0
        a = max(0, int(70 * (1 - d)))
        pygame.draw.line(band, (*COLOR_ACCENT_BLUE, a), (0, i), (w, i))
    screen.blit(band, (0, y - 70))


def _stealth_mode(screen, elapsed, ctx):
    duration = 3.0
    w, h = screen.get_width(), screen.get_height()
    breathe = math.sin(elapsed / duration * math.pi)
    alpha = int(50 * max(0.0, breathe))
    if alpha <= 0:
        return
    vignette = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(vignette, (0, 0, 0, alpha), (0, 0, w, 40))
    pygame.draw.rect(vignette, (0, 0, 0, alpha), (0, h - 40, w, 40))
    pygame.draw.rect(vignette, (0, 0, 0, alpha), (0, 0, 40, h))
    pygame.draw.rect(vignette, (0, 0, 0, alpha), (w - 40, 0, 40, h))
    screen.blit(vignette, (0, 0))


def _motion_flash(screen, elapsed, ctx):
    ctx = ctx or {}
    side = ctx.get('side', 'left')
    w, h = screen.get_width(), screen.get_height()
    fade = flash_alpha_envelope(elapsed * 0.6)
    r = 140
    glow = glow_sprite(r, COLOR_ACCENT_AMBER, int(110 * fade), core_frac=0.2)
    pos = {
        'left': (0, h // 2),
        'right': (w, h // 2),
        'top': (w // 2, 0),
        'bottom': (w // 2, h),
    }.get(side, (0, h // 2))
    screen.blit(glow, (pos[0] - glow.get_width() // 2, pos[1] - glow.get_height() // 2))


def _front_door_welcome(screen, elapsed, ctx):
    duration = 2.5
    w, h = screen.get_width(), screen.get_height()
    t = elapsed / duration
    y = int(t * h)
    band = pygame.Surface((w, 160), pygame.SRCALPHA)
    for i in range(160):
        d = abs(i - 80) / 80.0
        a = max(0, int(55 * (1 - d)))
        pygame.draw.line(band, (*COLOR_ACCENT_AMBER, a), (0, i), (w, i))
    screen.blit(band, (0, y - 80))

    fade = min(1.0, elapsed / 0.4) * max(0.0, 1.0 - max(0.0, (elapsed - (duration - 0.6)) / 0.6))
    if fade > 0:
        label = _text("Welcome home", 'regular', 26, (255, 255, 255), int(220 * fade))
        _blit_centered(screen, label, w // 2, h // 2)


# ============================================================
# Registry
# ============================================================

_MOMENTS = [
    Moment("catherine_wheel", "achievement", _catherine_wheel,
           duration_s=4.0, cooldown_s=3600 * 20, weight=1.2,
           trigger_events=("fitbit_goal_hit",)),
    Moment("level_up_banner", "achievement", _level_up_banner,
           duration_s=2.5, cooldown_s=3600 * 8, weight=1.0,
           trigger_events=("milestone_hit",)),
    Moment("countdown_zero_burst", "achievement", _countdown_zero_burst,
           duration_s=2.0, cooldown_s=120.0, weight=1.0,
           trigger_events=("countdown_zero",)),
    Moment("personal_best_fanfare", "achievement", _personal_best_fanfare,
           duration_s=3.0, cooldown_s=3600 * 20, weight=1.0,
           trigger_events=("personal_best",)),
    Moment("streak_fire", "achievement", _streak_fire,
           duration_s=6.0, cooldown_s=3600 * 10, weight=0.8,
           trigger_events=("streak_milestone",)),

    Moment("news_flash", "news", _news_flash,
           duration_s=2.8, cooldown_s=300.0, weight=1.2,
           trigger_events=("breaking_news",)),
    Moment("breaking_ticker_klaxon", "news", _breaking_ticker_klaxon,
           duration_s=1.0, cooldown_s=300.0, weight=1.0,
           trigger_events=("breaking_news_preroll",)),
    Moment("wire_service_static", "news", _wire_service_static,
           duration_s=0.5, cooldown_s=1800.0, weight=0.6,
           trigger_events=("breaking_news_major",)),

    Moment("money_rain", "financial", _money_rain,
           duration_s=3.0, cooldown_s=600.0, weight=1.0,
           trigger_events=("stock_big_gain",)),
    Moment("crash_klaxon", "financial", _crash_klaxon,
           duration_s=2.0, cooldown_s=600.0, weight=1.0,
           trigger_events=("stock_big_drop",)),
    Moment("crypto_millionaire", "financial", _crypto_millionaire,
           duration_s=3.5, cooldown_s=3600 * 20, weight=1.2,
           trigger_events=("crypto_ath",)),
    Moment("rocket_launch", "financial", _rocket_launch,
           duration_s=3.0, cooldown_s=3600 * 20, weight=1.2,
           trigger_events=("rocket_stock_ath",)),
    Moment("market_open_bell", "financial", _market_open_bell,
           duration_s=1.2, cooldown_s=3600 * 20, weight=0.8,
           trigger_events=("market_open",)),

    Moment("lockdown_sweep", "smarthome", _lockdown_sweep,
           duration_s=2.5, cooldown_s=900.0, weight=1.0,
           trigger_events=("house_armed",)),
    Moment("stealth_mode", "smarthome", _stealth_mode,
           duration_s=3.0, cooldown_s=900.0, weight=1.0,
           trigger_events=("all_lights_off",)),
    Moment("motion_flash", "smarthome", _motion_flash,
           duration_s=1.0, cooldown_s=300.0, weight=1.0,
           trigger_events=("motion_detected",)),
    Moment("front_door_welcome", "smarthome", _front_door_welcome,
           duration_s=2.5, cooldown_s=600.0, weight=1.0,
           trigger_events=("arrived_home",)),
]


def register(director):
    for m in _MOMENTS:
        director.register(m)
