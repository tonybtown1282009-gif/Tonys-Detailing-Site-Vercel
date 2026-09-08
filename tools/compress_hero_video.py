"""
Compress a hero background video to something a homepage can afford.

The hero video autoplays behind the headline on every desktop visit, so its
file size is a page-load cost paid by every visitor. Phone footage comes off
the camera at 15-20 Mbps with an audio track the site never plays; this
re-encodes it to a muted, web-tuned MP4 (usually a 10-20x reduction with no
visible difference at hero size) and writes a poster frame to go with it.

    pip install imageio-ffmpeg
    python tools/compress_hero_video.py path/to/new-footage.mp4

By default it writes static/media/hero-video.mp4 and, unless --keep-poster is
passed, refreshes static/media/hero-fallback.jpg from a frame of the clip.
Pass --crf to trade size against quality (lower is better quality; 23 is
visually lossless, 27 is the default here, 30 is noticeably soft).
"""

import argparse
import os
import shutil
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA_DIR = os.path.join(BASE_DIR, "static", "media")
VIDEO_OUT = os.path.join(MEDIA_DIR, "hero-video.mp4")
POSTER_OUT = os.path.join(MEDIA_DIR, "hero-fallback.jpg")

# Above this the video stops being a background flourish and starts being the
# reason the page is slow. Matches the guidance in static/media/README.md.
SIZE_BUDGET_MB = 2.0


def ffmpeg_exe():
    """Prefer a system ffmpeg; fall back to the pip-installable static build."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
    except ImportError:
        sys.exit(
            "No ffmpeg found. Install one:\n"
            "  pip install imageio-ffmpeg   (or use your system package manager)"
        )
    return imageio_ffmpeg.get_ffmpeg_exe()


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"ffmpeg failed:\n{result.stderr[-2000:]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", help="the video to compress")
    ap.add_argument("--crf", type=int, default=27,
                    help="quality; lower is better and bigger (default 27)")
    ap.add_argument("--poster-at", type=float, default=None,
                    help="seconds into the clip to grab the poster from "
                         "(default: the midpoint)")
    ap.add_argument("--keep-poster", action="store_true",
                    help="leave hero-fallback.jpg alone")
    args = ap.parse_args()

    if not os.path.isfile(args.source):
        sys.exit(f"no such file: {args.source}")
    ff = ffmpeg_exe()

    run([
        ff, "-hide_banner", "-loglevel", "error", "-i", args.source,
        # The site never unmutes it, so the audio track is pure download cost.
        "-an",
        "-c:v", "libx264", "-preset", "slow", "-crf", str(args.crf),
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
        # Keyframe every 2s, and put the moov atom up front so playback can
        # start before the whole file has arrived.
        "-g", "60", "-movflags", "+faststart",
        "-y", VIDEO_OUT,
    ])

    if not args.keep_poster:
        at = args.poster_at
        if at is None:
            probe = subprocess.run(
                [ff, "-hide_banner", "-i", VIDEO_OUT],
                capture_output=True, text=True,
            ).stderr
            at = 1.0
            for line in probe.splitlines():
                if "Duration:" in line:
                    clock = line.split("Duration:")[1].split(",")[0].strip()
                    h, m, s = clock.split(":")
                    at = (int(h) * 3600 + int(m) * 60 + float(s)) / 2
                    break
        run([
            ff, "-hide_banner", "-loglevel", "error", "-ss", str(at),
            "-i", VIDEO_OUT, "-frames:v", "1", "-q:v", "4", "-y", POSTER_OUT,
        ])

    size_mb = os.path.getsize(VIDEO_OUT) / (1024 * 1024)
    source_mb = os.path.getsize(args.source) / (1024 * 1024)
    print(f"{args.source}  {source_mb:.1f} MB")
    print(f"{os.path.relpath(VIDEO_OUT, BASE_DIR)}  {size_mb:.1f} MB "
          f"({100 - size_mb / source_mb * 100:.0f}% smaller)")
    if not args.keep_poster:
        poster_kb = os.path.getsize(POSTER_OUT) / 1024
        print(f"{os.path.relpath(POSTER_OUT, BASE_DIR)}  {poster_kb:.0f} KB")
    if size_mb > SIZE_BUDGET_MB:
        print(f"\nWarning: over the {SIZE_BUDGET_MB} MB budget. Re-run with a "
              f"higher --crf (try {args.crf + 3}), or trim the clip shorter.")


if __name__ == "__main__":
    main()
