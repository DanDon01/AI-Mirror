#!/usr/bin/env python

import time
from pathlib import Path
import os
import logging
from dotenv import load_dotenv  # For loading .env file
import openai

# Load environment variables from environment.env outside the Git folder
env_path = Path(__file__).parent.parent / "environment.env"  # Adjust path as needed
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    print(f"Warning: {env_path} not found. Relying on system environment variables.")

# Set up logging like AIVoiceModule
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger("AudioTest")

# Config matching your AIVoiceModule (optional, can be empty if using .env)
CONFIG = {
    "openai": {"api_key": None},  # Will override with .env if present
    "audio": {"device_index": 3}
}

class AudioTester:
    def __init__(self, config=None):
        self.logger = logger
        self.config = config or {}
        
        # Fetch API key like AIVoiceModule
        self.api_key = self.config.get("openai", {}).get("api_key")
        if not self.api_key:
            self.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_VOICE_KEY")
            if not self.api_key:
                self.logger.error("No OpenAI API key found in config or environment variables")
                raise ValueError("No OpenAI API key found in config or environment variables")
        
        # Initialize OpenAI client
        self.client = openai.OpenAI(api_key=self.api_key)
        self.logger.info("Initialized OpenAI client")

    def transcribe_audio(self, audio_file_path: str) -> None:
        """Transcribe an audio file using Whisper via the standard OpenAI API."""
        audio_path = Path(audio_file_path)
        if not audio_path.exists():
            self.logger.error(f"Audio file {audio_path} not found.")
            return
        
        self.logger.info(f"Transcribing {audio_path}")
        start_time = time.time()
        try:
            with open(audio_path, "rb") as audio_file:
                transcription = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
            self.logger.info(f"Transcription: {transcription}")
            self.logger.info(f"Time taken: {int((time.time() - start_time) * 1000)}ms")
        except Exception as e:
            self.logger.error(f"Transcription failed: {str(e)}")

    def run_tests(self):
        # Test with normal 10s test.wav
        normal_audio_path = "/home/dan/test.wav"  # 10s, PCM16, 24 kHz, mono
        self.logger.info("Testing normal-speed audio:")
        self.transcribe_audio(normal_audio_path)

        # Test with sped-up test_spedup.wav
        spedup_audio_path = "/home/dan/test_spedup.wav"  # 5s, sped-up, PCM16, 24 kHz, mono
        self.logger.info("Testing sped-up audio:")
        self.transcribe_audio(spedup_audio_path)

        # Test with sent_audio_<timestamp>.wav from your last run
        # Replace <timestamp> with the actual value from your log (e.g., from 23:55:10 run)
        sent_audio_path = "/home/dan/mirror_recordings/sent_audio_20250304_235510.wav"  # Example
        self.logger.info("Testing sent audio from Realtime API:")
        self.transcribe_audio(sent_audio_path)

def main():
    tester = AudioTester(CONFIG)
    tester.run_tests()

if __name__ == "__main__":
    main()