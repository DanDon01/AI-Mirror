import unittest
from unittest.mock import Mock, patch
from princess_player import PrincessPlayer

class PrincessPlayerTests(unittest.TestCase):
    def test_play_requires_ffmpeg(self):
        with patch("princess_player.shutil.which", return_value=None):
            with self.assertRaises(RuntimeError):
                PrincessPlayer().play("missing.mp4", (320, 240))

    def test_stop_waits_for_audio_process_to_release_device(self):
        process = Mock()
        process.poll.return_value = None
        PrincessPlayer._stop_process(process)
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=0.4)

if __name__ == "__main__": unittest.main()
