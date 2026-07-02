# tonys-detailing

Website for **Tony's Detailing** — professional mobile auto detailing based in Chardon, OH.

## Branch Strategy

| Branch | Purpose |
|--------|--------|
| `main` | Live production version — always matches what's deployed on Vercel |
| `dev`  | Working branch for changes before they go live; merge into `main` when ready |
| `v1`   | Snapshot of the original site (Version 1) — never modified |

## Deployment

The site deploys automatically from the `main` branch via Vercel. The entry point is `index.html`.

## Updating photos & video

All swappable media lives in [`static/media/`](static/media/) as named slots.
**To update media, replace the file with the same name and push** — no code
changes needed.

| Slot | Shows up on |
|------|-------------|
| `hero-video.mp4` | Homepage hero background (desktop). Falls back to `hero-fallback.jpg`, and always uses the image on phones. |
| `hero-fallback.jpg` | Homepage hero background when there's no video (and the video's poster). |
| `gallery-1.jpg` … `gallery-8.jpg` | Homepage **Before & After** gallery. |
| `rv-hero.jpg` | `/rv-detailing` hero background. |
| `boat-hero.jpg` | `/boat-detailing` hero background. |

Each slot ships as an empty placeholder and only appears once its file has real
content, so you can fill them in any order. Empty gallery slots are skipped, and
the gallery section hides entirely until at least one photo is added. The site
detects what's filled via the `/api/media` endpoint (see `app.py`); details are
in [`static/media/README.md`](static/media/README.md).
