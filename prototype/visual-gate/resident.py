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
import threading
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("resident")

UNPROMPTED_INTENTS = {"greeting", "greeting_morning", "greeting_afternoon",
                      "greeting_evening", "wellbeing", "night", "plans"}
CUE_INTENTS = {"weather", "calendar", "smarthome", "news"}


class BrowserPlayer:
    """Duck-types AvatarPlayer: 'playing' until the page says it finished."""

    def __init__(self, publish, media_url, max_seconds=45):
        self._publish = publish
        self._media_url = media_url
        self._max = max_seconds
        self._playing = False
        self._since = 0.0
        self.token = None
        self.label = "none"

    @property
    def playing(self):
        return self._playing

    @property
    def has_frame(self):
        return self._playing

    def play(self, path, size=None, kind="reply"):
        src = str(path)
        if not src.startswith(("http://", "https://")):
            src = self._media_url(Path(path))
        if "apparition" in str(path):
            kind = "apparition"
        self.token = secrets.token_hex(6)
        self._playing = True
        self._since = time.monotonic()
        self.label = kind
        self._publish({"type": "resident", "state": "speaking", "src": src,
                       "clip": self.token, "kind": kind})

    def finished(self, token):
        # An apparition ending late must not end the reply that replaced it.
        if token == self.token:
            self._playing = False

    def update(self, _pygame=None):
        if self._playing and time.monotonic() - self._since > self._max:
            logger.warning("resident clip never reported finished; releasing it")
            self._playing = False

    def stop(self):
        if self._playing:
            self._publish({"type": "resident", "state": "stop"})
        self._playing = False

    def draw(self, *args, **kwargs):
        pass

    def cleanup(self):
        self.stop()

    def diagnostic(self):
        return f"browser clip={self.label} playing={self._playing}"


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
            super().__init__(size=480)
            self.player = BrowserPlayer(self._publish, self.media_url)

        # ---- events --------------------------------------------------
        def _publish(self, event):
            self._publish_event(event)

        def media_url(self, path: Path):
            path = Path(path).resolve()
            allowed = [self.cache.root.resolve(), self.profile.apparition_dir.resolve(),
                       Path(__file__).resolve().parents[2] / "assets"]
            if not any(str(path).startswith(str(root)) for root in allowed) or not path.is_file():
                raise ValueError("clip is outside the avatar library")
            token = secrets.token_urlsafe(12)
            self._media[token] = path
            if len(self._media) > 64:
                for old in list(self._media)[:-64]:
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

        def tick(self):
            self.update()
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
                self._turn["reply"] = text
                self._turn["source"] = "generated"
                return original(reference, text, *args, **kwargs)

            self.fal.generate_from_text = spy
            try:
                super()._make_video(context_snapshot, transcript, profile)
            finally:
                self.fal.generate_from_text = original
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
