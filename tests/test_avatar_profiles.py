"""Tests for selectable talking-avatar characters."""

import json
from pathlib import Path
import tempfile
import unittest

from avatar_profiles import AvatarProfiles, NoAvatarsConfigured

# A sample catalogue, as a house pack's avatars/profiles.json would hold it.
SPECS = [
    {"key": "pilot", "name": "Pilot", "description": "Calm", "image": "Pilot.png"},
    {"key": "robot", "name": "Robot", "description": "Creaky", "image": "Robot.png"},
    {"key": "wizard", "name": "Wizard", "description": "Grand", "image": "Wizard.png"},
]


class AvatarProfilesTests(unittest.TestCase):
    def _asset_root(self, root):
        assets = Path(root) / "avatars"
        prompts = assets / "prompts"
        prompts.mkdir(parents=True)
        (assets / "profiles.json").write_text(json.dumps(SPECS), encoding="utf-8")
        for spec in SPECS:
            (assets / spec["image"]).write_bytes((spec["key"] + " image").encode("utf-8"))
            (prompts / f"{spec['key']}.txt").write_text(spec["key"] + " persona", encoding="utf-8")
        return assets

    def test_catalogue_comes_from_the_house_pack(self):
        with tempfile.TemporaryDirectory() as temp:
            profiles = AvatarProfiles(
                self._asset_root(temp), Path(temp) / "selection.json"
            )
            self.assertEqual(
                [item["key"] for item in profiles.options()],
                ["pilot", "robot", "wizard"],
            )

    def test_no_profiles_means_no_avatar(self):
        with tempfile.TemporaryDirectory() as temp:
            profiles = AvatarProfiles(Path(temp) / "avatars", Path(temp) / "selection.json")
            self.assertEqual(profiles.options(), [])
            with self.assertRaises(NoAvatarsConfigured):
                profiles.current()

    def test_selection_is_persisted_and_reloaded(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "data" / "selection.json"
            assets = self._asset_root(temp)
            profiles = AvatarProfiles(assets, state)
            selected = profiles.select("robot")
            self.assertEqual(selected.name, "Robot")
            self.assertEqual(AvatarProfiles(assets, state).current().key, "robot")

    def test_missing_reference_cannot_be_selected(self):
        with tempfile.TemporaryDirectory() as temp:
            assets = self._asset_root(temp)
            (assets / "Wizard.png").unlink()
            profiles = AvatarProfiles(assets, Path(temp) / "selection.json")
            with self.assertRaises(FileNotFoundError):
                profiles.select("wizard")

    def test_reference_hash_separates_character_video_caches(self):
        with tempfile.TemporaryDirectory() as temp:
            profiles = AvatarProfiles(
                self._asset_root(temp), Path(temp) / "selection.json"
            )
            self.assertNotEqual(
                profiles.get("pilot").reference_hash(),
                profiles.get("robot").reference_hash(),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
