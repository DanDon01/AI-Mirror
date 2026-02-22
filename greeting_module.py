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
    TRANSPARENCY,
)
from module_base import ModuleDrawHelper, SurfaceCache

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


class GreetingModule:
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
        try:
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', 300)
                height = position.get('height', 300)
            else:
                x, y = position
                width, height = 300, 300

            if self.title_font is None:
                title_f, body_f, small_f = ModuleDrawHelper.get_fonts()
                self.title_font = title_f
                self.body_font = body_f
                self.small_font = small_f

            draw_y = ModuleDrawHelper.draw_module_title(
                screen, "Mirror", x, y, width
            )

            data_hash = f"{self.current_greeting}|{self.current_affirmation}"

            if self.current_greeting:
                def _render_greeting(text=self.current_greeting):
                    surf = self.body_font.render(text, True, COLOR_TEXT_PRIMARY)
                    surf.set_alpha(TRANSPARENCY)
                    return surf

                greeting_surf = self._surface_cache.get_or_render(
                    "greeting", _render_greeting, data_hash
                )
                screen.blit(greeting_surf, (x, draw_y))
                draw_y += greeting_surf.get_height() + 8

            if self.current_affirmation:
                # Word-wrap the affirmation to fit the column width
                words = self.current_affirmation.split()
                lines = []
                current_line = ""
                for word in words:
                    test = f"{current_line} {word}".strip()
                    test_w = self.small_font.size(test)[0]
                    if test_w > width - 4:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                    else:
                        current_line = test
                if current_line:
                    lines.append(current_line)

                for i, line in enumerate(lines):
                    if draw_y > y + height - 20:
                        break

                    def _render_line(text=line, idx=i):
                        surf = self.small_font.render(text, True, COLOR_TEXT_SECONDARY)
                        surf.set_alpha(TRANSPARENCY)
                        return surf

                    line_surf = self._surface_cache.get_or_render(
                        f"affirm_{i}", _render_line, data_hash
                    )
                    screen.blit(line_surf, (x, draw_y))
                    draw_y += line_surf.get_height() + 2

        except Exception as e:
            logger.error(f"Error drawing greeting module: {e}")

    def cleanup(self):
        pass
