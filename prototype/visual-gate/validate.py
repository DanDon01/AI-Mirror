"""Validate the prototype across its whole timeline.

Stills only prove the handful of moments they were taken at. This walks
the full 48-second loop, checking that no frame throws, that something
is actually being drawn at every point, and reporting the draw-call and
primitive budget.

Those counts are the one performance figure that means anything from a
machine without a GPU path for WebGL: they say what the Pi is being
asked to do, whatever speed it does it at.

    python validate.py
"""

import struct
import sys

import numpy as np

from capture_lib import Session

STEP = 0.5
LOOP = 48.0


def check_assets():
    """Geometry sanity: counts line up, nothing is NaN, tracts sit
    inside the shell they are supposed to run through."""
    print("== geometry ==")
    ok = True

    def read_points(path):
        with open(path, "rb") as fh:
            count = struct.unpack("<I", fh.read(4))[0]
            data = np.frombuffer(fh.read(), dtype="<f4").reshape(count, 8)
        return data

    heart = read_points("assets/anatomy/heart.pts")
    brain = read_points("assets/anatomy/brain.pts")
    for name, arr in (("heart.pts", heart), ("brain.pts", brain)):
        bad = int(np.isnan(arr).sum() + np.isinf(arr).sum())
        span = arr[:, :3].max(axis=0) - arr[:, :3].min(axis=0)
        print(f"  {name:11s} {len(arr):6d} pts  non-finite {bad}  "
              f"extent {span[0]:.2f} x {span[1]:.2f} x {span[2]:.2f}")
        ok &= bad == 0

    if len(heart) != len(brain):
        print("  FAIL point counts differ, the morph pairs by index")
        ok = False

    with open("assets/anatomy/brain.fib", "rb") as fh:
        count, samples = struct.unpack("<II", fh.read(8))
        fib = np.frombuffer(fh.read(), dtype="<f4").reshape(count, samples, 5)
    bad = int(np.isnan(fib).sum() + np.isinf(fib).sum())

    # Every tract vertex should sit inside the brain's own bounding box.
    lo = brain[:, :3].min(axis=0)
    hi = brain[:, :3].max(axis=0)
    pts = fib[:, :, :3].reshape(-1, 3)
    outside = int(((pts < lo - 0.02) | (pts > hi + 0.02)).any(axis=1).sum())
    print(f"  brain.fib   {count:6d} x {samples}  non-finite {bad}  "
          f"vertices outside the shell {outside}/{len(pts)}")
    ok &= bad == 0 and outside == 0
    return ok


def main():
    if not check_assets():
        print("\nGEOMETRY CHECK FAILED")
        return 1

    print("\n== timeline sweep ==")
    worst = {}
    sampled = {}
    failures = []
    with Session(debug_port=9380, profile=".chrome-validate") as s:
        t = 0.0
        while t < LOOP:
            s.eval(f"window.__setTime({t:.3f})")
            err = s.eval("document.body.dataset.error || ''")
            info = s.eval("JSON.stringify(window.__gpuInfo() || {})")
            if err:
                failures.append((t, err))
            stats = {}
            try:
                import json
                stats = json.loads(info or "{}")
            except Exception:
                failures.append((t, f"unreadable stats: {info!r}"))
            if not stats or stats.get("calls", 0) < 1:
                failures.append((t, f"nothing drawn: {stats}"))
            for k, v in stats.items():
                worst[k] = max(worst.get(k, 0), v)
            sampled[round(t, 1)] = stats
            t += STEP

    print(f"  swept {int(LOOP / STEP)} points at {STEP}s intervals")
    print(f"  errors: {len(failures)}")
    for t, err in failures[:6]:
        print(f"    t={t:5.1f}  {err[:110]}")

    print("\n== draw budget by phase ==")
    print(f"  {'phase':11s} {'calls':>6s} {'triangles':>11s} "
          f"{'points':>9s} {'lines':>8s}")
    for label, at in (("heart", 4.0), ("dissolve", 13.5),
                      ("brain", 20.0), ("reforming", 28.0)):
        st = sampled.get(at, {})
        print(f"  {label:11s} {st.get('calls', 0):6d} "
              f"{st.get('triangles', 0):11,d} {st.get('points', 0):9,d} "
              f"{st.get('lines', 0):8,d}")
    print(f"\n  peak over the loop: {worst.get('calls', 0)} calls, "
          f"{worst.get('triangles', 0):,} tris, "
          f"{worst.get('points', 0):,} points, "
          f"{worst.get('lines', 0):,} lines")

    print("\nVALIDATION " + ("PASSED" if not failures else "FAILED"))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
