"""Render the visual-gate prototype to 1440x2560 stills.

    python render.py [name-fragment]
"""

import os
import sys
import time

from capture_lib import Session

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "shots")

SHOTS = [
    ("01-heart.png", 4.0),
    ("02-event.png", 8.6),
    ("03-transition.png", 13.7),
    ("04-brain.png", 20.0),
    ("05-rain.png", 36.0),
]


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    os.makedirs(OUT, exist_ok=True)
    with Session(debug_port=9360, profile=".chrome-still") as s:
        for name, t in SHOTS:
            if only and only not in name:
                continue
            s.seek(t)
            # Step once more after a beat so the compositor has certainly
            # picked up the new canvas contents before the grab.
            time.sleep(0.6)
            s.seek(t)
            out = os.path.join(OUT, name)
            s.shot(out)
            print(f"  {name:20s} t={t:5.1f}s  {os.path.getsize(out)//1024:5d} KB")


if __name__ == "__main__":
    main()
