"""Build the optimized images + icon set used by the v3 templates.

Run from the repo root:  python tools/build_v3_assets.py
Re-run after swapping a source photo. Outputs go to static/img/ and
templates/icons.json (inline SVG paths lifted from the local Lucide bundle, so
pages don't have to download the 400 KB library).
"""
import json
import os
import subprocess

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "static", "img")
GAL = os.path.join(ROOT, "static", "gallery")

# name -> (source, crop box as fractions (l, t, r, b) or None, widths)
IMAGES = {
    "hero": ("placeholder-22.jpg", None, (1200, 760)),
    "svc-ceramic": ("placeholder-35.jpg", None, (1200, 900, 600, 520)),
    "svc-full-detail": ("placeholder-20.jpg", None, (1200, 900, 600, 520)),
    "svc-wash": ("placeholder-28.jpg", None, (1200, 900, 600, 520)),
    "svc-interior": ("placeholder-14.jpg", None, (1200, 900, 600, 520)),
    "svc-correction": ("placeholder-22.jpg", (0.25, 0.15, 1.0, 0.85), (1200, 900, 600, 520)),
    "svc-headlight": ("../images/headlight-after.jpg", None, (1200, 900, 600, 520)),
    "headlight-before": ("../images/headlight-before.jpg", None, (700,)),
    "headlight-after": ("../images/headlight-after.jpg", None, (700,)),
}
# Gallery preview on the homepage (finished work + process shots).
WORK = (20, 35, 21, 45, 38, 14, 26, 22)


def save(im, name, width):
    im = im.copy()
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(os.path.join(OUT, f"{name}-{width}.webp"), "WEBP", quality=80 if name == "hero" else 88, method=6)


def logo():
    """Transparent logo from the on-black master: luminance becomes alpha."""
    src = Image.open(os.path.join(ROOT, "assets", "logo-on-black.png")).convert("RGB")
    bbox = src.convert("L").point(lambda v: 255 if v > 28 else 0).getbbox()
    src = src.crop(bbox)
    r, g, b = src.split()
    alpha = Image.eval(Image.merge("RGB", (r, g, b)).convert("L"), lambda v: min(255, int(v * 2.2)))
    im = src.copy()
    im.putalpha(alpha)
    im.thumbnail((420, 420), Image.LANCZOS)
    im.save(os.path.join(OUT, "logo-mark.png"), optimize=True)
    im.save(os.path.join(OUT, "logo-mark.webp"), "WEBP", quality=90)
    return im.size


def icons():
    names = [
        "phone", "arrow-right", "check", "star", "shield-check", "map-pin", "clock",
        "sparkles", "menu", "x", "chevron-down", "chevron-left", "droplets", "car",
        "car-front", "mail", "message-square", "calendar-check", "badge-check",
        "camera", "gem", "armchair", "sun", "plug", "info", "circle-alert",
        "send", "search", "hand-heart", "timer", "spray-can", "lightbulb",
    ]
    js = (
        "const L=require(process.argv[1]);const out={};"
        "for(const n of process.argv.slice(2)){"
        "const k=n.split('-').map(s=>s[0].toUpperCase()+s.slice(1)).join('');"
        "const node=L[k]||(L.icons&&L.icons[k]);if(!node){console.error('missing '+n);continue;}"
        "out[n]=node.map(([t,a])=>'<'+t+' '+Object.entries(a).map(([x,y])=>x+'=\"'+y+'\"').join(' ')+'/>').join('');}"
        "console.log(JSON.stringify(out));"
    )
    res = subprocess.run(
        ["node", "-e", js, os.path.join(ROOT, "assets", "lucide-1.23.0.min.js"), *names],
        capture_output=True, text=True, check=True,
    )
    if res.stderr:
        print(res.stderr)
    with open(os.path.join(ROOT, "templates", "icons.json"), "w") as fh:
        fh.write(res.stdout.strip() + "\n")


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, (src, box, widths) in IMAGES.items():
        im = Image.open(os.path.join(GAL, src)).convert("RGB")
        if box:
            w, h = im.size
            im = im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
        for wd in widths:
            save(im, name, wd)
    for n in WORK:
        im = Image.open(os.path.join(GAL, f"placeholder-{n}.jpg")).convert("RGB")
        save(im, f"work-{n}", 600)
    print("logo", logo())
    icons()


if __name__ == "__main__":
    main()
