import unittest
from unittest.mock import patch
from princess_player import PrincessPlayer

class PrincessPlayerTests(unittest.TestCase):
    def test_play_requires_ffmpeg(self):
        with patch("princess_player.shutil.which", return_value=None):
            with self.assertRaises(RuntimeError):
                PrincessPlayer().play("missing.mp4", (320, 240))

if __name__ == "__main__": unittest.main()
