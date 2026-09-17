"""The Moments Director for AI-Mirror.

A whole-display event system that sits above every module and can
temporarily take over any zone -- including the center -- for rare,
short, theatrical "moments": a Fitbit goal turning the screen border
into a catherine wheel, a storm bolt whiting out the whole mirror,
HAL's red eye drifting across for no reason at all. See the project
plan for the full moment library and phasing.

Two rules keep this from getting stale for someone who sees the mirror
every day:
  - Every moment has a cooldown and competes in a weighted random pick
    against a global minimum gap and a soft daily cap.
  - A short "recently played" history heavily discounts a moment that
    just played, so the same gag doesn't repeat back-to-back.

Modules call `director.notify(event_type, payload)` on anything that
might be moment-worthy (a goal hit, a lightning bolt, a big price
move, ...). Moments with no `trigger_events` are pure ambient whimsy --
they enter the idle random pool instead of waiting for a specific event.
"""

import logging
import random
import time
from collections import deque

logger = logging.getLogger("Director")


class Moment:
    """One entry in the moment library.

    `render(screen, elapsed, ctx)` draws the moment for the given number
    of seconds since it started; `ctx` is whatever payload was passed to
    notify()/force_trigger(), or None for ambient/random moments.
    """

    def __init__(self, name, category, render, duration_s=4.0,
                 cooldown_s=120.0, weight=1.0, trigger_events=None,
                 on_start=None):
        self.name = name
        self.category = category
        self.render = render
        self.duration_s = duration_s
        self.cooldown_s = cooldown_s
        self.weight = weight
        self.trigger_events = frozenset(trigger_events or ())
        self.on_start = on_start
        self.last_played = -1e9


class Director:
    """Owns the moment registry, decides what plays when, draws the
    active moment on top of everything else."""

    def __init__(self, screen_width, screen_height, config=None):
        self.screen_width = screen_width
        self.screen_height = screen_height
        cfg = config or {}
        self.enabled = cfg.get('enabled', True)
        self.frequency = max(0.05, cfg.get('frequency', 1.0))
        self.min_gap_s = cfg.get('min_gap_s', 240.0)
        self.daily_cap = cfg.get('daily_cap', 40)
        # Guests over: moments fire much more eagerly for as long as this
        # stays on (a shorter gap and a livelier idle roll), independent of
        # force_trigger/trigger_random which fire a single moment on demand.
        self.guest_mode = cfg.get('guest_mode', False)
        self._guest_gap_divisor = 6.0
        self._guest_idle_multiplier = 5.0

        self._moments = {}
        self._pending_events = []
        self._recent = deque(maxlen=cfg.get('recent_history', 6))
        self._active = None
        self._active_started = 0.0
        self._active_ctx = None
        self._last_played_at = -1e9
        self._played_today = 0
        self._day = time.localtime().tm_yday

    def register(self, moment):
        self._moments[moment.name] = moment

    def notify(self, event_type, payload=None):
        """A module reports something that might be moment-worthy.
        Cheap and safe to call every frame something changes -- events
        are only consulted when the Director is next idle."""
        if self.enabled:
            self._pending_events.append((event_type, payload))

    def force_trigger(self, name):
        """Play a specific moment right now, ignoring cooldown/gap/cap
        (the web panel's manual "guest mode" button)."""
        if self._active is not None:
            return False
        moment = self._moments.get(name)
        if moment is None:
            return False
        self._start(moment, None)
        return True

    def trigger_random(self):
        """Play any registered moment right now, ignoring cooldown/gap/cap."""
        if self._active is not None or not self._moments:
            return False
        self._start(self._weighted_pick(list(self._moments.values())), None)
        return True

    def moment_names(self):
        return sorted(self._moments.keys())

    # ----- eligibility -----

    def _cooldown_ok(self, moment):
        return (time.time() - moment.last_played) >= moment.cooldown_s

    def _weighted_pick(self, candidates):
        weights = [
            m.weight * (0.15 if m.name in self._recent else 1.0)
            for m in candidates
        ]
        return random.choices(candidates, weights=weights, k=1)[0]

    def _reset_daily_cap_if_new_day(self):
        today = time.localtime().tm_yday
        if today != self._day:
            self._day = today
            self._played_today = 0

    # ----- lifecycle -----

    def _start(self, moment, payload):
        self._active = moment
        self._active_started = time.time()
        self._active_ctx = payload
        moment.last_played = time.time()
        self._last_played_at = time.time()
        self._played_today += 1
        self._recent.append(moment.name)
        if moment.on_start:
            try:
                moment.on_start(payload)
            except Exception:
                logger.exception("Moment %s on_start failed", moment.name)
        logger.info("Moment started: %s", moment.name)

    def update(self):
        """Advance the active moment, or decide whether a new one should
        start. Call once per frame regardless of mirror state."""
        if not self.enabled:
            self._pending_events.clear()
            return
        self._reset_daily_cap_if_new_day()

        if self._active is not None:
            if time.time() - self._active_started >= self._active.duration_s:
                logger.info("Moment ended: %s", self._active.name)
                self._active = None
                self._active_ctx = None
            return

        events, self._pending_events = self._pending_events, []

        # Guest mode ignores the daily cap entirely (a party is exactly
        # the day the cap would otherwise start throttling things).
        if self._played_today >= self.daily_cap and not self.guest_mode:
            return
        gap = self.min_gap_s / self.frequency
        if self.guest_mode:
            gap /= self._guest_gap_divisor
        if time.time() - self._last_played_at < gap:
            return

        # Event-triggered candidates take priority over ambient whimsy.
        for event_type, payload in events:
            candidates = [
                m for m in self._moments.values()
                if event_type in m.trigger_events and self._cooldown_ok(m)
            ]
            if candidates:
                self._start(self._weighted_pick(candidates), payload)
                return

        # Ambient/whimsy moments (no specific trigger) compete for idle
        # airtime -- scaled so they stay a rare surprise, not a tic.
        idle_chance = 0.0006 * self.frequency
        if self.guest_mode:
            idle_chance *= self._guest_idle_multiplier
        if random.random() < idle_chance:
            candidates = [
                m for m in self._moments.values()
                if not m.trigger_events and self._cooldown_ok(m)
            ]
            if candidates:
                self._start(self._weighted_pick(candidates), None)

    def draw(self, screen):
        if self._active is None:
            return
        elapsed = time.time() - self._active_started
        try:
            self._active.render(screen, elapsed, self._active_ctx)
        except Exception:
            logger.exception("Moment %s render failed -- ending it", self._active.name)
            self._active = None

    @property
    def is_active(self):
        return self._active is not None

    @property
    def active_name(self):
        return self._active.name if self._active else None
