"""
Build web-optimized WOFF2 fonts from the TTFs in fonts/.

Each fonts/<Name>.ttf is subset to the Latin character set the site uses
(plus Latin-Extended for names/places typed into the booking form) and
written as fonts/<Name>.woff2. The pages load the .woff2 first and fall
back to the full .ttf, so re-run this whenever a TTF changes:

    pip install fonttools brotli
    python tools/build_fonts.py
"""

import glob
import os
import sys

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")

# Latin + Latin-Extended + general punctuation (– — ’ …), currency, arrows.
UNICODES = (
    "U+0000-024F,U+02B0-02FF,U+0300-036F,U+1E00-1EFF,"
    "U+2000-206F,U+20AC,U+2122,U+2190-2199,U+2212,U+2215,U+FEFF,U+FFFD"
)


def build(ttf_path):
    woff2_path = ttf_path[:-4] + ".woff2"
    font = TTFont(ttf_path)

    options = Options()
    options.flavor = "woff2"
    options.layout_features = ["*"]  # keep kerning/ligatures
    options.name_IDs = ["*"]
    options.notdef_outline = True

    subsetter = Subsetter(options=options)
    subsetter.populate(unicodes=parse_unicodes(UNICODES))
    subsetter.subset(font)
    font.flavor = "woff2"
    font.save(woff2_path)

    before, after = os.path.getsize(ttf_path), os.path.getsize(woff2_path)
    print(f"{os.path.basename(ttf_path):28s} {before / 1024:7.1f} KB -> {after / 1024:6.1f} KB")


def parse_unicodes(spec):
    codes = []
    for part in spec.split(","):
        part = part.strip().removeprefix("U+")
        if "-" in part:
            start, end = part.split("-")
            codes.extend(range(int(start, 16), int(end, 16) + 1))
        else:
            codes.append(int(part, 16))
    return codes


if __name__ == "__main__":
    ttfs = sorted(glob.glob(os.path.join(FONTS_DIR, "*.ttf")))
    if not ttfs:
        sys.exit("No TTFs found in fonts/")
    for path in ttfs:
        build(path)
