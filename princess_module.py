"""Princess-only Pi pipeline: local STT -> OpenAI text -> fal video/audio."""
from __future__ import annotations
import json, logging, os, subprocess, threading, time, wave
from pathlib import Path
from queue import Queue

from princess_cache import PrincessCache, TIME_SENSITIVE_INTENTS, time_of_day_tags
from princess_player import PrincessPlayer
from princess_services import FlashTalkService
from background_fetcher import background_network
import pygame

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "assets" / "princess" / "reference_v001.png"
REFERENCE_HASH = "4372362f69934d09af6b156ff5e71183d4b2c3c36155c6361d0f566a09ec7def"

def _intent_for(text: str) -> str:
    words = text.casefold()
    if any(term in words for term in ("good morning", "hello", "hi princess", "hey princess")): return "greeting"
    if "how are you" in words or "i'm fine" in words or "im fine" in words: return "wellbeing"
    if "thank" in words: return "thanks"
    if "good night" in words or "sleep well" in words: return "night"
    if "goodbye" in words or "have a good day" in words: return "farewell"
    if "plans" in words or "what are you doing" in words: return "plans"
    return "general"

class PrincessModule:
    def __init__(self, size=420, alsa_device=None, **kwargs):
        self.size = int(size); self.device = alsa_device or os.getenv("VOICE_MIC", "plughw:3,0")
        self.cache = PrincessCache(); self.player = PrincessPlayer(); self.recording = False
        self.fal = FlashTalkService(); self.openai_client = None; self._vosk_model = None
        self.proc = None; self.ready = Queue(); self.status = "Ready: SPACE to talk"
        self._bounds = (self.size, self.size)
        self.logger = logging.getLogger("Princess")
        self._portrait = None; self._alpha = 0.0; self._last_update = time.monotonic()
        try:
            self._portrait = pygame.image.load(str(REFERENCE))
            self.logger.info("Princess ready: local STT -> OpenAI text -> fal video")
        except Exception as exc:
            self.logger.error("Princess reference image unavailable: %s", exc)
        threading.Thread(target=self._warm_dependencies, daemon=True, name="princess-warmup").start()

    def _warm_dependencies(self):
        """Hide one-off client/model startup work before the first turn."""
        try:
            from openai import OpenAI
            self.openai_client = OpenAI()
            from vosk import Model
            model_path = os.getenv("VOSK_MODEL_PATH", "")
            if model_path:
                self._vosk_model = Model(model_path)
            self.fal.warm_reference(REFERENCE)
            self.logger.info("Princess local STT and text client warmed")
        except Exception as exc:
            self.logger.warning("Princess warm-up deferred: %s", exc)

    def on_button_press(self):
        self.logger.info("Princess Space pressed; recording=%s", self.recording)
        if self.recording: self._stop_recording()
        else: self._start_recording()

    def _start_recording(self):
        path = self.cache.root / "capture.wav"; path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.proc = subprocess.Popen(["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-D", self.device, str(path)])
            self.recording = True; self.status = "Listening — press SPACE when finished"
            self.logger.info("Princess recording started: device=%s", self.device)
        except Exception as exc:
            self.status = f"Mic error: {exc}"; self.logger.exception("Princess recording failed")

    def _stop_recording(self):
        self.recording = False
        if self.proc:
            self.proc.terminate(); self.proc.wait(timeout=3); self.proc = None
        self.status = "Cold start — transcribing locally..."
        background_network.set_paused(True, "Princess turn")
        self.logger.info("Princess recording stopped; processing local transcription")
        threading.Thread(target=self._make_video, daemon=True, name="princess-turn").start()

    def _transcribe_local(self, path):
        try:
            from vosk import KaldiRecognizer, Model
        except ImportError as exc:
            raise RuntimeError("Install vosk and set VOSK_MODEL_PATH for local Pi transcription") from exc
        model_path = os.getenv("VOSK_MODEL_PATH", "")
        if not model_path: raise RuntimeError("VOSK_MODEL_PATH is required for local transcription")
        with wave.open(str(path), "rb") as audio:
            if self._vosk_model is None:
                self._vosk_model = Model(model_path)
            recognizer = KaldiRecognizer(self._vosk_model, audio.getframerate())
            while chunk := audio.readframes(4000): recognizer.AcceptWaveform(chunk)
            return json.loads(recognizer.FinalResult()).get("text", "").strip()

    def _make_video(self):
        started = time.monotonic()
        try:
            transcript = self._transcribe_local(self.cache.root / "capture.wav")
            if not transcript: raise RuntimeError("No speech recognised")
            self.logger.info("Princess local STT complete in %.2fs: %s", time.monotonic() - started, transcript)
            model = os.getenv("PRINCESS_FAL_MODEL", "minimax/h3-max-turbo/image-to-video")
            cache_model = f"{model}::portrait-v2"
            intent = _intent_for(transcript)
            if intent != "general":
                cached = self.cache.select(transcript, REFERENCE_HASH, cache_model, intent=intent)
                if cached:
                    self.status = "Cache hit — playing Princess"
                    self.logger.info("Princess intent cache hit (%s) in %.2fs", intent, time.monotonic() - started)
                    self.ready.put(self.cache.root / cached["media_path"]); return
            self.status = "Cold start — asking Princess..."
            system = os.getenv("PRINCESS_SYSTEM_PROMPT", "You are a poised, confident princess. Be warmly playful, witty, and a little sassy with tasteful attitude; never cruel. Reply concisely and naturally, without markdown.")
            if self.openai_client is None:
                from openai import OpenAI
                self.openai_client = OpenAI()
            response = self.openai_client.responses.create(model=os.getenv("PRINCESS_LLM_MODEL", "gpt-5.4-mini"), max_output_tokens=80, input=[{"role":"system","content":system}, {"role":"user","content":transcript}])
            text = response.output_text.strip()
            if not text: raise RuntimeError("OpenAI returned no response text")
            self.status = "Cold start — creating Princess video..."; self.logger.info("Princess text reply ready in %.2fs; submitting fal video", time.monotonic() - started)
            cached = self.cache.lookup(text, REFERENCE_HASH, cache_model)
            if cached:
                self.logger.info("Princess cache hit")
                self.ready.put(self.cache.root / cached["media_path"]); return
            staging = self.cache.root / "staging" / "latest.mp4"
            video_prompt = (
                "A poised royal woman speaks naturally and directly to camera, with subtle confident facial expressions. "
                "Use a seamless pure black background. No mirror, no reflective glass, no frame, no border, no text, and no hands. "
                f'Say exactly: "{text}"'
            )
            result = self.fal.generate_from_text(REFERENCE, text, staging, model=model, prompt=video_prompt, duration_seconds=5, resolution=os.getenv("PRINCESS_FAL_RESOLUTION", "480P"))
            self.logger.info("Princess fal video ready in %.2fs (upload %.2fs, queue %.2fs, generation %.2fs, download %.2fs)", time.monotonic() - started, result.timings.get("image_upload", 0), result.timings.get("queue", 0), result.timings.get("generation", 0), result.timings.get("download", 0))
            if not any(word in transcript.casefold() for word in TIME_SENSITIVE_INTENTS):
                record = self.cache.add_clip(staging, spoken_text=text, intent=intent, model=cache_model, reference_sha256=REFERENCE_HASH, tags=sorted(time_of_day_tags()), duration_seconds=result.duration_seconds, metadata={"transcript": transcript, "prompt_version": "portrait-v2"})
                self.ready.put(self.cache.root / record["media_path"])
            else:
                self.ready.put(staging)
        except Exception as exc:
            self.logger.exception("Princess turn failed")
            self.ready.put(exc)

    def update(self):
        now = time.monotonic(); self._alpha = min(1.0, self._alpha + min(now - self._last_update, 0.1) * 3) if (self.recording or self.status not in ("Ready: SPACE to talk", "Playing")) else max(0.0, self._alpha - min(now - self._last_update, 0.1) * 2); self._last_update = now
        while not self.ready.empty():
            item = self.ready.get_nowait()
            if isinstance(item, Exception):
                background_network.set_paused(False)
                self.status = f"Error: {item}"; continue
            self.player.play(item, self._bounds); self.status = "Playing"
            background_network.set_paused(False)
        self.player.update(__import__("pygame"))

    def draw(self, screen, position):
        width, height = int(position.get("width", self.size)), int(position.get("height", self.size))
        self._bounds = (width, height)
        if self.player.playing or self.player.has_frame:
            self.player.draw(screen, position)
            return
        if self._portrait is not None and self._alpha > 0.01:
            scale = min(width / self._portrait.get_width(), height / self._portrait.get_height())
            image = pygame.transform.smoothscale(self._portrait, (max(1, int(self._portrait.get_width() * scale)), max(1, int(self._portrait.get_height() * scale))))
            image.set_alpha(int(255 * self._alpha))
            x = position.get("x", 0) + (width - image.get_width()) // 2; y = position.get("y", 0) + (height - image.get_height()) // 2
            screen.blit(image, (x, y))
        font = pygame.font.Font(None, 26); label = font.render(self.status, True, (242, 222, 172)); label.set_alpha(235)
        screen.blit(label, (position.get("x", 0) + 12, position.get("y", 0) + 12))
    def cleanup(self):
        background_network.set_paused(False)
        self.player.cleanup()
