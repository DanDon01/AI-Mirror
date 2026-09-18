"""Generate matched point clouds for the biometric object.

The heart and the brain are each defined as a signed distance field built
from smooth-unioned primitives, then sampled by projecting random points
onto the zero isosurface. Both clouds get the same point count so the
renderer can morph particle i from heart[i] to brain[i] directly.

Point clouds rather than meshes because the transition the brief asks for
IS particles, and because a cloud is forgiving about topology in a way a
sculpted mesh is not.

    python make_anatomy.py
"""

import os
import struct

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "assets", "anatomy"))
COUNT = 48000
RNG = np.random.default_rng(20260918)


# ----------------------------------------------------------------------
# SDF primitives (vectorised over an (N,3) array of points)
# ----------------------------------------------------------------------

def sd_ellipsoid(p, centre, radii):
    q = (p - centre) / radii
    k0 = np.linalg.norm(q, axis=1)
    k1 = np.linalg.norm(q / radii, axis=1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)


def sd_capsule(p, a, b, r):
    pa = p - a
    ba = b - a
    h = np.clip((pa @ ba) / (ba @ ba), 0.0, 1.0)[:, None]
    return np.linalg.norm(pa - ba * h, axis=1) - r


def smin(a, b, k):
    """Polynomial smooth minimum — the organic blend between parts."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def gyroid(p, freq):
    x, y, z = (p * freq).T
    return (np.sin(x) * np.cos(y) + np.sin(y) * np.cos(z) + np.sin(z) * np.cos(x))


def sd_chain(p, nodes, k=0.09, subdiv=4):
    """A tapering tube through a list of ((x,y,z), radius) nodes.

    Each span is subdivided into short constant-radius capsules that
    smooth-union together, which gives a clean taper without needing an
    exact round-cone distance function.
    """
    d = None
    for i in range(len(nodes) - 1):
        (a, ra), (b, rb) = nodes[i], nodes[i + 1]
        a = np.asarray(a, dtype=float)
        b = np.asarray(b, dtype=float)
        for s in range(subdiv):
            t0 = s / subdiv
            t1 = (s + 1) / subdiv
            seg = sd_capsule(p, a + (b - a) * t0, a + (b - a) * t1,
                             ra + (rb - ra) * (t0 + t1) * 0.5)
            d = seg if d is None else smin(d, seg, k)
    return d


# ----------------------------------------------------------------------
# The two forms
# ----------------------------------------------------------------------

def sdf_heart(p):
    # Left ventricle: a tapering cone of muscle running down to the apex,
    # which is what actually makes a heart read as a heart. Blended
    # spheres alone give a lumpy bag.
    lv = sd_chain(p, [
        ((0.03, 0.30, -0.03), 0.285),
        ((0.01, 0.14, 0.00), 0.295),
        ((-0.02, -0.03, 0.02), 0.255),
        ((-0.06, -0.19, 0.04), 0.195),
        ((-0.10, -0.33, 0.055), 0.125),
        ((-0.15, -0.50, 0.070), 0.030),
    ], k=0.045)

    # Right ventricle: shorter, sits anterior and to the side.
    rv = sd_chain(p, [
        ((0.26, 0.24, 0.105), 0.205),
        ((0.245, 0.08, 0.125), 0.195),
        ((0.185, -0.09, 0.115), 0.150),
        ((0.085, -0.27, 0.085), 0.060),
    ], k=0.045)
    d = smin(lv, rv, 0.055)

    # Atria across the top.
    la = sd_ellipsoid(p, np.array([-0.165, 0.395, -0.10]), np.array([0.168, 0.145, 0.168]))
    d = smin(d, la, 0.050)
    ra = sd_ellipsoid(p, np.array([0.245, 0.395, 0.025]), np.array([0.165, 0.145, 0.165]))
    d = smin(d, ra, 0.050)

    # Aorta arching up and back, pulmonary trunk rising forward and across.
    aorta = sd_chain(p, [
        ((0.03, 0.36, -0.02), 0.090),
        ((0.05, 0.60, -0.05), 0.080),
        ((0.01, 0.74, -0.11), 0.070),
        ((-0.11, 0.77, -0.18), 0.062),
        ((-0.14, 0.60, -0.23), 0.054),
    ], k=0.022)
    d = smin(d, aorta, 0.030)

    trunk = sd_chain(p, [
        ((0.17, 0.38, 0.10), 0.082),
        ((0.13, 0.62, 0.155), 0.072),
        ((0.01, 0.73, 0.115), 0.058),
    ], k=0.022)
    d = smin(d, trunk, 0.030)

    # Coronary groove plus fine surface irregularity.
    d += 0.006 * np.sin(p[:, 1] * 20.0 + p[:, 0] * 8.0)
    d -= 0.004 * np.abs(gyroid(p, 15.0))
    return d


def sdf_brain(p):
    # Two hemispheres, unioned just tightly enough to leave the
    # longitudinal fissure visible between them.
    lh = sd_ellipsoid(p, np.array([-0.165, 0.055, 0.0]), np.array([0.285, 0.295, 0.375]))
    rh = sd_ellipsoid(p, np.array([0.165, 0.055, 0.0]), np.array([0.285, 0.295, 0.375]))
    d = smin(lh, rh, 0.075)

    # Cerebellum tucked under the back.
    cb = sd_ellipsoid(p, np.array([0.0, -0.215, -0.245]), np.array([0.255, 0.155, 0.165]))
    d = smin(d, cb, 0.09)

    # Brainstem.
    st = sd_capsule(p, np.array([0.0, -0.16, -0.10]), np.array([0.0, -0.45, -0.045]), 0.072)
    d = smin(d, st, 0.08)

    # Gyri. A gyroid field folded onto the surface reads convincingly as
    # cortical convolution and costs one evaluation.
    d -= 0.030 * np.abs(gyroid(p, 9.5))
    return d


# ----------------------------------------------------------------------
# Surface sampling
# ----------------------------------------------------------------------

def gradient(fn, p, eps=2e-3):
    g = np.empty_like(p)
    for axis in range(3):
        step = np.zeros(3)
        step[axis] = eps
        g[:, axis] = fn(p + step) - fn(p - step)
    return g / (2 * eps)


def sample_surface(fn, count, extent=0.95, tol=3.5e-3, steps=26):
    """Project random points onto the zero isosurface."""
    kept = []
    while sum(len(k) for k in kept) < count:
        p = RNG.uniform(-extent, extent, size=(count, 3))
        for _ in range(steps):
            d = fn(p)
            g = gradient(fn, p)
            n = np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-6)
            p = p - (d[:, None] / n) * (g / n)
        good = np.abs(fn(p)) < tol
        inside = np.all(np.abs(p) < extent + 0.08, axis=1)
        kept.append(p[good & inside])
    return np.concatenate(kept)[:count]


def normalise(points, target_height=1.0):
    points = points - points.mean(axis=0)
    height = points[:, 1].max() - points[:, 1].min()
    return points * (target_height / height)


def order_for_morph(points):
    """Sort by spherical angle so heart point i and brain point i are
    roughly in the same place on the form. Without this the morph looks
    like static rather than a body reorganising itself."""
    v = points - points.mean(axis=0)
    theta = np.arctan2(v[:, 0], v[:, 2])
    phi = np.arctan2(v[:, 1], np.linalg.norm(v[:, [0, 2]], axis=1))
    key = np.round(phi * 24).astype(int) * 10000 + np.round(theta * 24).astype(int)
    return points[np.argsort(key, kind="stable")]


def write_bin(path, points, extra):
    with open(path, "wb") as fh:
        fh.write(struct.pack("<I", len(points)))
        payload = np.concatenate([points, extra[:, None]], axis=1).astype("<f4")
        fh.write(payload.tobytes())
    print(f"  {os.path.basename(path):12s} {len(points):6d} pts  "
          f"{os.path.getsize(path)//1024} KB")


def preview(name, points, size=460):
    """Flat orthographic dot render, purely to check the silhouette."""
    from PIL import Image
    img = Image.new("L", (size * 2, size), 0)
    px = img.load()
    for (ax, ay, off) in ((0, 1, 0), (2, 1, size)):
        a = points[:, ax]
        b = points[:, ay]
        sx = ((a - a.min()) / (a.max() - a.min()) * (size - 40) + 20 + off).astype(int)
        sy = ((1 - (b - b.min()) / (b.max() - b.min())) * (size - 40) + 20).astype(int)
        depth = points[:, 2] if ax == 0 else points[:, 0]
        shade = ((depth - depth.min()) / np.ptp(depth) * 34 + 8).astype(int)
        for x, y, v in zip(sx, sy, shade):
            if 0 <= x < size * 2 and 0 <= y < size:
                px[x, y] = min(255, px[x, y] + int(v))
    img.save(os.path.join(OUT, f"_preview_{name}.png"))


def main():
    os.makedirs(OUT, exist_ok=True)
    print("sampling heart")
    heart = order_for_morph(normalise(sample_surface(sdf_heart, COUNT)))
    print("sampling brain")
    brain = order_for_morph(normalise(sample_surface(sdf_brain, COUNT)))

    # Per-point scalar the shader uses for colour and region lighting:
    # height up the form, 0 at the base, 1 at the top.
    h_extra = (heart[:, 1] - heart[:, 1].min()) / np.ptp(heart[:, 1])
    b_extra = (brain[:, 1] - brain[:, 1].min()) / np.ptp(brain[:, 1])

    write_bin(os.path.join(OUT, "heart.bin"), heart, h_extra)
    write_bin(os.path.join(OUT, "brain.bin"), brain, b_extra)
    preview("heart", heart)
    preview("brain", brain)
    print(f"previews in {OUT}")


if __name__ == "__main__":
    main()
