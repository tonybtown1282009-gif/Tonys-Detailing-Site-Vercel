# Media slots

Drop your photos and video here to make them appear on the site. **To update any
piece of media, replace the file with the same name and push** — no code changes.

Each file below starts out as an empty placeholder. A slot only shows up on the
site once its file has real content; empty slots are hidden automatically.

| File | Where it shows | Recommended |
|------|----------------|-------------|
| `hero-video.mp4` | Homepage hero background (desktop only). Falls back to `hero-fallback.jpg` if missing, and always uses the image on phones. | MP4, H.264, muted, ~10–20s loop, 1920×1080, keep under ~8 MB |
| `hero-fallback.jpg` | Homepage hero background when there's no video (and the video's poster while it loads). | JPG, 1920×1080 |
| `gallery-1.jpg` … `gallery-8.jpg` | Homepage **Before & After** gallery. Fill as many as you like — empty ones are skipped, and the whole section hides if all are empty. | JPG, ~1200×900, landscape |
| `rv-hero.jpg` | `/rv-detailing` hero background. | JPG, 1920×1080 |
| `boat-hero.jpg` | `/boat-detailing` hero background. | JPG, 1920×1080 |

## How it works

The site asks the server (`/api/media`) which of these files exist and are
non-empty, then shows only those. Keep the **exact same file names** — the site
looks them up by name.
