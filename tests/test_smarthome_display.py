import unittest

IMPORT_ERROR = None
try:
    import pygame  # The display module intentionally depends on Pygame.
    from config import COLOR_ACCENT_RED
    from smarthome_module import _friendly_state, _state_color
except ModuleNotFoundError as exc:  # Minimal Windows test environments omit it.
    IMPORT_ERROR = exc


@unittest.skipIf(IMPORT_ERROR is not None, "Pygame is not installed in this test environment")
class SmartHomeDisplayTests(unittest.TestCase):
    def test_open_door_is_readable_and_alert_colored(self):
        info = {"state": "on", "attributes": {"device_class": "door"}}
        self.assertEqual(_friendly_state("binary_sensor.front_door", info), "OPEN")
        self.assertEqual(_state_color("binary_sensor.front_door", "on", info["attributes"]), COLOR_ACCENT_RED)

    def test_light_brightness_and_climate_temperatures_are_glanceable(self):
        self.assertEqual(
            _friendly_state("light.hall", {"state": "on", "attributes": {"brightness": 128}}),
            "On 50%",
        )
        self.assertEqual(
            _friendly_state("climate.lounge", {"state": "heat", "attributes": {"current_temperature": 20.5, "temperature": 21, "unit_of_measurement": "°C"}}),
            "20.5°C -> 21°C",
        )

    def test_cover_and_media_states_include_useful_context(self):
        self.assertEqual(
            _friendly_state("cover.blinds", {"state": "open", "attributes": {"current_position": 65}}),
            "Open 65%",
        )
        self.assertEqual(
            _friendly_state("media_player.kitchen", {"state": "playing", "attributes": {"media_title": "Morning News"}}),
            "Playing: Morning News",
        )


if __name__ == "__main__":
    unittest.main()
