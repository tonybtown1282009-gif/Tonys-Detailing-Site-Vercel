"""
Build the WebP images the pages actually load.

The originals (JPG/PNG) stay in place as the editable sources; this writes a
sibling .webp next to each one. Re-run after swapping a photo:

    pip install pillow
    python tools/optimize_images.py
"""

import glob
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (glob, max width, quality). Gallery/headlight photos render at <=400 CSS px,
# so 800px covers 2x screens. The hero fills the viewport, so it keeps its size.
JOBS = (
    ("static/gallery/placeholder-*.jpg", 800, 80),
    ("static/images/headlight-*.jpg", 800, 80),
    ("static/media/hero-fallback.jpg", 1080, 72),
    ("static/media/rv-hero.jpg", 1080, 72),
    ("static/media/boat-hero.jpg", 1080, 72),
    # The logo is shown at 32-42 CSS px; 192px covers 4x+ screens.
    ("assets/logo.png", 192, 90),
)


def build(path, max_width, quality):
    try:
        im = Image.open(path)
        im.load()
    except Exception:
        return None  # empty placeholder slot, etc.
    if im.width > max_width:
        im = im.resize((max_width, round(im.height * max_width / im.width)), Image.LANCZOS)
    im = im.convert("RGBA" if "transparency" in im.info or im.mode in ("RGBA", "LA") else "RGB")
    out = os.path.splitext(path)[0] + ".webp"
    im.save(out, "WEBP", quality=quality, method=6)
    return out, im.size


if __name__ == "__main__":
    for pattern, width, quality in JOBS:
        for path in sorted(glob.glob(os.path.join(ROOT, pattern))):
            res = build(path, width, quality)
            if res:
                print(f"{os.path.relpath(path, ROOT)} -> {os.path.getsize(res[0]) // 1024} KiB {res[1]}")
