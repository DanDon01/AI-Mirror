"""Character profiles and persistent selection for the talking-avatar pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import threading


from house_pack import house_path

ROOT = Path(__file__).resolve().parent
# The characters belong to the house, not to the code: see house_pack.py.
DEFAULT_ASSET_ROOT = house_path("avatars")
DEFAULT_STATE_PATH = ROOT / "data" / "avatar" / "selection.json"


class NoAvatarsConfigured(RuntimeError):
    """The house pack defines no characters, so there is no avatar."""


@dataclass(frozen=True)
class AvatarProfile:
    key: str
    name: str
    description: str
    reference_image: Path
    prompt_file: Path
    apparition_dir: Path

    def reference_hash(self) -> str:
        """Hash the selected portrait so cached videos never cross characters."""
        digest = hashlib.sha256()
        with self.reference_image.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def as_dict(self, *, selected: bool = False) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "selected": selected,
            "reference_available": self.reference_image.is_file(),
        }


def load_specs(asset_root: str | Path) -> tuple:
    """The character list from <asset_root>/profiles.json:

        [{"key": "robot", "name": "Robot", "description": "Creaky and kind",
          "image": "Robot.png"}, ...]

    Missing or unreadable means no characters (the avatar stays off)."""
    path = Path(asset_root) / "profiles.json"
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    specs = []
    for entry in entries if isinstance(entries, list) else []:
        try:
            key = str(entry["key"]).strip().casefold()
            specs.append((key, str(entry.get("name") or key), str(entry.get("description") or ""),
                          str(entry["image"])))
        except (KeyError, TypeError, AttributeError):
            continue
    return tuple(s for s in specs if s[0])


class AvatarProfiles:
    """Owns the fixed character catalogue and the operator's active choice."""

    def __init__(
        self,
        asset_root: str | Path = DEFAULT_ASSET_ROOT,
        state_path: str | Path = DEFAULT_STATE_PATH,
        default: str | None = None,
    ):
        self.asset_root = Path(asset_root).resolve()
        self.state_path = Path(state_path).resolve()
        self._lock = threading.RLock()
        self._profiles = {
            key: AvatarProfile(
                key=key,
                name=name,
                description=description,
                reference_image=self.asset_root / filename,
                prompt_file=self.asset_root / "prompts" / f"{key}.txt",
                apparition_dir=self.asset_root / "apparitions" / key,
            )
            for key, name, description, filename in load_specs(self.asset_root)
        }
        requested = (default or os.getenv("AVATAR_CHARACTER", "")).strip().casefold()
        self._selected = requested if requested in self._profiles else self._load_selection()
        if self._selected not in self._profiles:
            self._selected = next(iter(self._profiles), "")

    def _load_selection(self) -> str:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            return str(payload.get("selected", "")).strip().casefold()
        except (OSError, ValueError, TypeError):
            return ""

    def current(self) -> AvatarProfile:
        with self._lock:
            if not self._profiles:
                raise NoAvatarsConfigured(
                    f"No avatars configured: add {self.asset_root / 'profiles.json'} (see house.example/)")
            return self._profiles[self._selected]

    def get(self, key: str) -> AvatarProfile:
        normalized = str(key or "").strip().casefold()
        try:
            return self._profiles[normalized]
        except KeyError as exc:
            raise ValueError(f"Unknown avatar: {key}") from exc

    def select(self, key: str) -> AvatarProfile:
        profile = self.get(key)
        if not profile.reference_image.is_file():
            raise FileNotFoundError(f"Avatar reference image is missing: {profile.reference_image}")
        with self._lock:
            self._selected = profile.key
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            partial = self.state_path.with_suffix(".json.partial")
            partial.write_text(
                json.dumps({"selected": profile.key}, indent=2) + "\n",
                encoding="utf-8",
            )
            partial.replace(self.state_path)
        return profile

    def options(self) -> list[dict]:
        with self._lock:
            selected = self._selected
            return [
                profile.as_dict(selected=profile.key == selected)
                for profile in self._profiles.values()
            ]

