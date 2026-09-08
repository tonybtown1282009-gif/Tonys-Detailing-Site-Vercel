"""
Build the six service-area landing pages from the shared site shell.

Each page is a static file served straight off the project root, like every
other page here. Rather than hand-copy the ~1,000-line shell six times, this
script lifts it out of a donor page (boat-detailing.html) and stamps the
per-town content into it, so a change to the nav or footer only has to be
made once and re-run:

    python tools/build_area_pages.py

The pricing table is read out of the "Base Pricing by Vehicle Size" card in
index.html rather than retyped, so the towns can never drift from the
public pricing table.
"""

import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DONOR = os.path.join(BASE_DIR, "boat-detailing.html")
INDEX = os.path.join(BASE_DIR, "index.html")
CSS_OUT = os.path.join(BASE_DIR, "static", "area-page.css")
SITE = "https://tonys-detailing.vercel.app"

# ── Per-town content ──────────────────────────────────────────────────────
# `intro` and `local` are written per town on purpose: a page that is the
# same paragraph with the name swapped is exactly what a search engine
# discards, and it reads as filler to an actual customer too.
TOWNS = [
    {
        "slug": "gates-mills",
        "name": "Gates Mills",
        "h1": "Mobile Car Detailing in Gates Mills, Ohio",
        "title": "Car Detailing in Gates Mills, OH | Tony's Detailing",
        "desc": (
            "Mobile car detailing in Gates Mills, Ohio. We bring the full "
            "setup to your driveway — no drop-off, no waiting room. Book "
            "online or call (216) 903-4783."
        ),
        "intro": (
            "Gates Mills sits down in the Chagrin River valley, and the "
            "village's tree cover is the thing that shows up on paintwork "
            "here more than anywhere else we work. Sap, pollen, and the fine "
            "grit that comes off a long wooded driveway settle on a car that "
            "never sees a garage roof, and they etch if they sit. Because we "
            "come to you, the car gets decontaminated where it parks — no "
            "drive into town with a week of tree debris still baked on."
        ),
        "local": (
            "Long private drives are normal in Gates Mills, and a few of them "
            "are gravel. That is not a problem on our end: the van carries "
            "its own water and power, so we can set up well back from the "
            "road and work without running anything off the house. If your "
            "drive is tight or the turnaround is awkward, mention it when you "
            "book and we will plan the approach ahead of time."
        ),
    },
    {
        "slug": "hunting-valley",
        "name": "Hunting Valley",
        "h1": "Hunting Valley Car Detailing, At Your Home",
        "title": "Car Detailing in Hunting Valley, OH | Tony's Detailing",
        "desc": (
            "Mobile car detailing in Hunting Valley, Ohio. Full interior and "
            "exterior detailing done at your home, on your schedule. Book "
            "online or call (216) 903-4783."
        ),
        "intro": (
            "Hunting Valley is spread thin on purpose — large lots, few "
            "through roads, and a long way to the nearest place you could "
            "leave a car for the afternoon. That is the whole argument for "
            "mobile detailing out here. We arrive with the water, the power, "
            "and the extraction gear already in the van, and the car never "
            "leaves the property."
        ),
        "local": (
            "A lot of what we detail in Hunting Valley is a second or third "
            "vehicle that gets driven seasonally, which brings its own list: "
            "dust film from sitting, a musty interior, flat-spotted grime "
            "along the lower panels. Those respond well to a Full Detail with "
            "clay decontamination rather than a straight wash. We can also "
            "do more than one vehicle in a single visit — say so when you "
            "book so the day gets scheduled with enough room."
        ),
    },
    {
        "slug": "pepper-pike",
        "name": "Pepper Pike",
        "h1": "Car Detailing in Pepper Pike, Ohio",
        "title": "Car Detailing in Pepper Pike, OH | Tony's Detailing",
        "desc": (
            "Mobile car detailing in Pepper Pike, Ohio. Interior details, "
            "full details, and ceramic coating at your home. Book online or "
            "call (216) 903-4783."
        ),
        "intro": (
            "Pepper Pike is a commuter town, and commuter cars wear "
            "differently. The mileage goes on I-271 and Chagrin Boulevard, "
            "which means road film on the lower doors, brake dust welded to "
            "the front wheels, and an interior that collects a year of coffee "
            "cups and floor-mat salt. Most Pepper Pike bookings we take are "
            "an Interior Detail or a Full Detail for exactly that reason."
        ),
        "local": (
            "Winter is the hard season here. Salt tracked in from the "
            "driveway works into the carpet and stays there until something "
            "actually pulls it out, which is what hot-water extraction is "
            "for — a shop vacuum moves the loose grit and leaves the rest. "
            "If your mats have that white bloom on them by February, that is "
            "the service you want."
        ),
    },
    {
        "slug": "moreland-hills",
        "name": "Moreland Hills",
        "h1": "Moreland Hills Mobile Car Detailing",
        "title": "Car Detailing in Moreland Hills, OH | Tony's Detailing",
        "desc": (
            "Mobile car detailing in Moreland Hills, Ohio. We come to your "
            "driveway with everything needed for a full detail. Book online "
            "or call (216) 903-4783."
        ),
        "intro": (
            "Moreland Hills is wooded, hilly, and largely residential, and "
            "the driveways run steep enough that where a car sits matters to "
            "how it gets washed. We look for a level spot on arrival so the "
            "rinse water drains away from the panels instead of running back "
            "across them — a small thing that shows up in whether the glass "
            "dries streak-free."
        ),
        "local": (
            "The other Moreland Hills constant is deer. Between the "
            "Chagrin River corridor and the reservation land nearby, a lot "
            "of vehicles here pick up bug and organic residue on the front "
            "end through the warm months. That comes off with a clay and "
            "iron decontamination step, which is priced by vehicle size and "
            "can be added to any tier."
        ),
    },
    {
        "slug": "chagrin-falls",
        "name": "Chagrin Falls",
        "h1": "Car Detailing in Chagrin Falls, Ohio",
        "title": "Car Detailing in Chagrin Falls, OH | Tony's Detailing",
        "desc": (
            "Mobile car detailing in Chagrin Falls, Ohio. Detailing done in "
            "your own driveway — no downtown parking required. Book online "
            "or call (216) 903-4783."
        ),
        "intro": (
            "If you live near downtown Chagrin Falls, you already know the "
            "parking math: leaving a car somewhere for four hours is the "
            "hard part, not the detail itself. We work at the house instead. "
            "The village is one of the shorter runs from our home base in "
            "Chardon, so it is an easy area for us to schedule around."
        ),
        "local": (
            "Older homes near the falls often have a detached garage or a "
            "narrow drive shared with a neighbor, so we ask for roughly a "
            "car-and-a-half of width to work in — enough to open doors fully "
            "and get around the vehicle. Street-side works too if the "
            "driveway is genuinely too tight; just flag it when you book so "
            "we are not sorting it out on arrival."
        ),
    },
    {
        "slug": "bentleyville",
        "name": "Bentleyville",
        "h1": "Bentleyville Car Detailing, Done At Home",
        "title": "Car Detailing in Bentleyville, OH | Tony's Detailing",
        "desc": (
            "Mobile car detailing in Bentleyville, Ohio. Full interior and "
            "exterior service brought to your driveway. Book online or call "
            "(216) 903-4783."
        ),
        "intro": (
            "Bentleyville is small — a few hundred households strung along "
            "the Chagrin River south of the falls — and there is no detail "
            "shop in the village. The nearest options are a drive out to "
            "Solon or Chagrin Falls and back, twice, around whatever the "
            "shop's schedule allows. Mobile service removes both trips."
        ),
        "local": (
            "Because the village is compact, we can usually fit a "
            "Bentleyville booking alongside a Chagrin Falls or Moreland "
            "Hills job on the same day, which makes it easier to get a slot "
            "that is not two weeks out. If you have a preferred day, ask — "
            "there is a reasonable chance we are already going to be nearby."
        ),
    },
]


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def extract_pricing_rows(index_html):
    """Lift the base pricing rows out of index.html's #pricing section.

    Returns the <tbody> inner HTML verbatim, so the town pages quote the same
    numbers the pricing table shows and cannot drift from it.
    """
    card = re.search(
        r"<h3>Base Pricing by Vehicle Size</h3>.*?<tbody>(.*?)</tbody>",
        index_html,
        re.S,
    )
    if not card:
        raise SystemExit("could not find the base pricing table in index.html")
    return card.group(1).strip("\n")


def shell_parts(donor):
    """Split the donor page into the bits every page shares."""
    style = re.search(r"<style>(.*?)</style>", donor, re.S).group(1)
    foot_start = donor.find("<footer>")
    return {"style": style, "tail": tail_for_towns(donor[foot_start:])}


def area_menu(indent, arrow=False):
    """The six town links, shared by the desktop dropdown and the drawer."""
    tail = ' <i data-lucide="arrow-right"></i>' if arrow else ""
    return "\n".join(
        f'{indent}<a href="/{t["slug"]}">{t["name"]}{tail}</a>' for t in TOWNS
    )


def nav(town):
    """The shared site nav, with a Service Area dropdown of the town pages.

    Built here rather than lifted from the donor because the donor's nav
    carries its own page-specific links; only the Services dropdown markup is
    reused verbatim so the existing CSS and open/close script still drive it.
    """
    return f"""<!-- \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 NAV \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 -->
<nav id="nav">
  <a href="/" class="brand" aria-label="Tony's Detailing \u2014 home">
    <span class="brand-plate"><img src="/assets/logo.png" alt=""></span>
    <span class="brand-text">
      <span class="n">Tony's Detailing</span>
      <span class="s">Chardon &middot; OH</span>
    </span>
  </a>
  <div class="nav-links" role="navigation">
    <div class="nav-dd" id="navSvcDd">
      <button type="button" class="nav-dd-btn" aria-expanded="false" aria-controls="navSvcMenu">Services <i data-lucide="chevron-down"></i></button>
      <div class="nav-dd-menu" id="navSvcMenu">
        <a href="/#services">Car Detailing</a>
        <a href="/rv-detailing">RV Detailing</a>
        <a href="/boat-detailing">Boat Detailing</a>
        <a href="/ceramic-coating">Ceramic Coating</a>
      </div>
    </div>
    <div class="nav-dd" id="navAreaDd">
      <button type="button" class="nav-dd-btn" aria-expanded="false" aria-controls="navAreaMenu">Service Area <i data-lucide="chevron-down"></i></button>
      <div class="nav-dd-menu" id="navAreaMenu">
        <a href="/#area">All Areas &amp; Rates</a>
{area_menu("        ")}
      </div>
    </div>
    <a href="#pricing">Pricing</a>
    <a href="/reviews">Reviews</a>
    <a href="/">Main Site</a>
  </div>
  <div class="nav-right">
    <a href="tel:+12169034783" class="nav-phone" onclick="gtag('event','conversion',{{'send_to':'AW-18237414368/t4VuCLPxv8gcEOC3o_hD'}})"><i data-lucide="phone"></i>(216) 903-4783</a>
    <a href="/booking" class="btn sm">Book Now</a>
    <!-- Mobile-only call button: the desktop nav-phone link is hidden at this
         breakpoint, so keep the number one 44\u00d744 tap away. -->
    <a href="tel:+12169034783" class="m-call" aria-label="Call (216) 903-4783" onclick="gtag('event','conversion',{{'send_to':'AW-18237414368/t4VuCLPxv8gcEOC3o_hD'}})"><i data-lucide="phone"></i></a>
    <button class="hbg" id="hbg" aria-label="Open menu" aria-expanded="false"><span></span><span></span><span></span></button>
  </div>
</nav>
<div id="drawer">
  <button type="button" class="drawer-dd-btn" id="drawerSvcBtn" aria-expanded="false" aria-controls="drawerSvcList">Services <i data-lucide="chevron-down"></i></button>
  <div class="drawer-dd-list" id="drawerSvcList" hidden>
    <a href="/#services">Car Detailing <i data-lucide="arrow-right"></i></a>
    <a href="/rv-detailing">RV Detailing <i data-lucide="arrow-right"></i></a>
    <a href="/boat-detailing">Boat Detailing <i data-lucide="arrow-right"></i></a>
    <a href="/ceramic-coating">Ceramic Coating <i data-lucide="arrow-right"></i></a>
  </div>
  <button type="button" class="drawer-dd-btn" id="drawerAreaBtn" aria-expanded="false" aria-controls="drawerAreaList">Service Area <i data-lucide="chevron-down"></i></button>
  <div class="drawer-dd-list" id="drawerAreaList" hidden>
    <a href="/#area">All Areas &amp; Rates <i data-lucide="arrow-right"></i></a>
{area_menu("    ", arrow=True)}
  </div>
  <a href="#pricing">Pricing <i data-lucide="arrow-right"></i></a>
  <a href="/reviews">Reviews <i data-lucide="arrow-right"></i></a>
  <a href="/">Main Site <i data-lucide="arrow-right"></i></a>
  <a href="/booking" class="btn" style="margin-top:16px;justify-content:center;">Book Now</a>
</div>

"""


def mark_current(markup, slug):
    """Flag the town's own entries in the nav so they render as current."""
    return markup.replace(
        f'<a href="/{slug}">', f'<a href="/{slug}" aria-current="page">'
    )


def schema(town):
    """Service + LocalBusiness JSON-LD, areaServed pinned to this town.

    The Service hangs off the same #business @id the other pages use, so the
    town pages read as services this business offers in that place rather
    than as free-floating Service objects.
    """
    return f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@graph": [
    {{
      "@type": "AutoWash",
      "@id": "{SITE}/#business",
      "name": "Tony's Detailing",
      "url": "{SITE}/",
      "telephone": "+12169034783",
      "email": "tonysdetailing.net@gmail.com",
      "image": "{SITE}/assets/og-card.jpg",
      "priceRange": "$$",
      "address": {{
        "@type": "PostalAddress",
        "addressLocality": "Chardon",
        "addressRegion": "OH",
        "addressCountry": "US"
      }},
      "areaServed": {{
        "@type": "City",
        "name": "{town['name']}",
        "addressRegion": "OH",
        "addressCountry": "US"
      }}
    }},
    {{
      "@type": "Service",
      "@id": "{SITE}/{town['slug']}#service",
      "name": "Mobile Car Detailing in {town['name']}, OH",
      "serviceType": "Mobile auto detailing",
      "url": "{SITE}/{town['slug']}",
      "provider": {{"@id": "{SITE}/#business"}},
      "areaServed": {{
        "@type": "City",
        "name": "{town['name']}",
        "addressRegion": "OH",
        "addressCountry": "US"
      }}
    }}
  ]
}}
</script>"""


def head(town):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=AW-18237414368"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'AW-18237414368');
</script>
<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
}})(window,document,'script','dataLayer','GTM-W5PW7BVG');</script>
<!-- End Google Tag Manager -->
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{town['title']}</title>
<meta name="description" content="{town['desc']}">
<link rel="canonical" href="{SITE}/{town['slug']}">
<meta name="theme-color" content="#1e3a5f">
<link rel="icon" href="/assets/favicon.ico" sizes="48x48">
<link rel="icon" href="/assets/favicon-16x16.png" type="image/png" sizes="16x16">
<link rel="icon" href="/assets/favicon-32x32.png" type="image/png" sizes="32x32">
<link rel="icon" href="/assets/favicon-192.png" type="image/png" sizes="192x192">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Tony's Detailing">
<meta property="og:title" content="{town['title']}">
<meta property="og:description" content="{town['desc']}">
<meta property="og:url" content="{SITE}/{town['slug']}">
<meta property="og:image" content="{SITE}/assets/og-card.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
{schema(town)}
<script src="/assets/lucide-1.23.0.min.js" defer></script>
<script>function tdIcons(){{if(window.lucide){{lucide.createIcons();}}else{{document.addEventListener('DOMContentLoaded',function(){{if(window.lucide)lucide.createIcons();}});}}}}</script>
<script>try{{if(localStorage.getItem('td_promo15_dismissed')==='1')document.documentElement.classList.add('promo-off');}}catch(e){{}}</script>
<!-- The shell styles live in an external sheet rather than inline (six pages
     shared one copy), so the fonts it declares are two hops from the HTML.
     Preload the faces used above the fold so they start downloading with the
     stylesheet instead of after it. -->
<link rel="preload" as="font" type="font/woff2" href="/fonts/Montserrat-ExtraBold.woff2" crossorigin>
<link rel="preload" as="font" type="font/woff2" href="/fonts/Montserrat-SemiBold.woff2" crossorigin>
<link rel="preload" as="font" type="font/woff2" href="/fonts/Inter-Regular.woff2" crossorigin>
<link rel="stylesheet" href="/static/area-page.css">
<!-- Mobile app shell (≤720px): vertical page, horizontal card rails, sticky
     header + bottom tab bar, safe areas, dark mode. Loaded last so its
     same-specificity rules win over the desktop styles above. -->
<link rel="stylesheet" href="/static/mobile-app.css">
</head>
<body>
<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-W5PW7BVG"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->
"""


def body(town, pricing_rows):
    others = [t for t in TOWNS if t["slug"] != town["slug"]]
    nearby = "\n".join(
        f'        <a href="/{t["slug"]}" class="btn ghost sm">{t["name"]}</a>'
        for t in others
    )
    return f"""
<div id="panes">

<!-- ─────────────── HERO ─────────────── -->
<section id="hero">
  <div class="hero-grid"></div>
  <div class="hero-glow"></div>
  <div class="hero-inner">
    <span class="hero-tag-row">
      <span class="dot"></span>
      <span>Mobile Service &middot; {town['name']}, Ohio</span>
    </span>
    <h1 class="hero-h1">{town['h1']}</h1>
    <p class="hero-sub">{town['intro']}</p>
    <div class="hero-actions">
      <a href="/booking" class="btn xl">Book Your Detail <i data-lucide="arrow-right"></i></a>
      <a href="tel:+12169034783" class="btn ghost lg" onclick="gtag('event','conversion',{{'send_to':'AW-18237414368/t4VuCLPxv8gcEOC3o_hD'}})"><i data-lucide="phone"></i> (216) 903-4783</a>
    </div>
  </div>
</section>

<!-- ─────────────── LOCAL NOTES ─────────────── -->
<section id="local">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Working In {town['name']}</span>
      <h2>What To Expect On The Day</h2>
    </div>
    <p class="lead">{town['local']}</p>
    <p class="lead">Everything runs off the van &mdash; water, power, and extraction &mdash; so all we need from you is a parking spot and access to the vehicle. Travel zone and any distance surcharge are confirmed when you book; see <a href="/#area">the service area map</a> for how the zones work.</p>
  </div>
</section>

<!-- ─────────────── PRICING ─────────────── -->
<section id="pricing">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Transparent Pricing</span>
      <h2>{town['name']} Detailing Prices</h2>
      <p>The same published rates we charge everywhere we work &mdash; base pricing scales with vehicle size. Condition upcharges are estimates, confirmed after a quick on-arrival walk-around.</p>
    </div>
    <div class="pr-card">
      <div class="pr-head">
        <i data-lucide="car"></i>
        <h3>Base Pricing by Vehicle Size</h3>
        <span class="pr-pill">USD</span>
      </div>
      <table class="ptbl">
        <thead>
          <tr>
            <th>Service</th>
            <th>Sedan</th>
            <th>SUV / Crossover</th>
            <th>Lg. SUV / Truck</th>
            <th>Minivan</th>
          </tr>
        </thead>
        <tbody>
{pricing_rows}
        </tbody>
      </table>
    </div>
    <div class="cert-actions">
      <a href="/#pricing" class="btn ghost lg">Add-Ons &amp; Upcharges <i data-lucide="arrow-right"></i></a>
      <a href="/ceramic-coating" class="btn ghost lg">Ceramic Coating <i data-lucide="arrow-right"></i></a>
    </div>
  </div>
</section>

<!-- ─────────────── NEARBY ─────────────── -->
<section id="nearby">
  <div class="wrap">
    <div class="section-head center">
      <span class="eyebrow">Nearby</span>
      <h2>Other Towns We Serve</h2>
      <p>{town['name']} is one stop on a route that covers Geauga, eastern Cuyahoga, and Lake counties.</p>
    </div>
    <div class="cert-actions">
{nearby}
    </div>
  </div>
</section>

<!-- ─────────────── FINAL CTA ─────────────── -->
<section id="cta">
  <div class="wrap">
    <div class="cta-inner">
      <h2>Book A Detail In {town['name']}</h2>
      <p>Pick a service and a day online, or call and we will sort it out in a couple of minutes.</p>
      <div class="cta-actions">
        <a href="/booking" class="btn xl">Book Online <i data-lucide="arrow-right"></i></a>
        <a href="tel:+12169034783" class="btn ghost lg" onclick="gtag('event','conversion',{{'send_to':'AW-18237414368/t4VuCLPxv8gcEOC3o_hD'}})"><i data-lucide="phone"></i> Call (216) 903-4783</a>
      </div>
    </div>
  </div>
</section>

<!-- ─────────────── FOOTER ─────────────── -->
"""


def tail_for_towns(tail):
    """Adapt the donor's footer + scripts for a town page.

    The donor tail carries two boat-specific things: a dropdown script wired
    to the Services ids only, and a footer line about boat condition. Both are
    rewritten here (with asserts, so a change to the donor fails loudly
    instead of silently shipping a broken page) rather than duplicated by hand
    across six files.
    """
    # 1. Make the dropdown script reusable so it drives Service Area too.
    swaps = [
        (
            "(function(){\n  var dd = document.getElementById('navSvcDd');",
            "function tdDropdown(ddId, dBtnId, dListId){\n"
            "  var dd = document.getElementById(ddId);",
        ),
        (
            "var dBtn = document.getElementById('drawerSvcBtn');",
            "var dBtn = document.getElementById(dBtnId);",
        ),
        (
            "var dList = document.getElementById('drawerSvcList');",
            "var dList = document.getElementById(dListId);",
        ),
        (
            "      dList.hidden = open;\n    });\n  }\n})();",
            "      dList.hidden = open;\n    });\n  }\n}\n"
            "tdDropdown('navSvcDd', 'drawerSvcBtn', 'drawerSvcList');\n"
            "tdDropdown('navAreaDd', 'drawerAreaBtn', 'drawerAreaList');",
        ),
    ]
    for old, new in swaps:
        if tail.count(old) != 1:
            raise SystemExit(f"expected exactly one occurrence of: {old[:60]!r}")
        tail = tail.replace(old, new, 1)
    tail = tail.replace(
        "/* ───────────────── SERVICES DROPDOWN (nav + mobile drawer) ───────────────── */",
        "/* ──────────────── NAV DROPDOWNS (nav + mobile drawer) ──────────────── */",
        1,
    )

    # 2. The footer disclaimer is written for boats on the donor page.
    old_disclaimer = "Results may vary based on boat condition."
    if old_disclaimer not in tail:
        raise SystemExit("donor footer disclaimer not found — check the donor")
    tail = tail.replace(
        old_disclaimer, "Results may vary based on vehicle condition.", 1
    )
    return tail


def main():
    donor = read(DONOR)
    parts = shell_parts(donor)
    pricing_rows = extract_pricing_rows(read(INDEX))

    os.makedirs(os.path.dirname(CSS_OUT), exist_ok=True)
    with open(CSS_OUT, "w", encoding="utf-8") as fh:
        fh.write(
            "/* Shared desktop styles for the service-area pages.\n"
            "   Generated by tools/build_area_pages.py from the site shell —\n"
            "   edit the donor page, not this file. */\n"
        )
        # The donor's @font-face rules use paths relative to the page
        # (fonts/X.woff2). This sheet is served from /static/, where those
        # would resolve to /static/fonts/ and 404, so anchor them at the root.
        css = re.sub(r"url\('fonts/", "url('/fonts/", parts["style"])
        if "url('fonts/" in css:
            raise SystemExit("a relative font URL survived rewriting")
        fh.write(css.strip("\n") + "\n")

    for town in TOWNS:
        html = mark_current(
            head(town) + nav(town) + body(town, pricing_rows) + parts["tail"],
            town["slug"],
        )
        out = os.path.join(BASE_DIR, f"{town['slug']}.html")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"wrote {os.path.relpath(out, BASE_DIR)}")
    print(f"wrote {os.path.relpath(CSS_OUT, BASE_DIR)}")


if __name__ == "__main__":
    main()
