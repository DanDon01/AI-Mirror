from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
from princess_cache import PrincessCache, normalize_text

class PrincessCacheTests(unittest.TestCase):
    def test_normalization_lookup_and_use_tracking(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); media = root / "clip.mp4"; media.write_bytes(b"mp4")
            cache = PrincessCache(root / "library")
            ref = "a" * 64
            cache.add_clip(media, spoken_text=" Well   Hello there! ", intent="greeting", model="model", reference_sha256=ref, tags=["morning"])
            found = cache.lookup("well hello there", ref, "model")
            self.assertIsNotNone(found)
            cache.mark_used(found["id"])
            self.assertEqual(cache.inspect()[0]["use_count"], 1)
            self.assertEqual(cache.health()["approved"], 1)
            self.assertEqual(cache.select("unseen", ref, "model", intent="greeting", when=__import__('datetime').datetime(2026, 9, 3, 9))["id"], found["id"])
            self.assertEqual(normalize_text("A  TEST?!"), "a test")

    def test_corrupt_media_is_quarantined_and_export_import_verifies(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); media = root / "clip.mp4"; media.write_bytes(b"mp4")
            cache = PrincessCache(root / "one"); ref = "b" * 64
            cache.add_clip(media, spoken_text="hello", intent="greeting", model="model", reference_sha256=ref, tags=["evening"])
            bundle = cache.export_bundle(root / "bundle.zip")
            imported = PrincessCache(root / "two")
            self.assertEqual(imported.import_bundle(bundle), 1)
            row = cache.inspect()[0]; (cache.root / row["media_path"]).write_bytes(b"tampered")
            self.assertIsNone(cache.lookup("hello", ref, "model"))
            self.assertEqual(cache.inspect()[0]["status"], "quarantined")

    def test_promotes_old_generic_clip_using_its_transcript(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); media = root / "clip.mp4"; media.write_bytes(b"mp4")
            cache = PrincessCache(root / "library"); ref = "c" * 64
            cache.add_clip(media, spoken_text="Good evening, darling.", intent="greeting", model="model", reference_sha256=ref, tags=["night"], metadata={"transcript": "Good evening"})
            self.assertEqual(cache.promote_matching_transcript("good evening", "greeting_evening"), 1)
            found = cache.select("good evening", ref, "model", intent="greeting_evening", when=__import__('datetime').datetime(2026, 9, 3, 23))
            self.assertIsNotNone(found)

if __name__ == "__main__": unittest.main()
