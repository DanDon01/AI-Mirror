"""Small unit tests for the live Princess turn helpers."""
import sys
from types import SimpleNamespace
import unittest

sys.modules.setdefault("pygame", SimpleNamespace())

from princess_module import _intent_for, _response_text


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
