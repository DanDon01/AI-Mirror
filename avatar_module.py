"""Avatar-only Pi pipeline: local STT -> OpenAI text -> fal video/audio."""
from __future__ import annotations
import json, logging, os, random, re, shutil, subprocess, threading, time, wave
from pathlib import Path
from queue import Queue

from avatar_cache import AvatarCache, TIME_SENSITIVE_INTENTS, time_of_day_tags
from avatar_player import AvatarPlayer
from avatar_services import FlashTalkService
from avatar_context import AvatarContext
from avatar_profiles import AvatarProfile, AvatarProfiles
from background_fetcher import background_network
import pygame

ROOT = Path(__file__).resolve().parent
DEFAULT_SYSTEM_PROMPT = "You are a character appearing in an interactive smart mirror. Stay in character and answer directly."


def _load_system_prompt(profile: AvatarProfile | None = None) -> str:
    """Load the editable tracked prompt, ignoring its human guidance comments."""
    override = os.getenv("AVATAR_SYSTEM_PROMPT", "").strip()
    if override:
        return override
    profile = profile or AvatarProfiles().current()
    prompt_override = os.getenv("AVATAR_PROMPT_FILE", "").strip()
    prompt_file = Path(prompt_override) if prompt_override else profile.prompt_file
    try:
        prompt = " ".join(
            line.strip() for line in prompt_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        return prompt or DEFAULT_SYSTEM_PROMPT
    except OSError:
        return DEFAULT_SYSTEM_PROMPT

def _intent_for(text: str) -> str:
    words = text.casefold()
    if any(term in words for term in ("news", "headlines", "what's happening", "whats happening")): return "news"
    if any(term in words for term in ("weather", "temperature", "forecast", "rain", "wind")): return "weather"
    if any(term in words for term in ("calendar", "schedule", "appointments", "what have i got", "what do i have")): return "calendar"
    if any(term in words for term in ("smart home", "lights", "light", "heating", "thermostat", "front door", "house status")): return "smarthome"
    if "good morning" in words or words.strip(" .!?") == "morning": return "greeting_morning"
    if "good afternoon" in words or words.strip(" .!?") == "afternoon": return "greeting_afternoon"
    if "good evening" in words or words.strip(" .!?") == "evening": return "greeting_evening"
    if any(term in words for term in ("hello", "hi avatar", "hey avatar", "hiya")): return "greeting"
    if "how are you" in words or "i'm fine" in words or "im fine" in words: return "wellbeing"
    if "thank" in words: return "thanks"
    if "good night" in words or "sleep well" in words: return "night"
    if "goodbye" in words or "have a good day" in words: return "farewell"
    if "plans" in words or "what are you doing" in words: return "plans"
    return "general"


def _response_text(response) -> str:
    """Read a visible reply from both current and older Responses SDK shapes."""
    text = getattr(response, "output_text", "") or ""
    if text.strip():
        return text.strip()
    for message in getattr(response, "output", []) or []:
        content = getattr(message, "content", None)
        if content is None and isinstance(message, dict):
            content = message.get("content", [])
        for part in content or []:
            value = getattr(part, "text", None)
            if value is None and isinstance(part, dict):
                value = part.get("text", "")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _response_intent_and_text(raw: str, fallback_intent: str) -> tuple[str, str]:
    """Parse the one-call Nano routing envelope without exposing it to Fal."""
    intent = fallback_intent
    reply_lines = []
    for line in raw.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().casefold() == "intent":
            candidate = value.strip().casefold()
            if candidate in {"general", "news", "weather", "calendar", "smarthome"}:
                intent = candidate
        elif separator and key.strip().casefold() == "reply":
            reply_lines.append(value.strip())
        elif reply_lines:
            reply_lines.append(line.strip())
    reply = " ".join(part for part in reply_lines if part).strip()
    return intent, reply or raw.strip()


def _effective_intent(local_intent: str, model_intent: str) -> str:
    """Keep a known local live-data route authoritative over model formatting."""
    return local_intent if local_intent != "general" else model_intent


def _spoken_reply(text: str, max_words: int = 12) -> str:
    """Make model output safe, concise, and literal before it reaches Fal."""
    clean = re.sub(r"[`*_#]+", "", str(text or ""))
    clean = clean.replace('"', "").replace("\\", "")
    clean = " ".join(clean.split())
    return " ".join(clean.split()[:max(1, max_words)]).strip()

class AvatarModule:
    def __init__(self, size=420, alsa_device=None, **kwargs):
        self.size = int(size); self.device = alsa_device or os.getenv("VOICE_MIC", "plughw:3,0")
        self.cache = AvatarCache(); self.player = AvatarPlayer(); self.recording = False
        self.profiles = AvatarProfiles()
        self.profile = self.profiles.current()
        self._turn_profile = None; self._turn_active = False
        self.context = AvatarContext()
        self.fal = FlashTalkService(); self.openai_client = None; self._vosk_model = None
        self.proc = None; self.ready = Queue(); self.status = "Ready: SPACE to talk"
        self._mic_proc = None; self._mic_thread = None; self._mic_stop = threading.Event()
        self._stream_lock = threading.RLock(); self._stream_recognizer = None; self._capture = None
        self._streaming_capture = False; self._last_apparition = None; self._apparition_pending = False
        self._deferred_cache = None; self._cache_downloading = False; self._hold_background_for_playback = False
        self._playback_label = "none"
        self._bounds = (self.size, self.size)
        self.logger = logging.getLogger("Avatar")
        self._portrait = None; self._alpha = 0.0; self._last_update = time.monotonic()
        self._load_portrait(self.profile)
        self.logger.info(
            "Avatar ready as %s: local STT -> OpenAI text -> fal video",
            self.profile.name,
        )
        threading.Thread(target=self._warm_dependencies, daemon=True, name="avatar-warmup").start()

    def _load_portrait(self, profile: AvatarProfile):
        try:
            self._portrait = pygame.image.load(str(profile.reference_image))
        except Exception as exc:
            self._portrait = None
            self.logger.error("%s reference image unavailable: %s", profile.name, exc)

    def get_avatar_options(self):
        """Return the selector payload used by the LAN web panel."""
        return {
            "avatars": self.profiles.options(),
            "current": self.profile.key,
            "busy": bool(self._turn_active or self.recording or self.player.playing),
        }

    def select_avatar(self, key):
        """Switch character while idle; the next turn uses its image and prompt."""
        if self._turn_active or self.recording or self.player.playing:
            raise RuntimeError("Wait for the current avatar turn to finish")
        profile = self.profiles.select(key)
        self.player.stop()
        self.profile = profile
        self._load_portrait(profile)
        self.status = "Ready: SPACE to talk"
        threading.Thread(
            target=self._warm_reference,
            args=(profile,),
            daemon=True,
            name=f"avatar-warm-{profile.key}",
        ).start()
        self.logger.info("Avatar changed to %s", profile.name)
        return profile

    def _warm_reference(self, profile):
        try:
            self.fal.warm_reference(profile.reference_image)
            self.logger.info("%s reference image warmed", profile.name)
        except Exception as exc:
            self.logger.warning("%s reference warm-up deferred: %s", profile.name, exc)

    def set_context_sources(self, sources):
        """Called by the mirror after all data modules are initialized."""
        self.context.set_sources(sources)

    def _warm_dependencies(self):
        """Hide one-off client/model/microphone startup work before the first turn."""
        try:
            from openai import OpenAI
            self.openai_client = OpenAI()
            from vosk import Model
            model_path = os.getenv("VOSK_MODEL_PATH", "")
            if model_path:
                self._vosk_model = Model(model_path)
                self._start_warmed_microphone()
            self.fal.warm_reference(self.profile.reference_image)
            self.logger.info("Avatar local STT and text client warmed; streaming_mic=%s", self._streaming_capture)
        except Exception as exc:
            self.logger.warning("Avatar warm-up deferred: %s", exc)

    def _start_warmed_microphone(self):
        """Keep one raw ALSA stream open; discard PCM until a Avatar turn starts."""
        if os.getenv("AVATAR_WARM_MIC", "1").lower() not in ("1", "true", "yes", "on"):
            return
        if self._mic_proc or self._vosk_model is None or not shutil.which("arecord"):
            return
        try:
            self._mic_stop.clear()
            self._mic_proc = subprocess.Popen(
                ["arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", "16000", "-c", "1", "-D", self.device],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
            )
            self._mic_thread = threading.Thread(target=self._drain_warmed_microphone, daemon=True, name="avatar-vosk-stream")
            self._mic_thread.start()
            self._streaming_capture = True
            self.logger.info("Avatar warm microphone opened: device=%s", self.device)
        except Exception as exc:
            self._mic_proc = None; self._streaming_capture = False
            self.logger.warning("Avatar warm microphone unavailable; using per-turn recorder: %s", exc)

    def _drain_warmed_microphone(self):
        process = self._mic_proc
        try:
            while process and process.stdout and not self._mic_stop.is_set():
                pcm = process.stdout.read(4000)
                if not pcm:
                    break
                with self._stream_lock:
                    if not self.recording or self._stream_recognizer is None:
                        continue
                    if self._capture is not None:
                        self._capture.writeframesraw(pcm)
                    self._stream_recognizer.AcceptWaveform(pcm)
        except Exception:
            if not self._mic_stop.is_set():
                self.logger.exception("Avatar warm microphone stream failed")
        finally:
            if not self._mic_stop.is_set():
                self._streaming_capture = False
                self.logger.warning("Avatar warm microphone ended; using per-turn recorder")

    def _stop_warmed_microphone(self):
        self._mic_stop.set()
        with self._stream_lock:
            if self._capture is not None:
                self._capture.close(); self._capture = None
            self._stream_recognizer = None
        process = self._mic_proc; self._mic_proc = None; self._streaming_capture = False
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: process.kill()

    def _play_apparition(self):
        """Begin optional theatre immediately; response generation continues in parallel."""
        if os.getenv("AVATAR_APPARITIONS", "1").lower() not in ("1", "true", "yes", "on"):
            return
        clips = sorted(self.profile.apparition_dir.glob("*.mp4"))
        if not clips:
            return
        choices = [clip for clip in clips if clip != self._last_apparition] or clips
        clip = random.choice(choices)
        try:
            # Do not show the static portrait while ffmpeg decodes the clip's
            # deliberately black opening frame.
            self._apparition_pending = True
            self._playback_label = f"apparition: {clip.name}"
            self.player.play(clip, self._bounds)
            self._last_apparition = clip
            self.logger.info("Avatar apparition started: %s", clip.name)
        except Exception:
            self._apparition_pending = False
            self.logger.exception("Avatar apparition playback failed")

    def on_button_press(self):
        self.logger.info("Avatar Space pressed; recording=%s", self.recording)
        if self.recording: self._stop_recording()
        elif self._turn_active:
            self.logger.info("Avatar input ignored while the current turn is finishing")
        else: self._start_recording()

    def _start_recording(self):
        self._turn_profile = self.profile
        self._turn_active = True
        path = self.cache.root / "capture.wav"; path.parent.mkdir(parents=True, exist_ok=True)
        self.player.stop()
        self._play_apparition()
        if self._streaming_capture and self._vosk_model is not None and self._mic_proc and self._mic_proc.poll() is None:
            try:
                from vosk import KaldiRecognizer
                with self._stream_lock:
                    self._capture = wave.open(str(path), "wb")
                    self._capture.setnchannels(1); self._capture.setsampwidth(2); self._capture.setframerate(16000)
                    self._stream_recognizer = KaldiRecognizer(self._vosk_model, 16000)
                    self.recording = True
                self.status = "Listening - press SPACE when finished"
                self.logger.info("Avatar streaming recording started: device=%s", self.device)
                return
            except Exception:
                with self._stream_lock:
                    if self._capture is not None: self._capture.close()
                    self._capture = None; self._stream_recognizer = None
                self.logger.exception("Avatar streaming capture setup failed; using per-turn recorder")
        try:
            self.proc = subprocess.Popen(["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-D", self.device, str(path)])
            self.recording = True; self.status = "Listening - press SPACE when finished"
            self.logger.info("Avatar recording started: device=%s", self.device)
        except Exception as exc:
            self._turn_active = False
            self.status = f"Mic error: {exc}"; self.logger.exception("Avatar recording failed")

    def _stop_recording(self):
        if self._stream_recognizer is not None:
            try:
                with self._stream_lock:
                    self.recording = False
                    recognizer = self._stream_recognizer; self._stream_recognizer = None
                    if self._capture is not None:
                        self._capture.close(); self._capture = None
                    transcript = json.loads(recognizer.FinalResult()).get("text", "").strip()
                self.status = "Conjuring your answer..."
                background_network.set_paused(True, "Avatar turn")
                snapshot = self.context.snapshot()
                self.logger.info("Avatar streaming STT finalised instantly: %s", transcript)
                threading.Thread(target=self._make_video, args=(snapshot, transcript, self._turn_profile), daemon=True, name="avatar-turn").start()
                return
            except Exception as exc:
                self.recording = False
                self.logger.exception("Avatar streaming transcription failed; falling back")
                self.status = f"STT error: {exc}"
                self._turn_active = False
                background_network.set_paused(False)
                return
        self.recording = False
        if self.proc:
            try:
                self.proc.terminate(); self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.logger.warning("Avatar recorder did not stop cleanly; killing it")
                self.proc.kill(); self.proc.wait(timeout=3)
            except Exception:
                self.logger.exception("Avatar recorder shutdown failed")
            finally:
                self.proc = None
        self.status = "Cold start - transcribing locally..."
        background_network.set_paused(True, "Avatar turn")
        self.logger.info("Avatar recording stopped; processing local transcription")
        snapshot = self.context.snapshot()
        threading.Thread(target=self._make_video, args=(snapshot, None, self._turn_profile), daemon=True, name="avatar-turn").start()

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

    def _make_video(self, context_snapshot=None, transcript=None, profile=None):
        started = time.monotonic()
        try:
            profile = profile or self._turn_profile or self.profile
            reference_hash = profile.reference_hash()
            if transcript is None:
                transcript = self._transcribe_local(self.cache.root / "capture.wav")
                self.logger.info("Avatar local STT complete in %.2fs: %s", time.monotonic() - started, transcript)
            else:
                self.logger.info("Avatar streaming STT ready at response submit: %s", transcript)
            if not transcript: raise RuntimeError("No speech recognised")
            model = os.getenv("AVATAR_FAL_MODEL", "minimax/h3-max-turbo/image-to-video")
            # Keep legacy clips on disk for review, but do not select clips
            # created before the apparition/audio and stricter no-mirror path.
            cache_model = f"{model}::portrait-v4-avatar::{profile.key}"
            local_intent = _intent_for(transcript)
            intent = local_intent
            if local_intent != "general":
                promoted = self.cache.promote_matching_transcript(transcript, local_intent)
                if promoted: self.logger.info("Avatar promoted %s existing cached clip(s) to %s", promoted, local_intent)
                cached = self.cache.select(transcript, reference_hash, cache_model, intent=local_intent)
                if cached:
                    self.status = f"Cache hit - playing {profile.name}"
                    self.logger.info("Avatar intent cache hit (%s) in %.2fs", intent, time.monotonic() - started)
                    self.ready.put(self.cache.root / cached["media_path"]); return
            self.status = f"Cold start - asking {profile.name}..."
            system = _load_system_prompt(profile)
            system += " Reply with exactly one natural short sentence, at most 12 words. No markdown."
            if intent == "general":
                live_context = context_snapshot or {}
            else:
                live_context = {intent: (context_snapshot or {}).get(intent, {})}
            compact_context = {
                name: {"available": value.get("available", False), "data": value.get("data"), "reason": value.get("reason")}
                for name, value in live_context.items()
            }
            system += (
                " Classify the user's request as exactly one of general, news, weather, calendar, or smarthome. "
                "Use live facts only for the matching category; if that category is unavailable, say so plainly and invent nothing. "
                "Return exactly two lines: INTENT: <category> then REPLY: <your reply>. "
                f"Current mirror data: {json.dumps(compact_context, ensure_ascii=False, separators=(',', ':'))}"
            )
            if self.openai_client is None:
                from openai import OpenAI
                self.openai_client = OpenAI()
            llm_model = os.getenv("AVATAR_LLM_MODEL", "gpt-5-nano-2025-08-07")
            request = {"model": llm_model, "max_output_tokens": int(os.getenv("AVATAR_LLM_MAX_OUTPUT_TOKENS", "160")), "input": [{"role":"system","content":system}, {"role":"user","content":transcript}]}
            if llm_model.startswith("gpt-5"):
                request["reasoning"] = {"effort": os.getenv("AVATAR_LLM_REASONING_EFFORT", "minimal")}
            response = self.openai_client.responses.create(**request)
            raw_text = _response_text(response)
            if not raw_text:
                status = getattr(response, "status", "unknown")
                detail = getattr(response, "incomplete_details", None)
                raise RuntimeError(f"OpenAI returned no visible response text (status={status}, detail={detail})")
            model_intent, text = _response_intent_and_text(raw_text, local_intent)
            intent = _effective_intent(local_intent, model_intent)
            text = _spoken_reply(text, int(os.getenv("AVATAR_MAX_REPLY_WORDS", "12")))
            if not text:
                raise RuntimeError("OpenAI returned no Avatar reply text")
            self.status = f"Cold start - creating {profile.name} video..."; self.logger.info("Avatar text reply ready in %.2fs; submitting fal video", time.monotonic() - started)
            self.logger.info("Avatar reply sent to Fal: %s", text)
            cached = self.cache.lookup(text, reference_hash, cache_model) if intent not in TIME_SENSITIVE_INTENTS else None
            if cached:
                self.logger.info("Avatar cache hit")
                self.ready.put(self.cache.root / cached["media_path"]); return
            staging = self.cache.root / "staging" / f"turn-{time.time_ns()}.mp4"
            video_prompt = (
                "The uploaded character is the only subject, speaking naturally and directly to camera with subtle facial expressions. "
                "Use a seamless pure black background. There is no mirror, magical mirror, reflection, reflective glass, frame, border, text, or hands anywhere in the video. "
                f'Say exactly: "{text}"'
            )
            self.logger.info("Avatar Fal prompt: %s", video_prompt)
            stream_first = os.getenv("AVATAR_STREAM_FIRST", "1").lower() in ("1", "true", "yes", "on")
            streamed = threading.Event()
            stream_url = None
            def stream_when_ready(url):
                nonlocal stream_url
                stream_url = url
                if stream_first:
                    self.ready.put({"stream_url": url})
                    streamed.set()
            result = self.fal.generate_from_text(profile.reference_image, text, staging, model=model, prompt=video_prompt, duration_seconds=5, resolution=os.getenv("AVATAR_FAL_RESOLUTION", "480P"), on_video_ready=stream_when_ready, defer_download=stream_first)
            self.logger.info("Avatar fal video ready in %.2fs (upload %.2fs, queue %.2fs, generation %.2fs, download %.2fs)", time.monotonic() - started, result.timings.get("image_upload", 0), result.timings.get("queue", 0), result.timings.get("generation", 0), result.timings.get("download", 0))
            if streamed.is_set(): self.logger.info("Avatar cache download deferred until playback has completed")
            if intent not in TIME_SENSITIVE_INTENTS:
                if streamed.is_set():
                    self._deferred_cache = {"url": stream_url, "staging": staging, "text": text, "intent": intent, "model": cache_model, "duration_seconds": result.duration_seconds, "transcript": transcript, "reference_hash": reference_hash, "avatar": profile.key}
                else:
                    record = self.cache.add_clip(staging, spoken_text=text, intent=intent, model=cache_model, reference_sha256=reference_hash, tags=sorted(time_of_day_tags()), duration_seconds=result.duration_seconds, metadata={"transcript": transcript, "prompt_version": "portrait-v4-avatar", "avatar": profile.key})
                    self.ready.put(self.cache.root / record["media_path"])
            else:
                if not streamed.is_set(): self.ready.put(staging)
        except Exception as exc:
            self.logger.exception("Avatar turn failed")
            self.ready.put(exc)

    def update(self):
        now = time.monotonic(); self._alpha = min(1.0, self._alpha + min(now - self._last_update, 0.1) * 3) if (self.recording or self.status not in ("Ready: SPACE to talk", "Playing")) else max(0.0, self._alpha - min(now - self._last_update, 0.1) * 2); self._last_update = now
        while not self.ready.empty():
            item = self.ready.get_nowait()
            if isinstance(item, Exception):
                background_network.set_paused(False)
                self._hold_background_for_playback = False
                self._turn_active = False
                self.status = f"Error: {item}"; continue
            try:
                self._apparition_pending = False
                if isinstance(item, dict) and "stream_url" in item:
                    self._playback_label = "Fal live stream (reply video)"
                    self.player.play(item["stream_url"], self._bounds)
                    self.status = f"Streaming {self._turn_profile.name if self._turn_profile else 'avatar'} video..."; self._hold_background_for_playback = True
                else:
                    self._playback_label = f"local clip: {Path(item).name}"
                    self.player.play(item, self._bounds); self.status = "Playing"
                    background_network.set_paused(False)
            except Exception as exc:
                self.logger.exception("Avatar playback startup failed")
                self._hold_background_for_playback = False
                self._turn_active = False
                background_network.set_paused(False)
                self.status = f"Playback error: {exc}"
        try:
            self.player.update(__import__("pygame"))
        except Exception as exc:
            self.logger.exception("Avatar playback update failed")
            self.player.stop()
            self._hold_background_for_playback = False
            self._turn_active = False
            background_network.set_paused(False)
            self.status = f"Playback error: {exc}"
        if self._apparition_pending and (self.player.has_frame or not self.player.playing):
            self._apparition_pending = False
        if self._hold_background_for_playback and not self.player.playing:
            self._hold_background_for_playback = False
            self._turn_active = False
            self._turn_profile = None
            self.status = "Ready: SPACE to talk"
            background_network.set_paused(False)
            self.logger.info("Avatar playback complete; background network requests resumed")
        elif self._turn_active and self.status == "Playing" and not self.player.playing:
            self._turn_active = False
            self._turn_profile = None
            self.status = "Ready: SPACE to talk"
        if not self.player.playing and self._deferred_cache and not self._cache_downloading:
            pending = self._deferred_cache; self._deferred_cache = None; self._cache_downloading = True
            threading.Thread(target=self._save_after_playback, args=(pending,), daemon=True, name="avatar-cache-save").start()

    def _save_after_playback(self, pending):
        try:
            self.logger.info("Avatar playback complete; downloading response for cache")
            self.fal.download_video(pending["url"], pending["staging"])
            record = self.cache.add_clip(pending["staging"], spoken_text=pending["text"], intent=pending["intent"], model=pending["model"], reference_sha256=pending["reference_hash"], tags=sorted(time_of_day_tags()), duration_seconds=pending["duration_seconds"], metadata={"transcript": pending["transcript"], "prompt_version": "portrait-v4-avatar", "avatar": pending["avatar"]})
            self.logger.info("Avatar response saved to cache: %s", record["media_path"])
        except Exception:
            self.logger.exception("Avatar background cache save failed")
        finally:
            self._cache_downloading = False

    def draw(self, screen, position):
        width, height = int(position.get("width", self.size)), int(position.get("height", self.size))
        self._bounds = (width, height)
        # Keep the portrait visible while the background decoder buffers its
        # first frame; otherwise streaming introduces a black transition.
        if self.player.has_frame:
            self.player.draw(screen, position)
        elif self._portrait is not None and self._alpha > 0.01 and not self._apparition_pending:
            scale = min(width / self._portrait.get_width(), height / self._portrait.get_height())
            image = pygame.transform.smoothscale(self._portrait, (max(1, int(self._portrait.get_width() * scale)), max(1, int(self._portrait.get_height() * scale))))
            image.set_alpha(int(255 * self._alpha))
            x = position.get("x", 0) + (width - image.get_width()) // 2; y = position.get("y", 0) + (height - image.get_height()) // 2
            screen.blit(image, (x, y))
        font = pygame.font.Font(None, 26); label = font.render(self.status, True, (242, 222, 172)); label.set_alpha(235)
        screen.blit(label, (position.get("x", 0) + 12, position.get("y", 0) + 12))
        # Temporary Pi troubleshooting overlay.  It never displays signed URLs,
        # prompts, keys, or transcribed speech; only the current local stage.
        if os.getenv("AVATAR_DEBUG_OVERLAY", "1").lower() in ("1", "true", "yes", "on"):
            debug_font = pygame.font.Font(None, 19)
            lines = [f"AVATAR DEBUG - {self.profile.name}", f"stage: {self.status}", f"source: {self._playback_label}", self.player.diagnostic(), f"apparition_pending={self._apparition_pending} queue={self.ready.qsize()}"]
            y = position.get("y", 0) + 42
            for line in lines:
                debug = debug_font.render(line, True, (180, 230, 255)); debug.set_alpha(245)
                screen.blit(debug, (position.get("x", 0) + 12, y)); y += 18
    def cleanup(self):
        background_network.set_paused(False)
        self._stop_warmed_microphone()
        self.player.cleanup()
