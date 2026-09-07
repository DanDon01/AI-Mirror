"""Small unit tests for the live Princess turn helpers."""
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
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
        module._stream_lock = __import__("threading").RLock()
        module._stream_recognizer = None
        module._capture = None
        module._streaming_capture = False
        module._last_apparition = None
        module._apparition_pending = False
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

    def test_streaming_transcript_skips_second_vosk_pass_on_cache_hit(self):
        class IdlePlayer:
            playing = False
        class Cache:
            root = Path("data/princess/library")
            def promote_matching_transcript(self, *args): return 0
            def select(self, *args, **kwargs): return {"media_path": "media/clip.mp4"}
        module = self._bare_module(IdlePlayer())
        module.cache = Cache()
        module._transcribe_local = Mock(side_effect=AssertionError("must not reprocess streamed PCM"))
        module._make_video({}, "good evening")
        self.assertEqual(module.ready.get_nowait(), module.cache.root / "media/clip.mp4")
        module._transcribe_local.assert_not_called()

    def test_streaming_stop_finalises_existing_recognizer_without_reading_wav(self):
        class IdlePlayer:
            playing = False
        class ImmediateThread:
            def __init__(self, target, args=(), **kwargs): self.target = target; self.args = args
            def start(self): self.target(*self.args)
        module = self._bare_module(IdlePlayer())
        module.recording = True
        module._stream_recognizer = SimpleNamespace(FinalResult=lambda: '{"text":"good evening"}')
        capture = Mock(); module._capture = capture
        module.context = SimpleNamespace(snapshot=lambda: {"weather": {"available": True}})
        module._make_video = Mock()
        with patch("princess_module.threading.Thread", ImmediateThread):
            module._stop_recording()
        self.assertFalse(module.recording)
        capture.close.assert_called_once()
        module._make_video.assert_called_once_with({"weather": {"available": True}}, "good evening")
        self.assertTrue(background_network.paused)
        background_network.set_paused(False)

    def test_apparition_plays_immediately_without_waiting_for_turn(self):
        class Player:
            playing = False
            def __init__(self): self.calls = []
            def play(self, path, bounds): self.calls.append((path, bounds))
        player = Player()
        module = self._bare_module(player)
        with tempfile.TemporaryDirectory() as temp, patch("princess_module.APPARITION_DIR", Path(temp)):
            clip = Path(temp) / "shimmer.mp4"; clip.write_bytes(b"placeholder")
            module._play_apparition()
        self.assertEqual(player.calls, [(clip, (420, 420))])

    def test_apparition_holds_back_portrait_until_decoder_has_a_frame(self):
        class BufferingPlayer:
            playing = True
            has_frame = False
            def update(self, pygame_module): pass
        module = self._bare_module(BufferingPlayer())
        module._apparition_pending = True
        module.update()
        self.assertTrue(module._apparition_pending)
        module.player.has_frame = True
        module.update()
        self.assertFalse(module._apparition_pending)

    def test_apparition_cache_generation_is_new(self):
        source = Path(__file__).resolve().parent.parent / "princess_module.py"
        self.assertIn('portrait-v3-apparition', source.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
