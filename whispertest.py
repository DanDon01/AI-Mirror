#!/usr/bin/env python

import time
from pathlib import Path
import openai

# Initialize OpenAI client (assumes OPENAI_API_KEY in env)
openai_client = openai.OpenAI()

def transcribe_audio(audio_file_path: str) -> None:
    """Transcribe an audio file using Whisper via the standard OpenAI API."""
    audio_path = Path(audio_file_path)
    if not audio_path.exists():
        print(f"Error: Audio file {audio_path} not found.")
        return
    
    start_time = time.time()
    try:
        with open(audio_path, "rb") as audio_file:
            transcription = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
        print(f"Transcription: {transcription}")
        print(f"Time taken: {int((time.time() - start_time) * 1000)}ms")
    except Exception as e:
        print(f"Transcription failed: {str(e)}")

def main() -> None:
    # Test with your normal 10s test.wav
    normal_audio_path = "/home/dan/test.wav"  # 10s, PCM16, 24 kHz, mono
    print("Testing normal-speed audio:")
    transcribe_audio(normal_audio_path)

    # Test with your sped-up test_spedup.wav
    spedup_audio_path = "/home/dan/test_spedup.wav"  # 5s, sped-up, PCM16, 24 kHz, mono
    print("\nTesting sped-up audio:")
    transcribe_audio(spedup_audio_path)

    # Optional: Test with a sent_audio_<timestamp>.wav from your last run
    # Replace <timestamp> with the actual value from your log
    sent_audio_path = "/home/dan/mirror_recordings/sent_audio_20250304_235510.wav"  # Example
    print("\nTesting sent audio from Realtime API:")
    transcribe_audio(sent_audio_path)

if __name__ == "__main__":
    main()