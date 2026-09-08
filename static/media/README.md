# Media slots

Drop your photos and video here to make them appear on the site. **To update any
piece of media, replace the file with the same name and push** — no code changes.

Each file below starts out as an empty placeholder. A slot only shows up on the
site once its file has real content; empty slots are hidden automatically.

| File | Where it shows | Recommended |
|------|----------------|-------------|
| `hero-video.mp4` | Homepage hero background (desktop only). Lazy-loaded after the page loads; phones and reduced-motion visitors never download it. | MP4, H.264, no audio track, ~10–20s loop, keep under ~2 MB — run it through `tools/compress_hero_video.py` |
| `hero-fallback.jpg` | Homepage hero background, and the video's poster. This is what paints first, so keep one here even when the video is filled. | JPG, 1920×1080 |
| `rv-hero.jpg` | `/rv-detailing` hero background. | JPG, 1920×1080 |
| `boat-hero.jpg` | `/boat-detailing` hero background. | JPG, 1920×1080 |

> **Gallery photos moved.** The homepage "Our Work" strip and the `/gallery`
> page now use `static/gallery/placeholder-1.jpg` … `placeholder-6.jpg`. Those
> are always visible (they ship as branded "photo coming soon" tiles) — replace
> a file with a real photo of the same name and push. See `static/gallery/README.md`.

## How it works

The server checks which of these files exist and are non-empty, and stamps the
right markup straight into the page's HTML before sending it (`render_page` in
`app.py`). The hero image is therefore in the document the browser first parses
— it paints without waiting on any request. The result is cached per page and
re-rendered automatically when a file's size or the page's timestamp changes,
so replacing a file and pushing is still all it takes.

The video is deliberately kept off that path: it ships as `preload="none"` with
its URL in `data-src`, and a few lines of script promote it to a real `src`
after the page has loaded — and only on desktop, with motion allowed. Phones
and reduced-motion visitors never request it.

Keep the **exact same file names** — the site looks them up by name.
