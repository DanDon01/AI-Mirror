"""The Moments library -- registers every themed moment with the Director.

Each category lives in its own module (moments_weather.py, moments_life.py,
moments_fun.py, moments_arcade.py, moments_seasonal.py) with a
`register(director)` entry point; this file just calls all of them, so
the Director and individual category files never need to know about
each other.
"""

import logging

from effects_kit import glow_sprite, ease_out_cubic
from event_director import Moment

logger = logging.getLogger("Moments")

_ACCENT = (196, 174, 128)


def _render_placeholder_pulse(screen, elapsed, ctx):
    """A soft glow pulse at center -- proves the Director can draw over
    everything (including center) and that timed easing works."""
    duration = 2.5
    t = min(elapsed / duration, 1.0)
    if t < 0.3:
        alpha_t = ease_out_cubic(t / 0.3)
    elif t < 0.7:
        alpha_t = 1.0
    else:
        alpha_t = 1.0 - ease_out_cubic((t - 0.7) / 0.3)

    radius = max(8, int(min(screen.get_width(), screen.get_height()) * 0.06))
    glow = glow_sprite(radius, _ACCENT, int(180 * alpha_t), core_frac=0.25)
    cx, cy = screen.get_width() // 2, screen.get_height() // 2
    screen.blit(glow, (cx - glow.get_width() // 2, cy - glow.get_height() // 2))


def _register_phase1(director):
    director.register(Moment(
        name="placeholder_pulse",
        category="system",
        render=_render_placeholder_pulse,
        duration_s=2.5,
        cooldown_s=60.0,
        weight=1.0,
        # No ambient trigger yet -- only fires via notify('director_test')
        # or a manual web-panel trigger, so it never surprises the user
        # before real moments exist.
        trigger_events=("director_test",),
    ))


_CATEGORY_MODULES = (
    "moments_weather",
    "moments_life",
    "moments_fun",
    "moments_arcade",
    "moments_seasonal",
)


def register_all(director):
    _register_phase1(director)
    for name in _CATEGORY_MODULES:
        try:
            module = __import__(name)
            module.register(director)
        except Exception:
            logger.exception("Failed to register moments from %s", name)
    logger.info("Moments registered: %d", len(director.moment_names()))
