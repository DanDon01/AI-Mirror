"""Avatar talking-head module for AI-Mirror - "Holly" style.

Renders a realistic human face floating on black (semi-transparent, like
the Red Dwarf ship computer) from a set of pre-rendered face frames in
assets/avatar/. Real-time neural rendering is not feasible on a Pi 5, but
Holly never needed it: the look is a mostly-static face that blinks,
smiles, and moves its mouth while speaking. Frame compositing at 30 FPS
does that perfectly.

Face frames (PNG, same size, head centered identically, on transparent
or pure black background):
    neutral.png      REQUIRED  eyes open, mouth closed
    blink.png        optional  same face, eyes closed
    smile.png        optional  same face, smiling
    mouth_small.png  optional  mouth slightly open
    mouth_open.png   optional  mouth open (ah)
    mouth_wide.png   optional  mouth wide open
    mouth_round.png  optional  rounded mouth (oo/oh)

Generate them by photographing a real face pulling each shape, or from a
single AI-generated/real photo using LivePortrait (open source, runs
offline on the dev PC) which has explicit eye-close and lip-open
retargeting. More frames = smoother mouth; even just neutral + open
reads as talking.

Lipsync: the voice playback thread calls feed_audio(pcm); loudness (RMS)
picks how open the mouth is, zero-crossing rate separates hissy
consonants from open vowels. Blinks are random (2-6 s), a smile plays
when the conversation ends.

Falls back to a simple procedural face if no frames are found, so the
module still works before assets exist.

Wiring (done in AI-Mirror.py):
    voice.set_audio_sink(avatar.feed_audio)
    voice.set_state_listener(avatar.set_voice_state)
"""

import logging
import math
import os
import random
import time
from collections import deque

import pygame

logger = logging.getLogger("Avatar")

try:
    import numpy as np
except ImportError:
    np = None

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ASSETS_PATH = os.path.join(_PROJECT_DIR, "assets", "avatar")

# Envelope analysis window (seconds of audio per mouth sample)
WINDOW_SEC = 0.025
SAMPLE_RATE = 24000

# How long the face stays visible after the conversation ends
LINGER_SEC = 5.0

# Fallback procedural palette (matches the mirror's clock cyan)
COLOR_FACE = (90, 195, 255)
COLOR_FACE_DIM = (45, 95, 125)
COLOR_MOUTH_FILL = (15, 40, 55)

FRAME_FILES = {
    "neutral": "neutral.png",
    "blink": "blink.png",
    "smile": "smile.png",
    "small": "mouth_small.png",
    "open": "mouth_open.png",
    "wide": "mouth_wide.png",
    "round": "mouth_round.png",
}


class AvatarModule:
    def __init__(self, size=420, assets_path=None, transparency=205,
                 scanlines=True, **kwargs):
        """
        Args:
            size: max face height/width in pixels.
            assets_path: folder of face frame PNGs (default assets/avatar).
            transparency: 0-255 alpha while speaking (semi-transparent
                          ghost look; idle is drawn slightly fainter).
            scanlines: subtle CRT scanline overlay for the retro look.
        """
        self.size = size
        self.assets_path = assets_path or DEFAULT_ASSETS_PATH
        self.transparency = transparency
        self.scanlines = scanlines

        self.state = "hidden"
        self.alpha = 0.0          # fade 0..1
        self._last_active = 0.0
        self._last_frame = time.monotonic()

        # Lipsync envelope: deque of (rms, zcr) samples, one per WINDOW_SEC
        self._envelope = deque(maxlen=2000)
        self._env_clock = 0.0
        self._level_max = 1500.0  # running loudness ceiling for normalisation
        self._openness = 0.0      # smoothed mouth openness 0..1
        self._narrow = 0.0        # smoothed narrowing 0..1 (fricatives)

        # Idle behaviours
        self._blink_until = 0.0
        self._next_blink = time.monotonic() + random.uniform(2.0, 5.0)
        self._think_phase = 0.0
        self._smile_until = 0.0

        # Face frames (raw and scaled-to-zone caches)
        self._frames = {}
        self._scaled = {}
        self._scaled_size = None
        self._scanline_surf = None
        self._load_frames()

        self._surface = None  # procedural fallback canvas

    # ------------------------------------------------------------------
    # Frame loading
    # ------------------------------------------------------------------

    def _load_frames(self):
        if not os.path.isdir(self.assets_path):
            logger.warning(
                f"No avatar frames at {self.assets_path} - using procedural "
                f"fallback face. Drop PNGs there for the realistic look "
                f"(see assets/avatar/README.txt)."
            )
            return
        for key, fname in FRAME_FILES.items():
            path = os.path.join(self.assets_path, fname)
            if os.path.exists(path):
                try:
                    self._frames[key] = pygame.image.load(path)
                except Exception as e:
                    logger.error(f"Failed to load avatar frame {fname}: {e}")
        if "neutral" not in self._frames:
            if self._frames:
                logger.error(
                    "avatar frames found but neutral.png is missing - "
                    "procedural fallback in use"
                )
            self._frames = {}
        else:
            logger.info(
                f"Avatar frames loaded: {sorted(self._frames.keys())}"
            )

    @property
    def has_face(self):
        return bool(self._frames)

    def _get_scaled(self, key, target_h):
        """Return the frame scaled to fit the zone, cached per size."""
        if self._scaled_size != target_h:
            self._scaled = {}
            self._scaled_size = target_h
        surf = self._scaled.get(key)
        if surf is None:
            raw = self._frames[key]
            scale = target_h / raw.get_height()
            w = max(1, int(raw.get_width() * scale))
            surf = pygame.transform.smoothscale(raw, (w, target_h))
            # convert_alpha needs a display; tolerate headless test runs
            try:
                surf = surf.convert_alpha()
            except pygame.error:
                pass
            self._scaled[key] = surf
        return surf

    # ------------------------------------------------------------------
    # Inputs from the voice module
    # ------------------------------------------------------------------

    def set_voice_state(self, status):
        """Map voice module status strings onto avatar states."""
        status = (status or "").lower()
        prev = self.state
        if status == "listening":
            self.state = "listening"
        elif status in ("processing", "sending", "responding"):
            self.state = "thinking"
        elif status == "speaking":
            self.state = "speaking"
        elif status in ("ready", "idle"):
            if self.state != "hidden":
                self.state = "idle"
                self._last_active = time.monotonic()
                if prev == "speaking":
                    # Holly signs off with a smile
                    self._smile_until = time.monotonic() + 2.5
        elif status == "error":
            self.state = "idle"
            self._last_active = time.monotonic()

        if self.state in ("listening", "thinking", "speaking"):
            self._last_active = time.monotonic()

    def feed_audio(self, pcm_bytes, sample_rate=SAMPLE_RATE):
        """Analyse a 16-bit mono PCM chunk into mouth envelope samples.

        Called from the voice playback thread as each chunk is scheduled,
        so the envelope leads the heard audio by at most one chunk.
        """
        try:
            if np is None or len(pcm_bytes) < 4:
                return
            samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
            window = max(1, int(sample_rate * WINDOW_SEC))
            for i in range(0, len(samples) - window + 1, window):
                seg = samples[i:i + window]
                rms = float(np.sqrt(np.mean(seg * seg)))
                zcr = float(np.mean(np.abs(np.diff(np.sign(seg))) > 0))
                self._envelope.append((rms, zcr))
        except Exception as e:
            logger.debug(f"feed_audio error: {e}")

    # ------------------------------------------------------------------
    # Module interface
    # ------------------------------------------------------------------

    def update(self):
        now = time.monotonic()
        dt = min(now - self._last_frame, 0.1)
        self._last_frame = now

        visible = self.state in ("listening", "thinking", "speaking") or (
            self.state == "idle" and now - self._last_active < LINGER_SEC
        )
        target = 1.0 if visible else 0.0
        speed = 2.5 * dt
        self.alpha += max(-speed, min(speed, target - self.alpha))
        if self.alpha <= 0.01 and self.state == "idle":
            self.state = "hidden"
            self._envelope.clear()
            self._env_clock = 0.0

        if now >= self._next_blink:
            self._blink_until = now + 0.13
            self._next_blink = now + random.uniform(2.0, 6.0)

        self._think_phase += dt

        # Consume envelope in real time while speaking
        target_open = 0.0
        target_narrow = 0.0
        if self.state == "speaking" and self._envelope:
            self._env_clock += dt
            consumed = None
            while self._envelope and self._env_clock >= WINDOW_SEC:
                consumed = self._envelope.popleft()
                self._env_clock -= WINDOW_SEC
            if consumed:
                rms, zcr = consumed
                self._level_max = max(self._level_max * 0.999, rms, 500.0)
                target_open = min(1.0, rms / self._level_max)
                target_narrow = min(1.0, max(0.0, zcr * 1.8 - 0.3))

        rate = 18.0 if target_open > self._openness else 10.0
        self._openness += (target_open - self._openness) * min(1.0, rate * dt)
        self._narrow += (target_narrow - self._narrow) * min(1.0, 8.0 * dt)

    def _pick_frame(self, now):
        """Choose which face frame to show this frame."""
        if now < self._blink_until and "blink" in self._frames:
            return "blink"
        if self.state == "speaking":
            o = self._openness
            if o < 0.12:
                return "neutral"
            # Hissy consonants and oo-sounds use the narrower shapes
            if self._narrow > 0.55 and "small" in self._frames:
                return "small"
            if o < 0.35:
                return self._first_available("small", "round", "open")
            if o < 0.7:
                if self._narrow < 0.25 and "round" in self._frames and o < 0.5:
                    return "round"
                return self._first_available("open", "wide", "small")
            return self._first_available("wide", "open", "small")
        if now < self._smile_until and "smile" in self._frames:
            return "smile"
        if self.state == "listening" and "smile" in self._frames:
            # Attentive half-smile while listening
            return "smile" if (int(now) % 8) < 2 else "neutral"
        return "neutral"

    def _first_available(self, *keys):
        for k in keys:
            if k in self._frames:
                return k
        return "neutral"

    def draw(self, screen, position):
        try:
            if self.alpha <= 0.01:
                return

            if isinstance(position, dict):
                x, y = position.get('x', 0), position.get('y', 0)
                width = position.get('width', self.size)
                height = position.get('height', self.size)
            else:
                x, y = position
                width = height = self.size

            if self.has_face:
                self._draw_face_frames(screen, x, y, width, height)
            else:
                self._draw_procedural(screen, x, y, width, height)
        except Exception as e:
            logger.error(f"Avatar draw error: {e}")

    # ------------------------------------------------------------------
    # Realistic frame compositing (the Holly look)
    # ------------------------------------------------------------------

    def _draw_face_frames(self, screen, x, y, width, height):
        now = time.monotonic()
        target_h = min(height, self.size)
        frame = self._get_scaled(self._pick_frame(now), target_h)

        # Slow drift so the face feels alive, never static
        bob_y = math.sin(now * 0.9) * 3
        bob_x = math.sin(now * 0.6) * 2

        fx = x + (width - frame.get_width()) // 2 + int(bob_x)
        fy = y + (height - target_h) // 2 + int(bob_y)

        # Semi-transparent ghost-on-glass: fainter when idle
        base_alpha = self.transparency if self.state == "speaking" else int(self.transparency * 0.82)
        frame.set_alpha(int(base_alpha * self.alpha))
        screen.blit(frame, (fx, fy))

        if self.scanlines:
            self._draw_scanlines(screen, fx, fy, frame.get_width(), target_h)

        if self.state == "thinking":
            self._draw_thinking_dots(screen, x + width // 2, fy + target_h + 18, now)

    def _draw_scanlines(self, screen, x, y, w, h):
        """Faint CRT scanlines over the face for the retro monitor look."""
        if (self._scanline_surf is None
                or self._scanline_surf.get_size() != (w, h)):
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            for ly in range(0, h, 3):
                pygame.draw.line(surf, (0, 0, 0, 60), (0, ly), (w, ly))
            self._scanline_surf = surf
        self._scanline_surf.set_alpha(int(110 * self.alpha))
        screen.blit(self._scanline_surf, (x, y))

    def _draw_thinking_dots(self, screen, cx, dy, now):
        for i in (-1, 0, 1):
            phase = math.sin(self._think_phase * 4.0 - i * 0.9)
            a = int((90 + 100 * max(0.0, phase)) * self.alpha)
            dot = pygame.Surface((8, 8), pygame.SRCALPHA)
            pygame.draw.circle(dot, (*COLOR_FACE, a), (4, 4), 3)
            screen.blit(dot, (cx + i * 18 - 4, dy))

    # ------------------------------------------------------------------
    # Procedural fallback (used until face frames exist)
    # ------------------------------------------------------------------

    def _draw_procedural(self, screen, x, y, width, height):
        s = min(width, height, self.size)
        if self._surface is None or self._surface.get_width() != s:
            self._surface = pygame.Surface((s, s), pygame.SRCALPHA)
        surf = self._surface
        surf.fill((0, 0, 0, 0))

        cx, cy = s // 2, s // 2
        now = time.monotonic()
        head_r = int(s * 0.38)
        head_cy = int(cy + math.sin(now * 1.3) * s * 0.008)

        pygame.draw.circle(surf, (*COLOR_FACE, 200), (cx, head_cy), head_r, 2)

        # Eyes
        eye_dx = int(head_r * 0.42)
        eye_y = head_cy - int(head_r * 0.18)
        eye_w = max(4, int(head_r * 0.16))
        eye_h = max(4, int(head_r * 0.22))
        if now < self._blink_until:
            eye_h = max(2, eye_h // 6)
        for side in (-1, 1):
            rect = pygame.Rect(
                cx + side * eye_dx - eye_w // 2, eye_y - eye_h // 2, eye_w, eye_h
            )
            pygame.draw.ellipse(surf, (*COLOR_FACE, 230), rect)

        # Mouth
        mouth_y = head_cy + int(head_r * 0.4)
        base_w = int(head_r * 0.62)
        if self.state == "speaking":
            open_h = int(2 + self._openness * head_r * 0.34)
            w = int(base_w * (1.0 - 0.35 * self._narrow))
            rect = pygame.Rect(cx - w // 2, mouth_y - open_h // 2, w, open_h)
            if open_h > 5:
                pygame.draw.ellipse(surf, (*COLOR_MOUTH_FILL, 220), rect)
                pygame.draw.ellipse(surf, (*COLOR_FACE, 220), rect, 2)
            else:
                pygame.draw.line(surf, (*COLOR_FACE, 220),
                                 (cx - w // 2, mouth_y), (cx + w // 2, mouth_y), 2)
        else:
            rect = pygame.Rect(cx - base_w // 2, mouth_y - int(head_r * 0.18),
                               base_w, int(head_r * 0.32))
            pygame.draw.arc(surf, (*COLOR_FACE, 200), rect,
                            math.pi * 1.15, math.pi * 1.85, 2)

        if self.state == "thinking":
            self._draw_thinking_dots(screen, x + width // 2,
                                     y + (height + s) // 2 + 10, now)

        surf.set_alpha(int(self.alpha * 255))
        screen.blit(surf, (x + (width - s) // 2, y + (height - s) // 2))

    def cleanup(self):
        pass
