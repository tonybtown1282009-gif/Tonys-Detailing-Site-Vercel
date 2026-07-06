---
name: verify
description: Build, run, and drive this site locally to verify a change end-to-end (Flask server + Playwright screenshots).
---

# Verify a change to Tony's Detailing site

Static HTML pages served by a small Flask app (`app.py`) — one process, no build step.

## Launch

```bash
python3 -m venv /tmp/venv && /tmp/venv/bin/pip install -q -r requirements.txt -r requirements-dev.txt
/tmp/venv/bin/python -c "from app import app; app.run(port=5057)" &
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:5057/   # expect 200
```

Clean URLs (`/`, `/gallery`, `/booking`, …) and `.html` forms both work; the
catch-all only serves `fonts/`, `assets/`, `static/`.

## Drive

Use Playwright (Python) with the pre-installed Chromium — do NOT `playwright install`:

```python
import glob
chrome = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
browser = p.chromium.launch(executable_path=chrome)
```

Worth checking per change: desktop 1440px + mobile 390px viewports (mobile
context with `has_touch=True` — several features branch on
`@media (hover:hover) and (pointer:fine)`), `/api/media` manifest JSON, and
`page.on("response")` for 4xx on local assets.

## Gotchas

- Hover-revealed elements (e.g. the gallery strip's "View All" overlay)
  intercept the pointer once visible — `locator.hover()` times out on the
  element underneath. Use `page.mouse.move(x, y)` with bounding-box coords.
- `hero-video.mp4` shows `requestfailed` in headless Chromium (no H.264
  codec). Environment noise, not a site bug.
- googletagmanager.com requests fail in the sandbox — ignore.
- Tests (`pytest tests/ -q`) are CI's job; run the app for verification.
