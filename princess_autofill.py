"""Background fal generation for reusable Princess responses."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from queue import Queue
import threading
import os
from princess_cache import PrincessCache, time_of_day_tags, TIME_SENSITIVE_INTENTS
from princess_services import FlashTalkService

class PrincessAutoFiller:
    def __init__(self, cache: PrincessCache, reference: str | Path, model: str, prompt: str):
        self.cache, self.reference, self.model, self.prompt = cache, Path(reference), model, prompt
        self.queue = Queue(); self.pending = set(); self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True, name="princess-autofill"); self.thread.start()

    def enqueue(self, text: str, intent: str = "general") -> bool:
        normalized = " ".join(text.casefold().split())
        if not normalized or intent.casefold() in TIME_SENSITIVE_INTENTS or normalized in self.pending: return False
        self.pending.add(normalized); self.queue.put((text, intent)); return True

    def _run(self):
        while self.running:
            try: text, intent = self.queue.get(timeout=0.5)
            except Exception: continue
            key = " ".join(text.casefold().split())
            try:
                tags = sorted(time_of_day_tags())
                out = self.cache.root / "staging" / (key[:40].replace(" ", "_") + ".mp4")
                result = FlashTalkService().generate_from_text(self.reference, text, out, model=self.model, prompt=self.prompt, duration_seconds=5)
                self.cache.add_clip(out, spoken_text=text, intent=intent, model=self.model, reference_sha256=os.getenv("PRINCESS_REFERENCE_SHA256", "4372362f69934d09af6b156ff5e71183d4b2c3c36155c6361d0f566a09ec7def"), tags=tags, duration_seconds=result.duration_seconds, metadata={"autofill": True})
                out.unlink(missing_ok=True)
            except Exception:
                pass
            finally:
                self.pending.discard(key); self.queue.task_done()

    def stop(self): self.running = False
