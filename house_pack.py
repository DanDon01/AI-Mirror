"""Where this mirror's own house lives.

Everything specific to one home - its avatars and their clips, the 3D house
model, the city and watchlist, private notes - sits in a "house pack": one
directory outside version control of this repo. By default it is ``house/``
next to this file; MIRROR_HOUSE_DIR points anywhere else.

The pack is optional. Without it the mirror runs with neutral defaults, the
example house, and no avatar. ``house.example/`` shows the layout:

    house/
      config_local.py          CONFIG overrides (city, coordinates, watchlist)
      avatars/profiles.json    the characters: key, name, description, image
      avatars/<image>.png      reference portraits
      avatars/prompts/<key>.txt  persona prompts
      avatars/apparitions/<key>/ optional arrival clips
      theatre/<key>/<kind>/    appear / think / idle clips (avatar_theatre.py)
      visual-gate/             files the browser front end may load from /house/
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def house_dir() -> Path:
    """The house pack directory (it may not exist)."""
    configured = os.getenv("MIRROR_HOUSE_DIR", "").strip()
    return Path(configured).expanduser().resolve() if configured else ROOT / "house"


def house_path(*parts: str) -> Path:
    return house_dir().joinpath(*parts)


def has_house() -> bool:
    return house_dir().is_dir()
