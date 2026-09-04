"""Persistent, checksum-backed Princess response library (Phase 3)."""

from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import zipfile


def normalize_text(text: str) -> str:
    return " ".join(text.casefold().split()).strip(" .!?\t\r\n")

TIME_TAGS = ("morning", "afternoon", "evening", "night")
TIME_SENSITIVE_INTENTS = {"news", "weather", "stocks", "calendar", "events", "traffic", "smarthome"}

def time_of_day_tags(when: datetime | None = None) -> set[str]:
    hour = (when or datetime.now()).hour
    if 5 <= hour < 12: return {"morning"}
    if 12 <= hour < 17: return {"afternoon"}
    if 17 <= hour < 22: return {"evening"}
    return {"night"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PrincessCache:
    def __init__(self, root: str | Path = "data/princess/library"):
        self.root = Path(root).resolve()
        self.media = self.root / "media"
        self.quarantine_dir = self.root / "quarantine"
        self.db_path = self.root / "princess.sqlite3"
        self.root.mkdir(parents=True, exist_ok=True)
        self.media.mkdir(exist_ok=True)
        self.quarantine_dir.mkdir(exist_ok=True)
        self._init_db()

    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _db(self):
        db = self._connect()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def _init_db(self):
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS clips (
                id INTEGER PRIMARY KEY, cache_key TEXT NOT NULL UNIQUE,
                spoken_text TEXT NOT NULL, normalized_text TEXT NOT NULL,
                intent TEXT NOT NULL, tags_json TEXT NOT NULL,
                model TEXT NOT NULL, reference_sha256 TEXT NOT NULL,
                media_path TEXT NOT NULL, media_sha256 TEXT NOT NULL,
                duration_seconds REAL, metadata_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'approved', use_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, last_used_at TEXT
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_clips_lookup ON clips(normalized_text, reference_sha256, status)")

    def add_clip(self, media_path: str | Path, *, spoken_text: str, intent: str,
                 model: str, reference_sha256: str, tags: list[str] | None = None,
                 duration_seconds: float | None = None, metadata: dict | None = None) -> dict:
        source = Path(media_path).resolve()
        if not source.is_file() or source.stat().st_size == 0:
            raise ValueError("media file does not exist or is empty")
        if intent.casefold() in TIME_SENSITIVE_INTENTS:
            raise ValueError(f"time-sensitive intent is not reusable: {intent}")
        tags = tags or []
        if not set(tags).intersection(TIME_TAGS):
            raise ValueError("pooled responses require at least one time-of-day tag")
        media_hash = _sha256(source)
        destination = self.media / f"{media_hash}.mp4"
        if not destination.exists():
            partial = destination.with_suffix(".mp4.partial")
            shutil.copyfile(source, partial)
            partial.replace(destination)
        normalized = normalize_text(spoken_text)
        cache_key = hashlib.sha256(f"{normalized}|{reference_sha256}|{model}|{media_hash}".encode()).hexdigest()
        record = {"cache_key": cache_key, "spoken_text": spoken_text, "normalized_text": normalized,
                  "intent": intent, "tags": tags, "model": model, "reference_sha256": reference_sha256,
                  "media_path": str(destination.relative_to(self.root)).replace("\\", "/"),
                  "media_sha256": media_hash, "duration_seconds": duration_seconds,
                  "metadata": metadata or {}, "status": "approved", "created_at": _now()}
        with self._db() as db:
            db.execute("""INSERT OR IGNORE INTO clips
                (cache_key,spoken_text,normalized_text,intent,tags_json,model,reference_sha256,media_path,media_sha256,duration_seconds,metadata_json,status,created_at)
                VALUES (:cache_key,:spoken_text,:normalized_text,:intent,:tags,:model,:reference_sha256,:media_path,:media_sha256,:duration_seconds,:metadata,:status,:created_at)""",
                {**record, "tags": json.dumps(record["tags"]), "metadata": json.dumps(record["metadata"])})
        return record

    def lookup(self, spoken_text: str, reference_sha256: str, model: str) -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM clips WHERE normalized_text=? AND reference_sha256=? AND model=? AND status='approved' ORDER BY use_count, id LIMIT 1",
                             (normalize_text(spoken_text), reference_sha256, model)).fetchone()
        if not row:
            return None
        result = dict(row)
        path = self.root / result["media_path"]
        if not path.is_file() or _sha256(path) != result["media_sha256"]:
            self.quarantine(result["id"])
            return None
        return result

    def mark_used(self, clip_id: int) -> None:
        with self._db() as db:
            db.execute("UPDATE clips SET use_count=use_count+1,last_used_at=? WHERE id=?", (_now(), clip_id))

    def promote_matching_transcript(self, transcript: str, intent: str) -> int:
        """Upgrade old generic clips once their conversational intent is recognised."""
        wanted = normalize_text(transcript)
        if not wanted or intent == "general":
            return 0
        promoted = 0
        with self._db() as db:
            rows = db.execute("SELECT id, intent, metadata_json FROM clips WHERE intent<>? AND status='approved'", (intent,)).fetchall()
            for row in rows:
                try:
                    original = json.loads(row["metadata_json"]).get("transcript", "")
                except (TypeError, json.JSONDecodeError):
                    continue
                if normalize_text(original) == wanted:
                    db.execute("UPDATE clips SET intent=? WHERE id=?", (intent, row["id"]))
                    promoted += 1
        return promoted

    def quarantine(self, clip_id: int) -> None:
        with self._db() as db:
            row = db.execute("SELECT media_path FROM clips WHERE id=?", (clip_id,)).fetchone()
            if not row: return
            path = self.root / row["media_path"]
            if path.exists(): path.replace(self.quarantine_dir / path.name)
            db.execute("UPDATE clips SET status='quarantined' WHERE id=?", (clip_id,))

    def inspect(self) -> list[dict]:
        with self._db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM clips ORDER BY id")]

    def health(self, intent: str | None = None) -> dict:
        rows = self.inspect()
        if intent: rows = [row for row in rows if row["intent"] == intent]
        return {"total": len(rows), "approved": sum(r["status"] == "approved" for r in rows),
                "quarantined": sum(r["status"] == "quarantined" for r in rows),
                "by_intent": {name: sum(r["intent"] == name and r["status"] == "approved" for r in rows)
                               for name in sorted({r["intent"] for r in rows})}}

    def select(self, spoken_text: str, reference_sha256: str, model: str, *, intent: str = "general", when: datetime | None = None) -> dict | None:
        exact = self.lookup(spoken_text, reference_sha256, model)
        if exact: return exact
        rows = [r for r in self.inspect() if r["intent"] == intent and r["status"] == "approved"
                and time_of_day_tags(when).intersection(json.loads(r["tags_json"]))]
        if not rows: return None
        rows.sort(key=lambda row: (row["use_count"], row["last_used_at"] or "", row["id"]))
        return rows[0]

    def export_bundle(self, destination: str | Path) -> Path:
        destination = Path(destination).resolve(); destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(self.db_path, "princess.sqlite3")
            for row in self.inspect():
                path = self.root / row["media_path"]
                if path.is_file(): archive.write(path, row["media_path"])
        return destination

    def import_bundle(self, bundle: str | Path) -> int:
        count = 0
        with tempfile.TemporaryDirectory() as temp:
            with zipfile.ZipFile(bundle) as archive: archive.extractall(temp)
            source_db = Path(temp) / "princess.sqlite3"
            source = sqlite3.connect(source_db)
            try:
                source.row_factory = sqlite3.Row
                for row in source.execute("SELECT * FROM clips WHERE status='approved'"):
                    source_media = Path(temp) / row["media_path"]
                    if not source_media.is_file() or _sha256(source_media) != row["media_sha256"]: continue
                    target = self.media / source_media.name
                    if not target.exists(): shutil.copyfile(source_media, target)
                    self.add_clip(source_media, spoken_text=row["spoken_text"], intent=row["intent"], model=row["model"], reference_sha256=row["reference_sha256"], tags=json.loads(row["tags_json"]), duration_seconds=row["duration_seconds"], metadata=json.loads(row["metadata_json"]))
                    count += 1
            finally:
                source.close()
        return count
