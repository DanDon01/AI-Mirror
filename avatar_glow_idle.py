"""Make a still idle clip: the portrait held exactly, with glowing parts
(eyes, lamps) swelling up and back down. No model, no cost.

Generated idle clips kept moving the mouth while silent, which reads as
speech with the sound missing, whatever the prompt said. Here nothing in
the picture moves, so the mouth cannot. The clip starts and ends on the
flattened reference frame, like every theatre clip, so it hands over
seamlessly.

The glowing parts come from the character's entry in the house pack's
avatars/profiles.json, in reference-image pixels:

    "idle_glow": [
      {"x": 553, "y": 300, "rx": 30, "ry": 30, "color": [255, 150, 60]},
      ...
    ]

    python avatar_glow_idle.py --character robot            make one
    python avatar_glow_idle.py --character robot --seconds 6
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import avatar_theatre as theatre
from avatar_profiles import AvatarProfiles

FPS = 24


def glow_spots(profile_key: str) -> list[dict]:
    path = AvatarProfiles().asset_root / "profiles.json"
    for entry in json.loads(path.read_text(encoding="utf-8")):
        if str(entry.get("key", "")).casefold() == profile_key:
            return list(entry.get("idle_glow") or [])
    return []


def render(profile, spots: list[dict], seconds: float, destination: Path) -> None:
    import numpy as np
    from PIL import Image

    w, h = theatre.SIZE
    with tempfile.TemporaryDirectory() as tmp:
        flat = theatre.flatten(profile.reference_image, Path(tmp) / "reference.png")
        base = np.asarray(Image.open(flat).convert("RGB"), dtype=np.float32) / 255.0
    with Image.open(profile.reference_image) as ref:
        rw, rh = ref.size
    # Reference pixels -> flattened frame (scaled to fit, centred on black).
    scale = min(w / rw, h / rh)
    ox, oy = (w - rw * scale) / 2, (h - rh * scale) / 2

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    layers = []
    for spot in spots:
        cx, cy = ox + float(spot["x"]) * scale, oy + float(spot["y"]) * scale
        rx = max(1.0, float(spot.get("rx", spot.get("r", 20))) * scale)
        ry = max(1.0, float(spot.get("ry", spot.get("r", 20))) * scale)
        mask = np.exp(-(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2))[..., None]
        color = np.asarray(spot.get("color", [255, 255, 255]), dtype=np.float32)[None, None, :] / 255.0
        layers.append((mask, color, float(spot.get("strength", 1.0))))

    frames = int(round(seconds * FPS))
    command = [theatre.ffmpeg_bin(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264", "-profile:v", "high",
               "-pix_fmt", "yuv420p", "-crf", "16", "-movflags", "+faststart", str(destination)]
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for n in range(frames):
            # One slow swell, exactly zero on the first and last frame.
            level = math.sin(math.pi * n / (frames - 1)) ** 2 if frames > 1 else 0.0
            frame = base.copy()
            for mask, color, strength in layers:
                # Brighten what is already there, plus a soft halo of the colour.
                frame += level * strength * mask * (frame * 1.4 + color * 0.45)
            encoder.stdin.write((np.clip(frame, 0, 1) * 255).astype(np.uint8).tobytes())
    finally:
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise RuntimeError("ffmpeg failed to encode the idle clip")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--character", help="catalogue key (default: the current resident)")
    ap.add_argument("--seconds", type=float, default=theatre.CLIP_SECONDS + 0.08)
    args = ap.parse_args()
    profiles = AvatarProfiles()
    profile = profiles.get(args.character) if args.character else profiles.current()
    spots = glow_spots(profile.key)
    if not spots:
        raise SystemExit(f"{profile.name} has no idle_glow in avatars/profiles.json")
    folder = theatre.OUT / profile.key / "idle"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"idle_{len(theatre.existing(profile.key, 'idle')) + 1:02d}_{int(time.time())}"
    destination = folder / f"{name}.mp4"
    render(profile, spots, args.seconds, destination)
    sidecar = {"character": profile.key, "kind": "idle", "model": "local glow (avatar_glow_idle.py)",
               "idle_glow": spots, "seconds": args.seconds, "reference": profile.reference_image.name,
               "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    destination.with_suffix(".json").write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    print(f"saved {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
