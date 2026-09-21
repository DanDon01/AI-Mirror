"""Tests for selectable talking-avatar characters."""

from pathlib import Path
import tempfile
import unittest

from avatar_profiles import AvatarProfiles, PROFILE_SPECS


class AvatarProfilesTests(unittest.TestCase):
    def _asset_root(self, root):
        assets = Path(root) / "avatars"
        prompts = assets / "prompts"
        prompts.mkdir(parents=True)
        for key, _name, _description, filename in PROFILE_SPECS:
            (assets / filename).write_bytes((key + " image").encode("utf-8"))
            (prompts / f"{key}.txt").write_text(key + " persona", encoding="utf-8")
        return assets

    def test_catalogue_contains_all_requested_characters(self):
        with tempfile.TemporaryDirectory() as temp:
            profiles = AvatarProfiles(
                self._asset_root(temp), Path(temp) / "selection.json"
            )
            self.assertEqual(
                [item["key"] for item in profiles.options()],
                ["mechanic", "officer", "master_control", "commander", "bert"],
            )

    def test_selection_is_persisted_and_reloaded(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "data" / "selection.json"
            assets = self._asset_root(temp)
            profiles = AvatarProfiles(assets, state)
            selected = profiles.select("bert")
            self.assertEqual(selected.name, "Bert")
            self.assertEqual(AvatarProfiles(assets, state).current().key, "bert")

    def test_missing_reference_cannot_be_selected(self):
        with tempfile.TemporaryDirectory() as temp:
            assets = self._asset_root(temp)
            (assets / "Officer.png").unlink()
            profiles = AvatarProfiles(assets, Path(temp) / "selection.json")
            with self.assertRaises(FileNotFoundError):
                profiles.select("officer")

    def test_reference_hash_separates_character_video_caches(self):
        with tempfile.TemporaryDirectory() as temp:
            profiles = AvatarProfiles(
                self._asset_root(temp), Path(temp) / "selection.json"
            )
            self.assertNotEqual(
                profiles.get("mechanic").reference_hash(),
                profiles.get("commander").reference_hash(),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
