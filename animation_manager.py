"""Animation manager for AI-Mirror.

Handles per-module fade transitions, state transitions between mirror
modes (active/screensaver/sleep), and a center-screen notification
queue that modules can push temporary messages to.
"""

import pygame
import logging
import time
from config import ANIMATION, TRANSPARENCY, COLOR_TEXT_PRIMARY, COLOR_TEXT_DIM

logger = logging.getLogger("Animation")


class AnimationManager:
    """Manages fade alphas, state transitions, and center notifications."""

    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height

        # Per-module fade state: name -> {alpha, target, speed}
        self._module_fades = {}

        # State transition
        self._transitioning = False
        self._transition_progress = 0.0
        self._transition_from = None
        self._transition_to = None
        self._transition_speed = 1000.0 / max(ANIMATION.get('state_transition_ms', 800), 1)

        # Notification queue
        self._notifications = []
        self._notification_font = None
        self._notification_small_font = None

        # Timing
        self._fade_speed = 1000.0 / max(ANIMATION.get('fade_duration_ms', 400), 1)
        self._notif_display_ms = ANIMATION.get('notification_display_ms', 5000)
        self._notif_fade_ms = ANIMATION.get('notification_fade_ms', 500)

        self._last_tick = time.time()

    def _ensure_fonts(self):
        if self._notification_font is None:
            from config import FONT_NAME, FONT_SIZE_BODY, FONT_SIZE_SMALL
            self._notification_font = pygame.font.SysFont(FONT_NAME, FONT_SIZE_BODY + 4)
            self._notification_small_font = pygame.font.SysFont(FONT_NAME, FONT_SIZE_SMALL)

    # ----- Module fades -----

    def _get_fade(self, name):
        if name not in self._module_fades:
            self._module_fades[name] = {
                'alpha': TRANSPARENCY,
                'target': TRANSPARENCY,
            }
        return self._module_fades[name]

    def show_module(self, name):
        """Fade a module in to full transparency."""
        fade = self._get_fade(name)
        fade['target'] = TRANSPARENCY

    def hide_module(self, name):
        """Fade a module out to invisible."""
        fade = self._get_fade(name)
        fade['target'] = 0

    def get_module_alpha(self, name):
        """Return the current alpha for a module (0-255)."""
        fade = self._get_fade(name)
        return int(fade['alpha'])

    def is_module_fading(self, name):
        fade = self._get_fade(name)
        return abs(fade['alpha'] - fade['target']) > 1

    # ----- State transitions -----

    def begin_state_transition(self, from_state, to_state):
        """Start a fade transition between mirror states."""
        self._transitioning = True
        self._transition_progress = 0.0
        self._transition_from = from_state
        self._transition_to = to_state
        logger.info(f"State transition: {from_state} -> {to_state}")

    def is_transitioning(self):
        return self._transitioning

    def get_transition_progress(self):
        """Return 0.0 to 1.0 progress through the current state transition."""
        return self._transition_progress

    # ----- Center notifications -----

    def push_notification(self, text, color=None, duration_ms=None):
        """Add a notification to the center display queue."""
        self._notifications.append({
            'text': text,
            'color': color or COLOR_TEXT_PRIMARY,
            'created': time.time(),
            'duration': (duration_ms or self._notif_display_ms) / 1000.0,
            'alpha': 0,
            'phase': 'fade_in',
        })
        logger.info(f"Notification pushed: {text}")

    # ----- Update -----

    def update(self, dt_ms=None):
        """Advance all animations. Call once per frame.

        Args:
            dt_ms: delta time in milliseconds. If None, calculated from wall clock.
        """
        now = time.time()
        if dt_ms is None:
            dt_ms = (now - self._last_tick) * 1000.0
        self._last_tick = now
        dt_s = dt_ms / 1000.0

        # Module fades
        step = self._fade_speed * dt_ms
        for name, fade in self._module_fades.items():
            if fade['alpha'] < fade['target']:
                fade['alpha'] = min(fade['alpha'] + step, fade['target'])
            elif fade['alpha'] > fade['target']:
                fade['alpha'] = max(fade['alpha'] - step, fade['target'])

        # State transition
        if self._transitioning:
            self._transition_progress += self._transition_speed * dt_ms / 1000.0
            if self._transition_progress >= 1.0:
                self._transition_progress = 1.0
                self._transitioning = False
                logger.info(f"State transition complete: {self._transition_to}")

        # Notifications
        fade_s = self._notif_fade_ms / 1000.0
        alive = []
        for notif in self._notifications:
            age = now - notif['created']

            if notif['phase'] == 'fade_in':
                notif['alpha'] = min(255, int(255 * (age / fade_s)))
                if age >= fade_s:
                    notif['phase'] = 'display'
                    notif['alpha'] = 255

            elif notif['phase'] == 'display':
                if age >= notif['duration'] - fade_s:
                    notif['phase'] = 'fade_out'

            elif notif['phase'] == 'fade_out':
                remaining = notif['duration'] - age
                if remaining <= 0:
                    continue  # Remove from list
                notif['alpha'] = max(0, int(255 * (remaining / fade_s)))

            alive.append(notif)
        self._notifications = alive

    # ----- Drawing -----

    def draw_notifications(self, screen):
        """Render active notifications centered in the upper third of the screen."""
        if not self._notifications:
            return

        self._ensure_fonts()

        # Position in upper third (above face reflection area)
        center_x = self.screen_width // 2
        start_y = self.screen_height // 4

        for i, notif in enumerate(self._notifications[:3]):
            text = notif['text']
            color = notif['color']
            alpha = notif['alpha']

            surf = self._notification_font.render(text, True, color)
            surf.set_alpha(alpha)

            text_x = center_x - surf.get_width() // 2
            text_y = start_y + i * (surf.get_height() + 10)

            screen.blit(surf, (text_x, text_y))
