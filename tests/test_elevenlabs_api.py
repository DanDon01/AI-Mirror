#!/usr/bin/env python
"""Test ElevenLabs API connectivity: voice list and TTS synthesis."""

import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import load_env, run_test, TestResult


def test_api_key():
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key or key == "your-eleven-api-key":
        return False, "ELEVENLABS_API_KEY not set or placeholder"
    return True, f"key present ({len(key)} chars)"


def test_voice_id():
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    if not voice_id or voice_id == "your-voice-id":
        return False, "ELEVENLABS_VOICE_ID not set or placeholder"
    return True, f"voice ID: {voice_id[:8]}..."


def test_voice_list():
    import requests

    key = os.getenv("ELEVENLABS_API_KEY")
    resp = requests.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": key},
        timeout=10,
    )
    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}"
    data = resp.json()
    voices = data.get("voices", [])
    names = [v["name"] for v in voices[:5]]
    return True, f"{len(voices)} voices available: {', '.join(names)}..."


def test_tts_synthesis():
    import requests

    key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")

    if not voice_id or voice_id == "your-voice-id":
        return False, "no voice ID configured"

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    headers = {
        "Accept": "audio/mpeg",
        "xi-api-key": key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": "Test.",
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.7, "similarity_boost": 0.8},
    }

    with requests.post(url, headers=headers, json=payload, stream=True, timeout=15) as r:
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {r.text[:100]}"
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            for chunk in r.iter_content(chunk_size=4096):
                f.write(chunk)
            size = os.path.getsize(f.name)
            os.unlink(f.name)

    return size > 100, f"TTS audio: {size} bytes"


def main():
    load_env()
    results = TestResult()

    print("Testing ElevenLabs API...")
    print("-" * 50)

    run_test("API key present", test_api_key, results)
    run_test("Voice ID configured", test_voice_id, results)
    run_test("Voice list", test_voice_list, results)
    run_test("TTS synthesis", test_tts_synthesis, results)

    return results.summary()


if __name__ == "__main__":
    sys.exit(main())
