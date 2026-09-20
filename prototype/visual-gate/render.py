"""Render the visual-gate prototype to 1440x2560 stills.

    python render.py [name-fragment]
"""

import os
import sys
import time

from capture_lib import Session

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "shots")

# Chosen to catch each arrangement the timeline actually produces, not
# just the pretty ones: the quiet plate with nothing raised, one panel,
# two panels, the morph mid-flight, and the brain paired with weather.
SHOTS = [
    ("01-quiet.png", 1.5),
    ("02-heart-energy.png", 5.5),
    ("03-heart-pair.png", 10.0),
    ("04-transition.png", 13.8),
    ("05-brain-news.png", 20.0),
    ("06-brain-pair.png", 25.0),
    ("07-heart-weather.png", 31.0),
    ("08-heart-alone.png", 34.0),
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
