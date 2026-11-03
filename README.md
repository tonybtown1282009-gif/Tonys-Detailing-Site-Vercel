# tonys-detailing

Website for **Tony's Detailing** — professional mobile auto detailing based in Chardon, OH.

## Branch Strategy

| Branch | Purpose |
|--------|--------|
| `main` | Live production version — always matches what's deployed on Vercel |
| `dev`  | Working branch for changes before they go live; merge into `main` when ready |
| `v1`   | Snapshot of the original site (Version 1) — never modified |

## Deployment

The site deploys automatically from the `main` branch via Vercel. `app.py` serves everything.


## v3 site structure (lead-gen redesign)

The main pages are Jinja templates rendered by Flask; the older pages are
still static `.html` files.

| URL | Template | Notes |
|-----|----------|-------|
| `/` | `templates/home.html` | Hero → services → reviews → why us → ceramic → work → quote form |
| `/services` | `services.html` | All six services + full pricing, maintenance plans, service area |
| `/ceramic-coating` | `ceramic.html` | Flagship page |
| `/full-detail`, `/interior-detailing`, `/wash-n-wax`, `/paint-correction`, `/headlight-restoration` | `service.html` | One template, content from `site_content.py` |
| `/about`, `/contact`, `/quote` | same names | |
| `/lp/full-detail`, `/lp/ceramic-coating` | `landing.html` | **Meta ad landing pages** — no nav menu, form built in, `noindex`, not in the sitemap |

- **Copy** (service descriptions, FAQs, reviews, social links, landing-page
  headlines/promos) lives in `site_content.py`.
- **Prices** come from `BASE_PRICES` / `ADDON_PRICES` in `app.py` — change them
  there and every card, table and quote email updates.
- **Shared chrome** (nav, footer, mobile call/quote bar) is `templates/base.html`;
  the quote form and cards are in `templates/_macros.html`.
- Styles: `static/site.css`. Scripts: `static/site.js` (nav, video, call
  tracking, UTM capture) and `static/quote.js` (the form).
- Images: `python tools/build_v3_assets.py` rebuilds `static/img/` (WebP) and the
  inline icon set from the photos in `static/gallery/`.
- Any link can preselect a service in the form: `/quote?service=ceramic-coating`
  (slugs: `full-detail`, `interior-detailing`, `wash-n-wax`, `paint-correction`,
  `ceramic-coating`, `headlight-restoration`). Add `utm_source`/`utm_campaign`
  to ad URLs — they're saved with the lead.

### Quote form delivery (`/api/quote`)

Each lead is saved to SQLite, emailed to the shop via Resend, and — if
`SHEETS_WEBHOOK_URL` is set — appended to a Google Sheet. SQLite on Vercel is
wiped on cold starts, so on Vercel a lead only counts as received once the email
**or** the sheet accepted it; otherwise the visitor sees a "call or text us"
screen instead of a false confirmation.

Vercel environment variables (Production **and** Preview):

| Variable | Purpose |
|----------|---------|
| `RESEND_API_KEY` | Sends the lead email |
| `RESEND_FROM` | Optional verified sender |
| `SHEETS_WEBHOOK_URL` | Optional Google Sheets backup (below) |

**Google Sheets backup:** in the sheet, Extensions → Apps Script, paste the
script below, then Deploy → New deployment → Web app (Execute as: Me, Who has
access: Anyone). Put the web-app URL in `SHEETS_WEBHOOK_URL`.

```js
function doPost(e) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName('Quotes') || ss.insertSheet('Quotes');
  var d = JSON.parse(e.postData.contents);
  var cols = ['created','first_name','last_name','phone','email','vehicle_year',
    'vehicle_make','vehicle_model','vehicle_size','zip','area','miles','services',
    'ceramic_package','correction_type','last_detailed','condition','timing',
    'utilities','notes','contact_method','call_time','source_page','utm','estimate'];
  if (sheet.getLastRow() === 0) sheet.appendRow(cols);
  sheet.appendRow(cols.map(function (c) { return d[c] === undefined ? '' : d[c]; }));
  return ContentService.createTextOutput('ok');
}
```

Service-area flags come from `static/data/service-zips.json` (straight-line
miles from Chardon; rebuild with `python tools/build_service_zips.py`).

## Updating photos & video

All swappable media lives in [`static/media/`](static/media/) as named slots.
**To update media, replace the file with the same name and push** — no code
changes needed.

| Slot | Shows up on |
|------|-------------|
| `hero-loop.mp4` | Homepage hero loop on desktop/landscape screens (16:9). Empty until you add footage — the hero shows a still photo meanwhile. |
| `hero-loop-vertical.mp4` | Homepage hero loop on phones (9:16). |
| `hero-video.mp4` | Legacy clip, no longer used by the hero. |
| `hero-fallback.jpg` | Homepage hero background when there's no video (and the video's poster). |
| `gallery-1.jpg` … `gallery-8.jpg` | Homepage **Before & After** gallery. |
| `rv-hero.jpg` | `/rv-detailing` hero background. |
| `boat-hero.jpg` | `/boat-detailing` hero background. |

Each slot ships as an empty placeholder and only appears once its file has real
content, so you can fill them in any order. Empty gallery slots are skipped, and
the gallery section hides entirely until at least one photo is added. The site
detects what's filled via the `/api/media` endpoint (see `app.py`); details are
in [`static/media/README.md`](static/media/README.md).

## Mobile layout

Phones (≤720px) get an app-style shell defined in
[`static/mobile-app.css`](static/mobile-app.css), linked from every page
*after* that page's inline `<style>` so its same-specificity rules win
without `!important`. Above 720px the file contributes nothing but a few
`display:none` rules, so the desktop layout is untouched.

The pattern is the usual native-app one (Instagram / Netflix / DoorDash):

- the page scrolls **vertically only** — `overflow-x:clip` on `html`/`body`;
- content is stacked full-width sections, 16px gutters, 32px apart;
- inside a section, the items sit on one **horizontal rail** the user swipes
  independently of the page;
- a compact sticky header on top and a fixed 5-item tab bar at the bottom,
  both respecting `env(safe-area-inset-*)`.

**To turn a section's item list into a rail, add `m-rail` to its container.**
Cards are `min(78vw, 320px)` with a 12px gap, so the next one peeks in at the
right edge; the scrollbar is hidden and snapping is `x mandatory` /
`scroll-snap-align:start`. Add an optional `<a class="m-seeall">` inside the
section's `.section-head` for the right-aligned "See all" link, or a
`<div class="m-railhead"><h2>…</h2></div>` for sections that have no desktop
heading.

Pricing and the booking/contact forms deliberately stay stacked — a
reference table and a form are not a set of browsable cards, so a swipe rail
would be the wrong control. The wide price table restacks into one block per
service via the `data-label` attribute on each price cell.

Dark mode is driven by the existing CSS variables under
`prefers-color-scheme: dark`, scoped to the mobile shell; the desktop
stylesheet hard-codes light surfaces throughout and is left alone.

## Fonts

Pages load `fonts/*.woff2` (small, Latin-subset) and fall back to the full
`fonts/*.ttf`. If you replace a TTF, regenerate its WOFF2:

```
pip install -r requirements-dev.txt
python tools/build_fonts.py
```

**Font and image files must be committed as real binaries.** At one point every
font (and `assets/logo-on-black.png`) was accidentally committed as base64
*text*, which made browsers silently fall back to system fonts;
`tests/test_booking.py::test_fonts_are_real_binaries` now guards against a
repeat.

## Icons

Icons are [Lucide](https://lucide.dev), self-hosted at
`assets/lucide-<version>.min.js` and pinned so a CDN release can't change or
break them. To upgrade: download the new `dist/umd/lucide.min.js` from the
`lucide` npm package, add it under the new versioned name, and update the
`<script src>` tag in each page.

## SEO & serving notes

- Every page carries canonical/Open Graph/Twitter tags and the favicon set in
  `assets/`; the homepage embeds LocalBusiness JSON-LD.
- `robots.txt` and `sitemap.xml` are generated by `app.py` from
  `PUBLIC_PAGES` — add new pages to that tuple.
- Only `fonts/`, `assets/`, and `static/` are ever served by the static
  route; app source, tests, and any local database/.env are not reachable
  over HTTP. Unknown URLs get the branded `404.html`.
