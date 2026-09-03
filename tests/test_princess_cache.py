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
            cache.add_clip(media, spoken_text=" Well   Hello there! ", intent="greeting", model="model", reference_sha256=ref)
            found = cache.lookup("well hello there", ref, "model")
            self.assertIsNotNone(found)
            cache.mark_used(found["id"])
            self.assertEqual(cache.inspect()[0]["use_count"], 1)
            self.assertEqual(normalize_text("A  TEST?!"), "a test")

    def test_corrupt_media_is_quarantined_and_export_import_verifies(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); media = root / "clip.mp4"; media.write_bytes(b"mp4")
            cache = PrincessCache(root / "one"); ref = "b" * 64
            cache.add_clip(media, spoken_text="hello", intent="greeting", model="model", reference_sha256=ref)
            bundle = cache.export_bundle(root / "bundle.zip")
            imported = PrincessCache(root / "two")
            self.assertEqual(imported.import_bundle(bundle), 1)
            row = cache.inspect()[0]; (cache.root / row["media_path"]).write_bytes(b"tampered")
            self.assertIsNone(cache.lookup("hello", ref, "model"))
            self.assertEqual(cache.inspect()[0]["status"], "quarantined")

if __name__ == "__main__": unittest.main()
