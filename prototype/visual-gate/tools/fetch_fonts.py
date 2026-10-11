"""Bundle the prototype's typefaces locally.

The mirror cannot depend on the network to render text. Pulling the faces
from Google at load time also means a Pi with a fontconfig problem or no
route silently falls back to a system serif, and the typography you are
judging is not the typography that was designed.

Both families are SIL Open Font Licence 1.1.

    python tools/fetch_fonts.py
"""

import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "assets", "fonts"))

# A modern-browser UA is what makes Google serve woff2 rather than ttf.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

FAMILIES = [
    ("Instrument+Serif", "ital@0;1"),
    ("Instrument+Sans", "wght@400..700"),
]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main():
    os.makedirs(OUT, exist_ok=True)
    css_parts = []

    for family, axis in FAMILIES:
        url = f"https://fonts.googleapis.com/css2?family={family}:{axis}&display=swap"
        css = get(url).decode("utf-8")

        # Keep only the latin blocks; the mirror shows no other script and
        # the extra subsets are dead weight on the Pi.
        blocks = re.findall(r"/\*\s*([\w\-\[\]]+)\s*\*/\s*(@font-face\s*\{[^}]*\})", css)
        wanted = [(name, block) for name, block in blocks if name == "latin"]
        if not wanted:
            wanted = [("latin", b) for b in re.findall(r"@font-face\s*\{[^}]*\}", css)][:1]

        for name, block in wanted:
            src = re.search(r"url\((https://[^)]+\.woff2)\)", block)
            if not src:
                continue
            remote = src.group(1)
            fname = (family.replace("+", "-").lower() + "-" +
                     re.sub(r"[^a-z0-9]+", "-",
                            re.search(r"font-style:\s*(\w+)", block).group(1)) + "-" +
                     (re.search(r"font-weight:\s*([\d ]+)", block).group(1)
                      .strip().replace(" ", "-")) + ".woff2")
            data = get(remote)
            with open(os.path.join(OUT, fname), "wb") as fh:
                fh.write(data)
            print(f"  {fname:44s} {len(data)//1024:4d} KB")
            # Relative to this stylesheet, which lives beside the files.
            css_parts.append(block.replace(remote, fname))

    header = ("/* Bundled locally so the mirror never depends on the network,\n"
              "   and so a fontconfig failure cannot silently substitute a\n"
              "   system face for the one that was designed.\n"
              "   Instrument Serif and Instrument Sans, SIL OFL 1.1. */\n\n")
    with open(os.path.join(OUT, "fonts.css"), "w", encoding="utf-8") as fh:
        fh.write(header + "\n\n".join(css_parts) + "\n")
    print(f"wrote {os.path.join(OUT, 'fonts.css')}")


if __name__ == "__main__":
    main()
