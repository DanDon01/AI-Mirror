"""Offline tests for the Princess Phase 2 provider boundaries."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from princess_services import (  # noqa: E402
    FlashTalkService,
    OpenAITTSService,
    atomic_write_json,
    is_pi_playback_compatible,
    sha256_file,
)


class FakeTracker:
    def __init__(self):
        self.records = []
        self.failures = []

    def allow(self, module, service):
        return True

    def record(self, module, service, estimated_cost=0.0):
        self.records.append((module, service, estimated_cost))

    def failure(self, module, service):
        self.failures.append((module, service))


class FakeSpeechResponse:
    headers = {"x-request-id": "req_tts_test"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def stream_to_file(self, path):
        Path(path).write_bytes(b"RIFF-fake-wave")


class FakeCreate:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return FakeSpeechResponse()


class FakeOpenAIClient:
    def __init__(self):
        self.create = FakeCreate()
        self.audio = type("Audio", (), {})()
        self.audio.speech = type("Speech", (), {})()
        self.audio.speech.with_streaming_response = self.create


class FakeFalHandle:
    request_id = "fal_test_request"

    def iter_events(self, **kwargs):
        yield type("Queued", (), {})()
        yield type("InProgress", (), {})()
        yield type("Completed", (), {"metrics": {"inference_time": 1.2}})()

    def get(self):
        return {
            "video": {"url": "https://example.invalid/result.mp4"},
            "seed": 42,
            "duration": 2.5,
            "timings": {"inference": 1.2},
        }


class FakeFal:
    def __init__(self):
        self.uploaded = []
        self.arguments = None

    def upload_file(self, path):
        self.uploaded.append(path)
        return f"https://example.invalid/{len(self.uploaded)}"

    def submit(self, model, arguments):
        self.arguments = {"model": model, **arguments}
        return FakeFalHandle()


class FakeDownloadResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield b"fake-mp4"


class FakeSession:
    def get(self, url, **kwargs):
        self.url = url
        return FakeDownloadResponse()


class PrincessServiceTests(unittest.TestCase):
    def test_atomic_json_and_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "nested" / "proof.json"
            atomic_write_json(path, {"status": "complete"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["status"], "complete")
            self.assertEqual(len(sha256_file(path)), 64)
            self.assertFalse(path.with_suffix(".json.partial").exists())

    def test_pi_compatibility_requires_expected_codecs(self):
        compatible = {
            "video": {"codec": "h264", "pixel_format": "yuv420p"},
            "audio": {"codec": "aac"},
        }
        self.assertTrue(is_pi_playback_compatible(compatible))
        compatible["video"]["pixel_format"] = "yuv444p"
        self.assertFalse(is_pi_playback_compatible(compatible))

    def test_tts_writes_atomically_and_records_request(self):
        tracker = FakeTracker()
        fake_client = FakeOpenAIClient()

        def client_factory(**kwargs):
            return fake_client

        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"OPENAI_API_KEY": "test"}):
            output = Path(temp) / "speech.wav"
            result = OpenAITTSService(tracker, client_factory).synthesize("Well hello there.", output)
            self.assertEqual(result.request_id, "req_tts_test")
            self.assertEqual(output.read_bytes(), b"RIFF-fake-wave")
            self.assertEqual(fake_client.create.kwargs["response_format"], "wav")
            self.assertEqual(len(tracker.records), 1)
            self.assertFalse(output.with_suffix(".wav.partial").exists())

    def test_flashtalk_persists_video_and_cost_without_url(self):
        tracker = FakeTracker()
        fal = FakeFal()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"FAL_KEY": "test"}):
            root = Path(temp)
            image = root / "reference.png"
            audio = root / "speech.wav"
            output = root / "provider_output.mp4"
            image.write_bytes(b"png")
            audio.write_bytes(b"wav")
            result = FlashTalkService(tracker, fal, FakeSession()).generate(
                image, audio, output, seed=42
            )
            self.assertEqual(result.request_id, "fal_test_request")
            self.assertEqual(result.seed, 42)
            self.assertEqual(result.estimated_cost_usd, 0.05)
            self.assertEqual(output.read_bytes(), b"fake-mp4")
            self.assertNotIn("url", json.dumps(result.__dict__).lower())
            self.assertEqual(fal.arguments["model"], "fal-ai/flashtalk")
            self.assertEqual(len(tracker.records), 1)

    def test_text_avatar_passes_duration_and_prompt_without_audio_upload(self):
        tracker = FakeTracker()
        fal = FakeFal()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"FAL_KEY": "test"}):
            root = Path(temp)
            image = root / "reference.png"
            output = root / "provider_output.mp4"
            image.write_bytes(b"png")
            ready_urls = []
            result = FlashTalkService(tracker, fal, FakeSession()).generate_from_text(
                image,
                "Well hello there.",
                output,
                model="minimax/h3-max-turbo/image-to-video",
                duration_seconds=3,
                on_video_ready=ready_urls.append,
            )
            self.assertEqual(fal.arguments["duration"], 5)
            self.assertIn('says exactly: "Well hello there."', fal.arguments["prompt"])
            self.assertNotIn("audio_url", fal.arguments)
            self.assertEqual(result.duration_seconds, 5.0)
            self.assertEqual(len(fal.uploaded), 1)
            self.assertEqual(ready_urls, ["https://example.invalid/result.mp4"])

    def test_text_avatar_defers_cache_download_until_requested(self):
        tracker = FakeTracker()
        fal = FakeFal()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"FAL_KEY": "test"}):
            root = Path(temp)
            image = root / "reference.png"
            output = root / "provider_output.mp4"
            image.write_bytes(b"png")
            urls = []
            service = FlashTalkService(tracker, fal, FakeSession())
            result = service.generate_from_text(image, "Hello.", output, on_video_ready=urls.append, defer_download=True)
            self.assertEqual(result.bytes, 0)
            self.assertFalse(output.exists())
            service.download_video(urls[0], output)
            self.assertEqual(output.read_bytes(), b"fake-mp4")


if __name__ == "__main__":
    unittest.main(verbosity=2)
