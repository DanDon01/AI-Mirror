from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest

from princess_context import PrincessContext


class PrincessContextTests(unittest.TestCase):
    def test_copies_fresh_data_without_fetching(self):
        now = datetime(2026, 9, 4, 12, 0, 0)
        sources = {
            "news": SimpleNamespace(headlines=[{"title": "Headline", "source": "BBC"}], last_fetch=now - timedelta(minutes=5)),
            "weather": SimpleNamespace(weather_data={"name": "Birmingham", "main": {"temp": 18, "feels_like": 17}, "weather": [{"description": "light rain"}], "wind": {"speed": 3}}, last_update=now - timedelta(minutes=5)),
            "calendar": SimpleNamespace(events=[{"summary": "Lunch", "start": {"dateTime": "2026-09-04T13:00:00+01:00"}}], last_update=now - timedelta(minutes=5)),
        }
        snapshot = PrincessContext(sources).snapshot(now)
        self.assertTrue(snapshot["news"]["available"])
        self.assertEqual(snapshot["weather"]["data"]["temperature_c"], 18)
        self.assertEqual(snapshot["calendar"]["data"]["events"][0]["title"], "Lunch")
        self.assertIn("dependency_fingerprint", snapshot["news"])

    def test_copies_only_selected_connected_home_entities(self):
        now = datetime(2026, 9, 4, 12, 0, 0)
        home = SimpleNamespace(
            _connected=True,
            entities=["light.lounge"],
            data={"light.lounge": {"state": "on", "attributes": {"friendly_name": "Lounge light"}}},
            last_update=now - timedelta(seconds=30),
        )
        snapshot = PrincessContext({"smarthome": home}).snapshot(now)
        self.assertTrue(snapshot["smarthome"]["available"])
        self.assertEqual(snapshot["smarthome"]["data"]["entities"], [{"name": "Lounge light", "state": "on", "unit": ""}])

    def test_stale_or_missing_context_is_unavailable(self):
        now = datetime(2026, 9, 4, 12, 0, 0)
        sources = {"news": SimpleNamespace(headlines=[{"title": "Old", "source": "BBC"}], last_fetch=now - timedelta(hours=1))}
        snapshot = PrincessContext(sources).snapshot(now)
        self.assertFalse(snapshot["news"]["available"])
        self.assertFalse(snapshot["weather"]["available"])
        self.assertFalse(snapshot["calendar"]["available"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
