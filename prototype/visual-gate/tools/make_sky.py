"""Pre-render volumetric-looking cloud layers as transparent WebP.

The brief's performance philosophy: let the Pi compose excellent material
rather than generate it. These are built once here, with proper fBm
density and a directional light term, then the page only translates and
fades them. Alpha falls to zero well inside every edge, so the layers
dissolve into black with no rectangular boundary anywhere.

    python make_sky.py
"""

import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "assets", "sky"))
RNG = np.random.default_rng(4821)


def value_noise(w, h, cells):
    """One octave: random lattice, smoothly upsampled."""
    grid = RNG.random((cells + 1, cells + 1)).astype(np.float32)
    img = Image.fromarray((grid * 255).astype(np.uint8), mode="L")
    img = img.resize((w, h), Image.BICUBIC)
    return np.asarray(img, dtype=np.float32) / 255.0


def fbm(w, h, octaves=6, base=3, gain=0.5, lacunarity=2.0):
    total = np.zeros((h, w), dtype=np.float32)
    amp = 1.0
    norm = 0.0
    cells = base
    for _ in range(octaves):
        total += amp * value_noise(w, h, int(cells))
        norm += amp
        amp *= gain
        cells *= lacunarity
    return total / norm


def falloff(w, h, hardness_x=2.0, hardness_y=2.4):
    """Radial-ish vignette in alpha so the layer has no visible edge."""
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xs / (w - 1)) * 2 - 1
    ny = (ys / (h - 1)) * 2 - 1
    d = np.sqrt((nx * hardness_x * 0.5) ** 2 + (ny * hardness_y * 0.5) ** 2)
    return np.clip(1.0 - d, 0.0, 1.0) ** 1.5


def build(name, w, h, *, density=0.52, softness=0.30, octaves=6, base=3,
          light_dir=(-0.55, -0.8), tint=(196, 208, 226), lift=0.24):
    field = fbm(w, h, octaves=octaves, base=base)

    # Density shaping: everything below the threshold vanishes entirely,
    # which is what makes a cloud edge wispy rather than cut out.
    alpha = np.clip((field - density) / max(softness, 1e-4), 0.0, 1.0)
    alpha = alpha ** 1.35
    alpha *= falloff(w, h)

    # Directional shading from a displaced copy of the density: where the
    # cloud is thicker toward the light, it is brighter.
    dx = int(w * 0.018 * light_dir[0])
    dy = int(h * 0.030 * light_dir[1])
    shifted = np.roll(np.roll(field, dy, axis=0), dx, axis=1)
    lit = np.clip((field - shifted) * 3.4 + 0.5, 0.0, 1.0)
    shade = lift + (1.0 - lift) * lit

    rgb = np.zeros((h, w, 3), dtype=np.float32)
    for i, c in enumerate(tint):
        rgb[..., i] = c * shade

    out = np.dstack([
        np.clip(rgb, 0, 255).astype(np.uint8),
        np.clip(alpha * 255, 0, 255).astype(np.uint8),
    ])
    path = os.path.join(OUT, name)
    Image.fromarray(out, mode="RGBA").save(path, quality=86, method=6)
    print(f"  {name:16s} {w}x{h}  {os.path.getsize(path)//1024} KB")


def main():
    os.makedirs(OUT, exist_ok=True)
    # Three layers at different scales: a soft distant bank, the main
    # body the moon sits behind, and a small sharp foreground wisp.
    build("cloud-far.webp", 1500, 760, density=0.46, softness=0.40,
          octaves=5, base=2, tint=(150, 166, 196), lift=0.30)
    build("cloud-main.webp", 1400, 700, density=0.52, softness=0.26,
          octaves=7, base=3, tint=(206, 216, 234), lift=0.20)
    build("cloud-near.webp", 1100, 520, density=0.58, softness=0.20,
          octaves=7, base=4, tint=(228, 232, 240), lift=0.14)
    build("haze.webp", 1600, 600, density=0.30, softness=0.58,
          octaves=4, base=2, tint=(120, 138, 170), lift=0.45)


if __name__ == "__main__":
    main()
