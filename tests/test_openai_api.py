#!/usr/bin/env python
"""Test OpenAI API connectivity: model list, chat completion, TTS."""

import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import load_env, run_test, TestResult


def test_api_key():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return False, "OPENAI_API_KEY not set"
    return True, f"key present ({len(key)} chars)"


def test_model_list():
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    models = client.models.list()
    model_ids = [m.id for m in models]
    count = len(model_ids)
    has_gpt4o = "gpt-4o" in model_ids
    return has_gpt4o, f"{count} models listed, gpt-4o={'found' if has_gpt4o else 'MISSING'}"


def test_chat_completion():
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Say 'test ok' and nothing else."}],
        max_tokens=10,
    )
    text = response.choices[0].message.content.strip()
    return len(text) > 0, f"response: '{text}'"


def test_tts_endpoint():
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input="Test.",
    )
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        response.stream_to_file(f.name)
        size = os.path.getsize(f.name)
        os.unlink(f.name)
    return size > 100, f"TTS audio: {size} bytes"


def test_realtime_model():
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    models = client.models.list()
    model_ids = [m.id for m in models]
    found = any("realtime" in m for m in model_ids)
    return found, f"realtime model {'found' if found else 'NOT found'}"


def main():
    load_env()
    results = TestResult()

    print("Testing OpenAI API...")
    print("-" * 50)

    run_test("API key present", test_api_key, results)
    run_test("Model list", test_model_list, results)
    run_test("Chat completion (gpt-4o)", test_chat_completion, results)
    run_test("TTS endpoint (gpt-4o-mini-tts)", test_tts_endpoint, results)
    run_test("Realtime model available", test_realtime_model, results)

    return results.summary()


if __name__ == "__main__":
    sys.exit(main())
