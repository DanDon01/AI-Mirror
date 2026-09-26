"""The resident: the existing avatar pipeline, playing in the browser.

AvatarModule already does the hard parts - a warmed microphone, local Vosk
speech-to-text, one short OpenAI reply, Fal talking-head video, and a
checksummed clip pool. In the Pygame app it decodes the result with ffmpeg
into a surface. Here the same module runs inside the bridge, and its player
is replaced by one that hands each clip to the page over the event stream;
the page plays it in a portal and reports back when it has finished.

What this adds on top of AvatarModule:

  - stage events (listening, thinking, conjuring, speaking, idle, error)
    so the glass can stage the unavoidable wait as theatre;
  - an intent cue as soon as the question is understood (weather,
    calendar, smarthome, news), so the relevant part of the mirror comes
    forward while the resident is still answering;
  - a journal of every turn (data/avatar/journal.jsonl): time, character,
    what was asked, what was said, whether it came from the pool or was
    generated. Time-sensitive replies are journalled but never pooled;
  - unprompted speech from the pool only - never a new API call. Only
    time-independent clips (greetings, wellbeing, night, plans) for the
    current character and time of day, with no numbers in them (a spoken
    figure could be a stale fact), each at most once a day.

Media is served by opaque token (/api/resident/media?t=...), never by path,
so the page cannot be used to read arbitrary files.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("resident")

UNPROMPTED_INTENTS = {"greeting", "greeting_morning", "greeting_afternoon",
                      "greeting_evening", "wellbeing", "night", "plans"}
CUE_INTENTS = {"weather", "calendar", "smarthome", "news"}
THEATRE_ROOT = Path(__file__).resolve().parents[2] / "data" / "avatar" / "theatre"


class BrowserPlayer:
    """Duck-types AvatarPlayer. The page shows the video (muted); the sound
    is played here exactly as the Pygame avatar did - ffmpeg decoding the
    same clip into aplay, on VOICE_SPEAKER if set - because that path is
    proven on the Pi, whereas Chromium's own audio output under a systemd
    service may go to another device or nowhere. 'playing' until the page
    says the clip finished (or a safety timeout)."""

    def __init__(self, publish, media_url, max_seconds=45):
        self._publish = publish
        self._media_url = media_url
        self._max = max_seconds
        self._playing = False
        self._since = 0.0
        self._decoder = None
        self._audio = None
        self._pending_audio = None
        self.audio_note = "idle"
        self.token = None
        self.label = "none"

    @property
    def playing(self):
        return self._playing

    @property
    def has_frame(self):
        return self._playing

    def play(self, path, size=None, kind="reply"):
        raw = str(path)
        local = not raw.startswith(("http://", "https://"))
        src = self._media_url(Path(path)) if local else raw
        self.token = secrets.token_hex(6)
        self._playing = True
        self._since = time.monotonic()
        self.label = kind + (" (local clip)" if local else " (Fal stream)")
        # The page may hold the reply until the current theatre clip reaches
        # its reference frame, so the sound starts when the page says the
        # reply video has actually started - not now - to stay in sync.
        self._pending_audio = str(Path(path).resolve()) if local else raw
        self.audio_note = "waiting for the video to start"
        self._publish({"type": "resident", "state": "speaking", "src": src,
                       "clip": self.token, "kind": kind})

    def started(self, token):
        if token == self.token and self._pending_audio:
            source, self._pending_audio = self._pending_audio, None
            self._since = time.monotonic()
            self._start_audio(source)

    def _start_audio(self, source):
        self._stop_audio()
        ffmpeg, aplay = shutil.which("ffmpeg"), shutil.which("aplay")
        if not ffmpeg or not aplay:
            self.audio_note = "silent: ffmpeg or aplay not installed"
            return
        speaker = os.getenv("VOICE_SPEAKER", "").strip()
        command = [aplay, "-q"] + (["-D", speaker] if speaker else [])
        try:
            self._decoder = subprocess.Popen(
                [ffmpeg, "-re", "-loglevel", "error", "-i", source, "-vn", "-f", "wav", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self._audio = subprocess.Popen(command, stdin=self._decoder.stdout,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            self._decoder.stdout.close()
            self.audio_note = "playing via aplay " + (speaker or "(ALSA default)")
        except Exception as exc:
            self.audio_note = f"audio failed to start: {exc}"
            logger.exception("resident audio failed to start")

    def _stop_audio(self):
        for proc in (self._audio, self._decoder):
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=0.4)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self._audio = self._decoder = None

    def _audio_state(self):
        """Report how the audio ended: an aplay/ffmpeg error is exactly what
        someone standing at a silent mirror needs to read."""
        for name, proc in (("aplay", self._audio), ("ffmpeg", self._decoder)):
            if proc is None or proc.poll() is None:
                continue
            if proc.returncode not in (0, None):
                err = b""
                try:
                    err = proc.stderr.read() if proc.stderr else b""
                except Exception:
                    pass
                line = err.decode("utf-8", "replace").strip().splitlines()
                self.audio_note = f"{name} exited {proc.returncode}: " + (line[-1][:120] if line else "no message")
        if self._audio is not None and self._audio.poll() == 0 and "playing" in self.audio_note:
            self.audio_note = "finished cleanly"
        return self.audio_note

    def finished(self, token):
        # An apparition ending late must not end the reply that replaced it.
        if token == self.token:
            self._playing = False
            self._audio_state()
            self._stop_audio()

    def update(self, _pygame=None):
        self._audio_state()
        # Waiting for the page to start the clip gets its own, shorter limit.
        limit = 30 if self._pending_audio else self._max
        if self._playing and time.monotonic() - self._since > limit:
            logger.warning("resident clip never reported finished; releasing it")
            self._playing = False
            self._stop_audio()

    def stop(self):
        if self._playing:
            self._publish({"type": "resident", "state": "stop"})
        self._playing = False
        self._pending_audio = None
        self._stop_audio()

    def draw(self, *args, **kwargs):
        pass

    def cleanup(self):
        self.stop()

    def diagnostic(self):
        age = f"{time.monotonic() - self._since:.1f}s" if self._playing else "-"
        return f"clip={self.label} playing={self._playing} age={age}"


def _make_resident_class():
    from avatar_module import AvatarModule, _intent_for

    class Resident(AvatarModule):
        def __init__(self, publish, root: Path, tuning):
            self._publish_event = publish
            self._media = {}
            self._tuning = tuning
            self._journal_path = root / "journal.jsonl"
            self._played_path = root / "unprompted.json"
            self._turn = {}
            self._last_state = None
            self._last_unprompted = 0.0
            self._marks = {}
            self._last_debug = None
            self._last_debug_at = 0.0
            self.last_turn = {}
            super().__init__(size=480)
            self.player = BrowserPlayer(self._publish, self.media_url)
            original_play = self.player.play

            def play(path, size=None, kind="reply"):
                if "apparition" not in str(path):
                    self._mark("play")
                return original_play(path, size, kind)

            self.player.play = play

        # ---- events --------------------------------------------------
        def _publish(self, event):
            self._publish_event(event)

        def _play_apparition(self):
            # The page plays the appear clip from the theatre pool itself,
            # so it can chain appear -> listening -> thinking seamlessly.
            return

        def theatre_pool(self):
            """This character's appear / think / idle clips, as media tokens.
            Made offline by avatar_theatre.py; older apparition clips count as
            appear clips when no new ones exist."""
            root = THEATRE_ROOT / self.profile.key
            pool = {}
            for kind in ("appear", "think", "idle"):
                clips = sorted((root / kind).glob("*.mp4"))
                if kind == "appear" and not clips:
                    clips = sorted(self.profile.apparition_dir.glob("*.mp4"))
                pool[kind] = [self.media_url(c) for c in clips]
            pool["character"] = self.profile.key
            return pool

        def media_url(self, path: Path):
            path = Path(path).resolve()
            allowed = [self.cache.root.resolve(), self.profile.apparition_dir.resolve(),
                       THEATRE_ROOT.resolve(), Path(__file__).resolve().parents[2] / "assets"]
            if not any(str(path).startswith(str(root)) for root in allowed) or not path.is_file():
                raise ValueError("clip is outside the avatar library")
            token = secrets.token_urlsafe(12)
            self._media[token] = path
            if len(self._media) > 256:
                for old in list(self._media)[:-256]:
                    self._media.pop(old, None)
            return "api/resident/media?t=" + token

        def media_path(self, token):
            return self._media.get(token)

        def _state_for(self, status):
            s = (status or "").lower()
            if s.startswith("listening"):
                return "listening"
            if "transcrib" in s or "asking" in s or "conjuring" in s:
                return "thinking"
            if "creating" in s:
                return "conjuring"
            if s.startswith(("streaming", "playing", "cache hit")):
                return "speaking"
            if s.startswith(("error", "mic error", "stt error", "playback error")):
                return "error"
            return "idle"

        # ---- the on-mirror debug panel (as the Pygame AVATAR DEBUG overlay)
        def _mark(self, name):
            self._marks[name] = time.monotonic()

        def debug_snapshot(self):
            m = self._marks
            base = m.get("stop") or m.get("start")
            def since(key):
                return f"{m[key] - base:.1f}s" if base and key in m and m[key] >= base else "-"
            return {
                "character": self.profile.name,
                "stage": self.status,
                "mic": ("streaming " if self._streaming_capture else "per-turn ") + str(self.device),
                "vosk": "loaded" if self._vosk_model is not None else "not loaded (VOSK_MODEL_PATH?)",
                "openai": "ready" if self.openai_client is not None else "not ready",
                "source": self.player.label,
                "audio": self.player.audio_note,
                "player": self.player.diagnostic(),
                "timings": f"heard {since('transcript')}  reply {since('reply')}  video {since('video')}  playing {since('play')}",
            }

        def _start_recording(self):
            self._marks = {}
            self._mark("start")
            super()._start_recording()

        def _stop_recording(self):
            self._mark("stop")
            super()._stop_recording()

        def tick(self):
            self.update()
            snap = self.debug_snapshot()
            now = time.monotonic()
            if snap != self._last_debug and now - self._last_debug_at > 0.25:
                self._last_debug, self._last_debug_at = snap, now
                show = os.getenv("AVATAR_DEBUG_OVERLAY", "1").lower() in ("1", "true", "yes", "on")
                self._publish({"type": "resident", "debug": snap, "show": show})
            state = self._state_for(self.status)
            if state == "speaking" and not self.player.playing and not self._turn_active:
                state = "idle"
            if state != self._last_state:
                self._last_state = state
                event = {"type": "resident", "state": state, "character": self.profile.name}
                if state == "error":
                    event["detail"] = "The resident could not answer just now"
                self._publish(event)

        # ---- turn hooks ----------------------------------------------
        def _on_transcript(self, text):
            self._mark("transcript")
            self._turn["transcript"] = text
            intent = _intent_for(text or "")
            self._turn["intent"] = intent
            if intent in CUE_INTENTS:
                self._publish({"type": "resident", "cue": intent})

        def _transcribe_local(self, path):
            text = super()._transcribe_local(path)
            self._on_transcript(text)
            return text

        def _make_video(self, context_snapshot=None, transcript=None, profile=None):
            profile = profile or self._turn_profile or self.profile
            self._turn = {"at": datetime.now().isoformat(timespec="seconds"),
                          "character": profile.key, "source": "cache"}
            if transcript:
                self._on_transcript(transcript)
            original = self.fal.generate_from_text

            def spy(reference, text, *args, **kwargs):
                self._mark("reply")
                self._turn["reply"] = text
                self._turn["source"] = "generated"
                ready = kwargs.get("on_video_ready")
                if ready is not None:
                    def on_ready(url):
                        self._mark("video")
                        return ready(url)
                    kwargs["on_video_ready"] = on_ready
                return original(reference, text, *args, **kwargs)

            self.fal.generate_from_text = spy
            try:
                super()._make_video(context_snapshot, transcript, profile)
            finally:
                self.fal.generate_from_text = original
                if "video" not in self._marks:
                    self._mark("video")
                self.last_turn = dict(self._turn, timings=self.debug_snapshot()["timings"],
                                      outcome=self.status)
                self._journal()

        def _journal(self):
            try:
                self._journal_path.parent.mkdir(parents=True, exist_ok=True)
                with self._journal_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(self._turn, ensure_ascii=False) + "\n")
            except OSError:
                logger.exception("resident journal write failed")

        # ---- unprompted ----------------------------------------------
        def _played_today(self):
            try:
                data = json.loads(self._played_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            today = datetime.now().strftime("%Y-%m-%d")
            return {int(k) for k, v in data.items() if v == today}, data

        def pick_unprompted(self, when=None):
            from avatar_cache import time_of_day_tags
            profile = self.profile
            reference = profile.reference_hash()
            tags = time_of_day_tags(when)
            played, _ = self._played_today()
            rows = []
            for r in self.cache.inspect():
                if r["status"] != "approved" or r["intent"] not in UNPROMPTED_INTENTS:
                    continue
                if r["reference_sha256"] != reference or not r["model"].endswith("::" + profile.key):
                    continue
                if not tags.intersection(json.loads(r["tags_json"])):
                    continue
                if re.search(r"\d", r["spoken_text"]) or r["id"] in played:
                    continue
                if not (self.cache.root / r["media_path"]).is_file():
                    continue
                rows.append(r)
            rows.sort(key=lambda r: (r["use_count"], r["last_used_at"] or "", r["id"]))
            return rows[0] if rows else None

        def speak_unprompted(self, cooldown_minutes=30):
            if self._turn_active or self.recording or self.player.playing:
                return None
            if time.time() - self._last_unprompted < cooldown_minutes * 60:
                return None
            clip = self.pick_unprompted()
            if clip is None:
                return None
            self._last_unprompted = time.time()
            self.cache.mark_used(clip["id"])
            _, played = self._played_today()
            played[str(clip["id"])] = datetime.now().strftime("%Y-%m-%d")
            try:
                self._played_path.write_text(json.dumps(played), encoding="utf-8")
            except OSError:
                pass
            self.player.play(self.cache.root / clip["media_path"], kind="unprompted")
            self._journal_unprompted(clip)
            return clip["id"]

        def _journal_unprompted(self, clip):
            self._turn = {"at": datetime.now().isoformat(timespec="seconds"),
                          "character": self.profile.key, "source": "pool-unprompted",
                          "reply": clip["spoken_text"], "intent": clip["intent"], "clip": clip["id"]}
            self._journal()

        def last_turn_summary(self):
            t = self.last_turn or {}
            return {k: t.get(k) for k in ("at", "transcript", "reply", "intent", "source", "timings", "outcome")}

        def pool_summary(self):
            health = self.cache.health()
            return {"character": self.profile.name, "total": health["approved"],
                    "by_intent": health["by_intent"]}

    return Resident


def start(publish, tuning):
    """Construct the resident, or return None when the avatar stack is not
    available (no pygame, no API key, disabled by VISUAL_GATE_RESIDENT=0).
    A mirror without a resident is still a complete mirror."""
    if os.getenv("VISUAL_GATE_RESIDENT", "1").lower() in ("0", "false", "no", "off"):
        logger.info("resident disabled by VISUAL_GATE_RESIDENT")
        return None
    try:
        import functools
        import avatar_module
        from avatar_cache import AvatarCache
        # AvatarCache defaults to a path relative to the working directory,
        # and this service runs from prototype/visual-gate. Bind it to the
        # project's own library - the pool the Pygame avatar has been
        # filling - rather than silently starting an empty one here.
        project = Path(__file__).resolve().parents[2]
        library = project / "data" / "avatar" / "library"
        avatar_module.AvatarCache = functools.partial(AvatarCache, library)
        resident = _make_resident_class()(publish, library.parent, tuning)
    except Exception as exc:
        logger.warning("resident unavailable: %s", exc)
        return None

    def loop():
        while True:
            try:
                resident.tick()
            except Exception:
                logger.exception("resident tick failed")
            time.sleep(0.1)

    threading.Thread(target=loop, daemon=True, name="resident").start()
    return resident
