"""Small unit tests for the live Princess turn helpers."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.modules.setdefault("pygame", SimpleNamespace())

from princess_module import _intent_for, _load_system_prompt, _response_intent_and_text, _response_text


class PrincessModuleTests(unittest.TestCase):
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

    def test_invalid_route_falls_back_without_losing_reply(self):
        intent, reply = _response_intent_and_text("INTENT: stocks\nREPLY: Markets are lively.", "general")
        self.assertEqual(intent, "general")
        self.assertEqual(reply, "Markets are lively.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
