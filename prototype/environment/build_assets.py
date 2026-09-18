"""Prepare the ENVIRONMENT prototype's image assets.

Sources are photographs from Wikimedia Commons (see assets/img/CREDITS.txt)
and CC0 cloud cutouts already in the project. Everything is graded and cut
to its exact final pixel size here, so the page never scales a large image
at runtime.
"""

import os
import shutil

from PIL import Image, ImageEnhance, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "assets", "img")
CLOUDS_SRC = os.path.abspath(os.path.join(HERE, "..", "..", "assets", "clouds"))
CLOUDS_DST = os.path.join(HERE, "assets", "clouds")


def grade(im, *, cool=0.0, warm=0.0, lift=0.0, contrast=1.0, saturation=1.0,
          darken=1.0):
    """Push a photograph toward the plate's palette."""
    im = im.convert("RGB")
    if saturation != 1.0:
        im = ImageEnhance.Color(im).enhance(saturation)
    if contrast != 1.0:
        im = ImageEnhance.Contrast(im).enhance(contrast)
    r, g, b = im.split()
    if cool:
        b = b.point(lambda v: min(255, int(v * (1 + cool))))
        r = r.point(lambda v: int(v * (1 - cool * 0.5)))
    if warm:
        r = r.point(lambda v: min(255, int(v * (1 + warm))))
        b = b.point(lambda v: int(v * (1 - warm * 0.4)))
    im = Image.merge("RGB", (r, g, b))
    if lift:
        im = im.point(lambda v: int(v + lift * (255 - v) * 0.35))
    if darken != 1.0:
        im = ImageEnhance.Brightness(im).enhance(darken)
    return im


def cover(im, w, h, anchor=0.5):
    """Crop to exactly w x h, keeping the most interesting band."""
    src_ratio = im.width / im.height
    dst_ratio = w / h
    if src_ratio > dst_ratio:
        new_w = int(im.height * dst_ratio)
        left = int((im.width - new_w) * 0.5)
        im = im.crop((left, 0, left + new_w, im.height))
    else:
        new_h = int(im.width / dst_ratio)
        top = int((im.height - new_h) * anchor)
        im = im.crop((0, top, im.width, top + new_h))
    return im.resize((w, h), Image.LANCZOS)


def save(im, name, quality=88):
    path = os.path.join(IMG, name)
    im.save(path, quality=quality, method=6)
    print(f"  {name:26s} {im.size[0]}x{im.size[1]}  {os.path.getsize(path)//1024} KB")


def main():
    print("hero")
    # Native 1:1 crop of the sky band only. Letting cover() pick the window
    # dragged the muddy water reflection into frame, which read as noise
    # behind the temperature rather than atmosphere.
    hero = Image.open(os.path.join(IMG, "sky_dusk_1.jpg")).convert("RGB")
    hero = hero.crop((240, 70, 1680, 1310))
    hero = grade(hero, cool=0.06, contrast=1.10, saturation=0.96, darken=0.88)
    save(hero, "hero-dusk.webp")

    print("outlook thumbnails")
    plan = [
        ("sky_dusk_1.jpg", "day-0.webp", dict(warm=0.10, contrast=1.06, saturation=0.95, darken=0.92)),
        ("sky_cumulus_0.jpg", "day-1.webp", dict(cool=0.12, contrast=1.10, saturation=0.80, darken=0.88)),
        ("tex_rain_1.jpg", "day-2.webp", dict(cool=0.16, contrast=1.04, saturation=0.55, darken=0.74)),
        ("cand_c.jpg", "day-3.webp", dict(cool=0.14, contrast=1.05, saturation=0.78, darken=0.80)),
    ]
    for src, out, g in plan:
        im = Image.open(os.path.join(IMG, src))
        im = cover(im, 300, 380, anchor=0.32)
        save(grade(im, **g), out)

    print("grain tile")
    import random
    random.seed(7)
    n = 220
    noise = Image.new("L", (n, n))
    noise.putdata([random.randint(96, 160) for _ in range(n * n)])
    noise = noise.filter(ImageFilter.GaussianBlur(0.35))
    tile = Image.new("RGBA", (n, n))
    tile.putdata([(v, v, v, 255) for v in noise.getdata()])
    tile.save(os.path.join(IMG, "grain.webp"), quality=70, method=6)
    print(f"  grain.webp                 {n}x{n}  "
          f"{os.path.getsize(os.path.join(IMG,'grain.webp'))//1024} KB")

    print("cloud cutouts (CC0, Kenney)")
    os.makedirs(CLOUDS_DST, exist_ok=True)
    picks = sorted(f for f in os.listdir(CLOUDS_SRC) if f.endswith(".png"))[:4]
    for i, name in enumerate(picks):
        im = Image.open(os.path.join(CLOUDS_SRC, name)).convert("RGBA")
        im = im.resize((980, int(980 * im.height / im.width)), Image.LANCZOS)
        px = im.load()
        for y in range(im.height):
            for x in range(im.width):
                r, g, b, a = px[x, y]
                px[x, y] = (214, 224, 238, int(a * 0.72))
        out = os.path.join(CLOUDS_DST, f"puff-{i}.webp")
        im.save(out, quality=82, method=6)
        print(f"  puff-{i}.webp               {im.size[0]}x{im.size[1]}  "
              f"{os.path.getsize(out)//1024} KB")
    shutil.copy(os.path.join(CLOUDS_SRC, "LICENSE.txt"),
                os.path.join(CLOUDS_DST, "LICENSE.txt"))


if __name__ == "__main__":
    main()
