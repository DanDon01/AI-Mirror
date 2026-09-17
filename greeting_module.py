"""Greeting module for AI-Mirror.

Displays time-based greetings and rotating compliments/affirmations.
No API needed -- purely local content that adds personality to the mirror.
"""

import logging
import random
from datetime import datetime, timedelta

import pygame

from config import (
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_ACCENT_BLUE,
    TRANSPARENCY, load_font,
    COLOR_TEXT_DIM,)
from module_base import ModuleDrawHelper, SurfaceCache, InstrumentPanel

logger = logging.getLogger("Greeting")

GREETINGS = {
    'morning': [
        "Good morning",
        "Rise and shine",
        "Morning",
        "Top of the morning",
    ],
    'afternoon': [
        "Good afternoon",
        "Afternoon",
        "Hey there",
    ],
    'evening': [
        "Good evening",
        "Evening",
        "Welcome home",
    ],
    'night': [
        "Goodnight",
        "Sleep well",
        "Rest easy",
    ],
}

AFFIRMATIONS = [
    "You look great today.",
    "Today is going to be a good day.",
    "Make it happen.",
    "Stay focused, stay sharp.",
    "One step at a time.",
    "Keep going, you are doing well.",
    "Be the reason someone smiles.",
    "Your only limit is you.",
    "Trust the process.",
    "Small progress is still progress.",
    "Breathe. You have got this.",
    "Today is full of possibility.",
    "Start where you are.",
    "Be kind to yourself.",
    "You are stronger than you think.",
    "Do something today your future self will thank you for.",
    "The best time to start is now.",
    "Believe in yourself.",
    "Every day is a fresh start.",
    "You are enough.",
]


def _get_time_period():
    """Return time period: morning (5-12), afternoon (12-17), evening (17-21), night (21-5)."""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return 'morning'
    if 12 <= hour < 17:
        return 'afternoon'
    if 17 <= hour < 21:
        return 'evening'
    return 'night'


class GreetingModule(InstrumentPanel):
    def __init__(self, rotation_interval=60, **kwargs):
        self.rotation_interval = timedelta(seconds=rotation_interval)
        self.last_rotation = datetime.min
        self.current_greeting = ""
        self.current_affirmation = ""
        self._surface_cache = SurfaceCache()
        self._last_period = None
        self._affirmation_index = 0

        # Shuffle affirmations so they feel random but don't repeat until cycled
        self._shuffled = list(AFFIRMATIONS)
        random.shuffle(self._shuffled)

        self.title_font = None
        self.body_font = None
        self.small_font = None

    def update(self):
        now = datetime.now()
        period = _get_time_period()

        # Rotate greeting when time period changes or on interval
        needs_update = (
            period != self._last_period
            or now - self.last_rotation >= self.rotation_interval
        )

        if needs_update:
            self._last_period = period
            self.current_greeting = random.choice(GREETINGS[period])
            self.current_affirmation = self._shuffled[self._affirmation_index]
            self._affirmation_index = (self._affirmation_index + 1) % len(self._shuffled)
            if self._affirmation_index == 0:
                random.shuffle(self._shuffled)
            self.last_rotation = now

    def draw(self, screen, position):
        """A greeting is text by nature -- it gets the house typography and
        rule, not a gauge."""
        self.draw_instrument(screen, position, default=(300, 200))

    def _render_panel(self, surf, width, height, position=None):
        import theme
        accent = theme.module_accent('greeting')
        pad = 6
        ix, iw = pad, width - pad * 2
        cur = 4

        if self.current_greeting:
            hero = self._text('f_big', str(self.current_greeting), COLOR_TEXT_PRIMARY)
            surf.blit(hero, (ix + iw - hero.get_width(), cur))
            cur += hero.get_height() + 4
            lead = int(iw * 0.34)
            pygame.draw.line(surf, (*accent, 45), (ix, cur), (ix + iw - lead, cur), 1)
            pygame.draw.line(surf, (*accent, 170), (ix + iw - lead, cur), (ix + iw, cur), 1)
            cur += 7

        if self.current_affirmation and cur + 14 < height:
            for line in self._wrap_text(str(self.current_affirmation), iw):
                if cur + 14 > height:
                    break
                ls = self._text('f_nano', line.upper(), COLOR_TEXT_DIM, spacing=1)
                surf.blit(ls, (ix + iw - ls.get_width(), cur))
                cur += 13

    def _wrap_text(self, text, max_w):
        font = self.f_nano
        words, lines, line = text.split(), [], ""
        for word in words:
            trial = f"{line} {word}".strip()
            if font.size(trial.upper())[0] <= max_w or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
        return lines[:3]


    def cleanup(self):
        pass
