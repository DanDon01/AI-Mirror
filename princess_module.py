"""Princess-only Pi pipeline: local STT -> OpenAI text -> fal video/audio."""
from __future__ import annotations
import json, os, subprocess, threading, wave
from pathlib import Path
from queue import Queue

from princess_cache import PrincessCache, TIME_SENSITIVE_INTENTS, time_of_day_tags
from princess_player import PrincessPlayer
from princess_services import FlashTalkService

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "assets" / "princess" / "reference_v001.png"
REFERENCE_HASH = "4372362f69934d09af6b156ff5e71183d4b2c3c36155c6361d0f566a09ec7def"

class PrincessModule:
    def __init__(self, size=420, alsa_device=None, **kwargs):
        self.size = int(size); self.device = alsa_device or os.getenv("VOICE_MIC", "plughw:3,0")
        self.cache = PrincessCache(); self.player = PrincessPlayer(); self.recording = False
        self.proc = None; self.ready = Queue(); self.status = "Ready: SPACE to talk"

    def on_button_press(self):
        if self.recording: self._stop_recording()
        else: self._start_recording()

    def _start_recording(self):
        path = self.cache.root / "capture.wav"; path.parent.mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen(["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-D", self.device, str(path)])
        self.recording = True; self.status = "Listening: SPACE to send"

    def _stop_recording(self):
        self.recording = False
        if self.proc:
            self.proc.terminate(); self.proc.wait(timeout=3); self.proc = None
        self.status = "Thinking..."
        threading.Thread(target=self._make_video, daemon=True, name="princess-turn").start()

    def _transcribe_local(self, path):
        try:
            from vosk import KaldiRecognizer, Model
        except ImportError as exc:
            raise RuntimeError("Install vosk and set VOSK_MODEL_PATH for local Pi transcription") from exc
        model_path = os.getenv("VOSK_MODEL_PATH", "")
        if not model_path: raise RuntimeError("VOSK_MODEL_PATH is required for local transcription")
        with wave.open(str(path), "rb") as audio:
            recognizer = KaldiRecognizer(Model(model_path), audio.getframerate())
            while chunk := audio.readframes(4000): recognizer.AcceptWaveform(chunk)
            return json.loads(recognizer.FinalResult()).get("text", "").strip()

    def _make_video(self):
        try:
            transcript = self._transcribe_local(self.cache.root / "capture.wav")
            if not transcript: raise RuntimeError("No speech recognised")
            from openai import OpenAI
            system = os.getenv("PRINCESS_SYSTEM_PROMPT", "You are a poised, warm princess in a magic mirror. Reply concisely, naturally, and without markdown.")
            response = OpenAI().responses.create(model=os.getenv("PRINCESS_LLM_MODEL", "gpt-5.4-mini"), input=[{"role":"system","content":system}, {"role":"user","content":transcript}])
            text = response.output_text.strip()
            if not text: raise RuntimeError("OpenAI returned no response text")
            model = os.getenv("PRINCESS_FAL_MODEL", "minimax/h3-max-turbo/image-to-video")
            cached = self.cache.lookup(text, REFERENCE_HASH, model)
            if cached:
                self.ready.put(self.cache.root / cached["media_path"]); return
            staging = self.cache.root / "staging" / "latest.mp4"
            result = FlashTalkService().generate_from_text(REFERENCE, text, staging, model=model, prompt=f"{system} Say exactly: {text}", duration_seconds=5)
            intent = "general"
            if not any(word in transcript.casefold() for word in TIME_SENSITIVE_INTENTS):
                record = self.cache.add_clip(staging, spoken_text=text, intent=intent, model=model, reference_sha256=REFERENCE_HASH, tags=sorted(time_of_day_tags()), duration_seconds=result.duration_seconds, metadata={"transcript": transcript})
                self.ready.put(self.cache.root / record["media_path"])
            else:
                self.ready.put(staging)
        except Exception as exc:
            self.ready.put(exc)

    def update(self):
        while not self.ready.empty():
            item = self.ready.get_nowait()
            if isinstance(item, Exception): self.status = f"Error: {item}"; continue
            self.player.play(item, (self.size, self.size)); self.status = "Playing"
        self.player.update(__import__("pygame"))

    def draw(self, screen, position): self.player.draw(screen, position)
    def cleanup(self): self.player.cleanup()
