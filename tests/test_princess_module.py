"""Small unit tests for the live Princess turn helpers."""
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from queue import Queue

sys.modules.setdefault("pygame", SimpleNamespace())

from background_fetcher import background_network
from princess_module import PrincessModule, _effective_intent, _intent_for, _load_system_prompt, _response_intent_and_text, _response_text, _spoken_reply


class PrincessModuleTests(unittest.TestCase):
    def _bare_module(self, player):
        module = PrincessModule.__new__(PrincessModule)
        module.player = player
        module.ready = Queue()
        module.recording = False
        module.status = "Ready: SPACE to talk"
        module._alpha = 0.0
        module._last_update = time.monotonic()
        module._hold_background_for_playback = False
        module._deferred_cache = None
        module._cache_downloading = False
        module._bounds = (420, 420)
        module.logger = __import__("logging").getLogger("PrincessTest")
        return module
    def test_response_text_reads_convenience_property(self):
        self.assertEqual(_response_text(SimpleNamespace(output_text=" Hello. ")), "Hello.")

    def test_response_text_reads_message_content_fallback(self):
        response = SimpleNamespace(
            output_text="",
            output=[SimpleNamespace(content=[SimpleNamespace(text="A fallback reply.")])],
        )
        self.assertEqual(_response_text(response), "A fallback reply.")

    def test_time_specific_greetings_do_not_share_a_pool(self):
        self.assertEqual(_intent_for("good morning"), "greeting_morning")
        self.assertEqual(_intent_for("good evening"), "greeting_evening")
        self.assertEqual(_intent_for("morning"), "greeting_morning")
        self.assertEqual(_intent_for("afternoon"), "greeting_afternoon")
        self.assertEqual(_intent_for("evening"), "greeting_evening")
        self.assertEqual(_intent_for("are the lights on"), "smarthome")

    def test_system_prompt_uses_editable_text_file_and_skips_comments(self):
        with tempfile.TemporaryDirectory() as temp:
            prompt_file = Path(temp) / "princess.txt"
            prompt_file.write_text("# Guidance only\n\nBe concise and mischievous.\n", encoding="utf-8")
            with patch.dict(os.environ, {"PRINCESS_PROMPT_FILE": str(prompt_file), "PRINCESS_SYSTEM_PROMPT": ""}, clear=False):
                self.assertEqual(_load_system_prompt(), "Be concise and mischievous.")

    def test_response_route_envelope_is_not_sent_to_fal(self):
        intent, reply = _response_intent_and_text("INTENT: weather\nREPLY: Bring an umbrella, Prince.", "general")
        self.assertEqual(intent, "weather")
        self.assertEqual(reply, "Bring an umbrella, Prince.")

    def test_spoken_reply_strips_markup_and_enforces_word_budget(self):
        reply = _spoken_reply('**One** "two" three four five six seven eight nine ten eleven twelve thirteen.')
        self.assertEqual(reply, "One two three four five six seven eight nine ten eleven twelve")

    def test_invalid_route_falls_back_without_losing_reply(self):
        intent, reply = _response_intent_and_text("INTENT: stocks\nREPLY: Markets are lively.", "general")
        self.assertEqual(intent, "general")
        self.assertEqual(reply, "Markets are lively.")

    def test_known_live_route_cannot_be_downgraded_by_model_envelope(self):
        self.assertEqual(_effective_intent("news", "general"), "news")
        self.assertEqual(_effective_intent("general", "weather"), "weather")

    def test_playback_startup_failure_is_contained_and_unpauses_network(self):
        class BrokenPlayer:
            playing = False
            def play(self, path, bounds): raise RuntimeError("ffmpeg unavailable")
            def update(self, pygame_module): pass
            def stop(self): pass
        module = self._bare_module(BrokenPlayer())
        module.ready.put("clip.mp4")
        background_network.set_paused(True, "Princess turn")
        module.update()
        self.assertIn("Playback error: ffmpeg unavailable", module.status)
        self.assertFalse(background_network.paused)

    def test_playback_update_failure_is_contained_and_unpauses_network(self):
        class BrokenPlayer:
            playing = True
            def update(self, pygame_module): raise RuntimeError("decoder failed")
            def stop(self): self.stopped = True
        player = BrokenPlayer()
        module = self._bare_module(player)
        module._hold_background_for_playback = True
        background_network.set_paused(True, "Princess playback")
        module.update()
        self.assertIn("Playback error: decoder failed", module.status)
        self.assertTrue(player.stopped)
        self.assertFalse(background_network.paused)

    def test_worker_error_is_shown_without_crashing_the_render_loop(self):
        class IdlePlayer:
            playing = False
            def update(self, pygame_module): pass
        module = self._bare_module(IdlePlayer())
        module.ready.put(RuntimeError("OpenAI request failed"))
        background_network.set_paused(True, "Princess turn")
        module.update()
        self.assertEqual(module.status, "Error: OpenAI request failed")
        self.assertFalse(background_network.paused)


if __name__ == "__main__":
    unittest.main(verbosity=2)
