"""Make spoken filler clips: short lines the character says straight after
the question, while the real reply is still being made.

A reply takes several seconds (text, then video). Played at once, a filler
turns that silence into part of the conversation. Fillers are made the same
way as replies (same video model, prompt, voice description and framing),
so they match, and they are made once and reused - never per turn.

They live with the theatre clips, in the house pack:
theatre/<character>/ack/. Each costs one video generation, so this only
runs with --run.

    python avatar_filler.py --character robot --line "One moment." --check
    python avatar_filler.py --character robot --line "One moment." --run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import avatar_theatre as theatre
from avatar_module import speaking_prompt
from avatar_profiles import AvatarProfiles
from avatar_services import FlashTalkService

PRICE_PER_SECOND_USD = 0.015          # minimax 480P promotional rate (Oct 2026)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--character", help="catalogue key (default: the current resident)")
    ap.add_argument("--line", action="append", required=True, help="what the character says (repeatable)")
    ap.add_argument("--run", action="store_true", help="generate (costs money)")
    ap.add_argument("--check", action="store_true", help="show the plan only (the default)")
    args = ap.parse_args()
    theatre.load_environment()
    model = os.getenv("AVATAR_FAL_MODEL", "minimax/h3-max-turbo/image-to-video")
    profiles = AvatarProfiles()
    profile = profiles.get(args.character) if args.character else profiles.current()
    folder = theatre.OUT / profile.key / "ack"
    prompt = speaking_prompt(profile)
    print(f"{profile.name}: {len(args.line)} filler clip(s), about ${len(args.line) * 5.2 * PRICE_PER_SECOND_USD:.2f} with {model}")
    print(f"  prompt: {prompt}")
    for line in args.line:
        print(f"  says:   {line}")
    if not args.run:
        print("\nnothing generated (use --run)")
        return 0
    folder.mkdir(parents=True, exist_ok=True)
    service = FlashTalkService()
    failures = 0
    for line in args.line:
        name = f"ack_{len(list(folder.glob('*.mp4'))) + 1:02d}_{int(time.time())}"
        destination = folder / f"{name}.mp4"
        try:
            result = service.generate_from_text(profile.reference_image, line, destination, model=model,
                                                prompt=prompt, duration_seconds=5, resolution="480P")
        except Exception as exc:
            failures += 1
            print(f"  FAILED {line!r}: {exc}")
            continue
        sidecar = {"character": profile.key, "kind": "ack", "model": model, "prompt": prompt, "line": line,
                   "seconds": result.duration_seconds, "reference": profile.reference_image.name,
                   "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
        destination.with_suffix(".json").write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
        print(f"  saved {destination}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
