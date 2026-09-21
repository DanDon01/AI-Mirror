"""Focused tests for the selectable low-latency avatar pipeline."""

import os
from pathlib import Path
from queue import Queue
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.modules.setdefault("pygame", SimpleNamespace())

from avatar_module import AvatarModule, _load_system_prompt, _spoken_reply
from avatar_profiles import AvatarProfile


class AvatarModuleTests(unittest.TestCase):
    def _profile(self, root, key="mechanic", name="Mechanic"):
        root = Path(root)
        image = root / f"{key}.png"
        prompt = root / f"{key}.txt"
        image.write_bytes((key + " image").encode("utf-8"))
        prompt.write_text("# editor note\nStay brisk and in character.\n", encoding="utf-8")
        apparitions = root / key
        apparitions.mkdir()
        return AvatarProfile(key, name, "test persona", image, prompt, apparitions)

    def _bare_module(self, player, profile):
        module = AvatarModule.__new__(AvatarModule)
        module.player = player
        module.ready = Queue()
        module.recording = False
        module.status = "Ready: SPACE to talk"
        module.profile = profile
        module._turn_profile = profile
        module._turn_active = False
        module._alpha = 0.0
        module._last_update = time.monotonic()
        module._hold_background_for_playback = False
        module._deferred_cache = None
        module._cache_downloading = False
        module._bounds = (420, 420)
        module._apparition_pending = False
        module.logger = __import__("logging").getLogger("AvatarTest")
        return module

    def test_profile_prompt_is_loaded_without_editor_comments(self):
        with tempfile.TemporaryDirectory() as temp:
            profile = self._profile(temp)
            with patch.dict(os.environ, {"AVATAR_SYSTEM_PROMPT": "", "AVATAR_PROMPT_FILE": ""}, clear=False):
                self.assertEqual(_load_system_prompt(profile), "Stay brisk and in character.")

    def test_global_prompt_override_still_takes_precedence(self):
        with tempfile.TemporaryDirectory() as temp:
            profile = self._profile(temp)
            with patch.dict(os.environ, {"AVATAR_SYSTEM_PROMPT": "Override persona"}, clear=False):
                self.assertEqual(_load_system_prompt(profile), "Override persona")

    def test_spoken_reply_keeps_the_short_video_word_budget(self):
        text = "one two three four five six seven eight nine ten eleven twelve thirteen"
        self.assertEqual(len(_spoken_reply(text).split()), 12)

    def test_apparitions_are_scoped_to_the_selected_character(self):
        class Player:
            playing = False
            def __init__(self): self.calls = []
            def play(self, path, bounds): self.calls.append((path, bounds))

        with tempfile.TemporaryDirectory() as temp:
            profile = self._profile(temp)
            clip = profile.apparition_dir / "arrival.mp4"
            clip.write_bytes(b"placeholder")
            player = Player()
            module = self._bare_module(player, profile)
            module._last_apparition = None
            module._play_apparition()
            self.assertEqual(player.calls, [(clip, (420, 420))])


if __name__ == "__main__":
    unittest.main(verbosity=2)
