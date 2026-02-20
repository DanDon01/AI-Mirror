#!/usr/bin/env python
"""Test audio output hardware (speakers via pygame.mixer).

Pi-specific: requires speakers/monitor audio connected.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import run_test, TestResult

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_mixer_init():
    """Test that pygame.mixer initializes successfully."""
    import pygame

    pygame.mixer.quit()
    try:
        pygame.mixer.init(frequency=24000, size=-16, channels=1)
        info = pygame.mixer.get_init()
        pygame.mixer.quit()
        if info:
            return True, f"freq={info[0]}, size={info[1]}, channels={info[2]}"
        return False, "mixer init returned no info"
    except Exception as e:
        return False, str(e)


def test_sine_tone():
    """Generate and play a 440Hz sine tone for 1 second."""
    import pygame
    import numpy as np

    try:
        pygame.mixer.init(frequency=22050, size=-16, channels=1)
        sample_rate = 22050
        duration = 1.0
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        tone = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)

        sound = pygame.sndarray.make_sound(tone.reshape(-1, 1))
        sound.set_volume(0.5)
        sound.play()
        time.sleep(1.2)
        pygame.mixer.quit()
        return True, "played 440Hz tone for 1 second"
    except Exception as e:
        return False, str(e)


def test_sound_effect_file():
    """Load and play mirror_listening.mp3 from assets."""
    import pygame

    sound_file = os.path.join(_PROJECT_ROOT, "assets", "sound_effects", "mirror_listening.mp3")
    if not os.path.exists(sound_file):
        return False, f"file not found: {sound_file}"

    try:
        pygame.mixer.init()
        sound = pygame.mixer.Sound(sound_file)
        duration = sound.get_length()
        sound.set_volume(0.5)
        sound.play()
        time.sleep(min(duration, 3.0))
        pygame.mixer.quit()
        return True, f"played mirror_listening.mp3 ({duration:.1f}s)"
    except Exception as e:
        return False, str(e)


def test_tts_playback():
    """Generate TTS audio via gTTS and play it."""
    import pygame
    import tempfile

    try:
        from gtts import gTTS

        tts = gTTS(text="Audio test successful.", lang="en", slow=False)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tts.save(f.name)
            mp3_path = f.name

        pygame.mixer.init()
        sound = pygame.mixer.Sound(mp3_path)
        sound.set_volume(0.5)
        sound.play()
        time.sleep(min(sound.get_length(), 3.0))
        pygame.mixer.quit()
        os.unlink(mp3_path)
        return True, "gTTS playback successful"
    except Exception as e:
        return False, str(e)


def main():
    results = TestResult()

    print("Testing Audio Output (Speakers)...")
    print("-" * 50)
    print("  (You should hear sounds during this test)")
    print()

    run_test("pygame.mixer init", test_mixer_init, results)
    run_test("440Hz sine tone", test_sine_tone, results)
    run_test("Sound effect file", test_sound_effect_file, results)
    run_test("gTTS playback", test_tts_playback, results)

    return results.summary()


if __name__ == "__main__":
    sys.exit(main())
