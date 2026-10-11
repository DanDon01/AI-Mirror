"""Web-panel wiring tests for character selection."""

from queue import Queue
from types import SimpleNamespace
import unittest

from web_panel import PAGE, WebPanel


class WebPanelAvatarTests(unittest.TestCase):
    def test_page_contains_avatar_selector_and_endpoint(self):
        self.assertIn('id="avatars"', PAGE)
        self.assertIn('/api/avatars', PAGE)
        self.assertIn('/api/avatar?value=', PAGE)

    def test_queued_selection_runs_on_main_loop(self):
        class Avatar:
            def __init__(self): self.selected = None
            def select_avatar(self, key):
                self.selected = key
                return SimpleNamespace(name="Commander")

        avatar = Avatar()
        notifications = []
        mirror = SimpleNamespace(
            modules={"avatar": avatar},
            animation_manager=SimpleNamespace(
                push_notification=lambda message, **kwargs: notifications.append(message)
            ),
        )
        panel = WebPanel(mirror)
        panel.commands = Queue()
        panel.commands.put(("set_avatar", "commander"))
        panel.process_commands()
        self.assertEqual(avatar.selected, "commander")
        self.assertEqual(notifications, ["Avatar: Commander"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
