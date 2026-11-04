"""
Tony's Detailing — Flask + SQLite backend.

Serves the existing static frontend and handles booking submissions:
stores each booking in SQLite, calculates a price estimate and any
auto-discounts, tracks loyalty visits per email, and sends an email
notification to the shop via the Resend API.

Brand: Tony's Detailing | (216) 903-4783 | tonysdetailing.net@gmail.com
"""

import os
import sqlite3
from datetime import datetime

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    Response,
    send_file,
    send_from_directory,
)

import site_content

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional at runtime
    pass

# ──────────────────────────────────────────────────────────────────────────
#  Configuration
# ──────────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Vercel's serverless filesystem is read-only except for /tmp, so fall back
# there when running on Vercel. Locally the DB lives in the project root.
DB_PATH = os.environ.get("DATABASE_PATH") or (
    "/tmp/bookings.db" if os.environ.get("VERCEL") else os.path.join(BASE_DIR, "bookings.db")
)

SHOP_EMAIL = "tonysdetailing.net@gmail.com"
SHOP_PHONE = "(216) 903-4783"

# ──────────────────────────────────────────────────────────────────────────
#  Media slots
#  Named files live in static/media/. The site shows a slot only when its file
#  exists AND is non-empty, so committed empty placeholders stay hidden until a
#  real photo/video is dropped in with the same name. See static/media/README.md.
#  (Gallery photos work differently: static/gallery/placeholder-N.jpg are
#  always-visible placeholder images swapped in place — see that folder's README.)
# ──────────────────────────────────────────────────────────────────────────
MEDIA_DIR = os.path.join(BASE_DIR, "static", "media")
MEDIA_SLOTS = (
    "hero-loop.mp4",           # homepage hero, landscape screens (16:9)
    "hero-loop-vertical.mp4",  # homepage hero, phones (9:16)
    "hero-video.mp4",          # legacy clip, no longer used by the hero
    "hero-fallback.jpg",
    "rv-hero.jpg",
    "boat-hero.jpg",
)
_MEDIA_SET = frozenset(MEDIA_SLOTS)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
# Resend requires a verified sender domain. onboarding@resend.dev works out of
# the box for testing; set RESEND_FROM once a domain is verified.
RESEND_FROM = os.environ.get("RESEND_FROM", "Tony's Detailing <onboarding@resend.dev>")

# ──────────────────────────────────────────────────────────────────────────
#  Pricing (server-side, authoritative)
#  Mirrors the public pricing table on the site. Minivan is priced between
#  SUV and Large SUV/Truck.
# ──────────────────────────────────────────────────────────────────────────
VEHICLE_TYPES = ["Sedan", "SUV/Crossover", "Large SUV/Truck", "Minivan"]

BASE_PRICES = {
    "Wash n' Wax": {"Sedan": 140, "SUV/Crossover": 150, "Large SUV/Truck": 180, "Minivan": 165},
    "Interior Detail": {"Sedan": 120, "SUV/Crossover": 135, "Large SUV/Truck": 155, "Minivan": 145},
    "Full Detail": {"Sedan": 195, "SUV/Crossover": 215, "Large SUV/Truck": 240, "Minivan": 225},
    # Ceramic coatings, priced by size like everything else. Both the 3-Year
    # and Elite run the full process (bug and
    # clay decon, IPA wipe down, single-stage enhancement polish) and take about
    # six hours. No tier includes multi-stage paint correction.
    "Ceramic Coating (3-Year)": {
        "Sedan": 799.99, "SUV/Crossover": 849.99, "Large SUV/Truck": 1049.99, "Minivan": 949.99,
    },
    "Ceramic Coating (Elite 5-Year)": {
        "Sedan": 1099.99, "SUV/Crossover": 1149.99, "Large SUV/Truck": 1349.99, "Minivan": 1249.99,
    },
    # Maintenance plan visits — recurring upkeep between full details, separate
    # from the one-time tiers above. Lighter scope (see MAINTENANCE_SCOPE_NOTE),
    # so priced lower than a Wash, Clay, Seal at the same size. Minivan is
    # interpolated between SUV and Large SUV/Truck, matching the other rows.
    "Monthly Maintenance Visit": {"Sedan": 150, "SUV/Crossover": 160, "Large SUV/Truck": 180, "Minivan": 170},
    "Biweekly Maintenance Visit": {"Sedan": 140, "SUV/Crossover": 150, "Large SUV/Truck": 170, "Minivan": 160},
}

# Old service names still posted by bookmarked /booking links.
SERVICE_ALIASES = {"Wash, Clay, Seal": "Wash n' Wax"}

MAINTENANCE_SERVICES = {"Monthly Maintenance Visit", "Biweekly Maintenance Visit"}
MAINTENANCE_SCOPE_NOTE = (
    "Maintenance visits do not include extraction, stain treatment, pet hair "
    "removal, or odor treatment. If a visit requires any of these, it will be "
    "quoted as a standalone detail instead."
)

# Flat travel fee added per visit when the address falls outside the standard
# service radius (see the Service Area section on the site).
TRAVEL_FEE = 15

# Add-on pricing. Clay & Iron Decontamination scales with vehicle size.
CLAY_PRICES = {"Sedan": 60, "SUV/Crossover": 70, "Large SUV/Truck": 80, "Minivan": 70}
ADDON_PRICES = {
    "Leather Conditioning": 40,
    "Odor Eliminator": 50,  # mid-point of the advertised $40–$75 range
    "Headlight Restoration": 100,  # flat rate, any vehicle size
    # Ceramic coating add-ons, flat rate by coating durability.
    "Wheel Face Coating (3-Year)": 250,
    "Wheel Face Coating (5-Year)": 300,
    "Glass & Trim Coating (3-Year)": 250,
    "Glass & Trim Coating (5-Year)": 300,
    # "Clay & Iron Decontamination" handled separately (size dependent)
}

# Condition upcharges are estimates confirmed on arrival.
UPCHARGE_PRICES = {
    "Pet Hair": 30,
    "Heavy Staining": 30,
    "Smoke/Odor": 40,
    "Excessive Debris": 25,
}

# Services that qualify for the referral discount (Full Detail minimum).
REFERRAL_ELIGIBLE_SERVICES = {"Full Detail"}
REFERRAL_DISCOUNT = 35
MULTI_VEHICLE_RATE = 0.10  # 10% off for 2+ vehicles

app = Flask(__name__, static_folder=None)


# ──────────────────────────────────────────────────────────────────────────
#  Database
# ──────────────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the bookings table if it doesn't exist, then add any new columns."""
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT    NOT NULL,
            phone            TEXT    NOT NULL,
            email            TEXT,
            location         TEXT,
            vehicle_type     TEXT,
            service          TEXT,
            addons           TEXT,
            upcharges        TEXT,
            vehicle_type_2   TEXT,
            service_2        TEXT,
            addons_2         TEXT,
            upcharges_2      TEXT,
            num_vehicles     TEXT,
            referred_by      TEXT,
            discount_applied TEXT,
            total_estimate   REAL,
            visits           INTEGER DEFAULT 1,
            timestamp        TEXT
        )
        """
    )

    # Migrate older databases: add any columns introduced after first release.
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(bookings)")}
    new_columns = {
        "location": "TEXT",
        "vehicle_type_2": "TEXT",
        "service_2": "TEXT",
        "addons_2": "TEXT",
        "upcharges_2": "TEXT",
        "outside_radius": "INTEGER DEFAULT 0",
    }
    for column, col_type in new_columns.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE bookings ADD COLUMN {column} {col_type}")

    conn.commit()
    conn.close()


# ──────────────────────────────────────────────────────────────────────────
#  Estimate + discount logic
# ──────────────────────────────────────────────────────────────────────────
def parse_num_vehicles(raw):
    """Map the form value ('1', '2', '3+') to an integer multiplier."""
    digits = "".join(c for c in (raw or "") if c.isdigit())
    try:
        return max(1, int(digits))
    except ValueError:
        return 1


def vehicle_cost(service, vehicle_type, addons, upcharges):
    """Price a single vehicle: base (by service + size) + add-ons + upcharges."""
    vehicle = vehicle_type if vehicle_type in VEHICLE_TYPES else "Sedan"
    service = SERVICE_ALIASES.get(service, service)
    base = BASE_PRICES.get(service, {}).get(vehicle, 0)

    addon_total = 0
    for addon in addons:
        if addon == "Clay & Iron Decontamination":
            addon_total += CLAY_PRICES.get(vehicle, 70)
        else:
            addon_total += ADDON_PRICES.get(addon, 0)

    upcharge_total = sum(UPCHARGE_PRICES.get(u, 0) for u in upcharges)
    return base + addon_total + upcharge_total


def calculate_estimate(
    num_vehicles, referred_by, vehicle1, vehicle2=None,
    outside_radius=False,
):
    """
    Returns (total_estimate, discount_summary).

    Each vehicle (a dict of service/vehicle_type/addons/upcharges) is priced on
    its own. Vehicle 1 is always counted; when 2+ vehicles are booked, vehicle 2
    is priced and applied to each additional vehicle (so "3+" charges vehicle 2
    twice — additional vehicles are estimated at the same rate).

    Discounts: 10% for 2+ vehicles and a flat $35 referral credit (the order
    must include at least a Full Detail to qualify). Both can stack; the
    referral credit is applied as a flat amount after the multi-vehicle
    percentage.

    The travel fee is a flat $15 charge per visit (not per vehicle) when the
    address falls outside the standard service radius, added after discounts.
    """
    count = parse_num_vehicles(num_vehicles)

    subtotal = vehicle_cost(**vehicle1)
    services = [vehicle1.get("service", "")]

    if count >= 2 and vehicle2 and vehicle2.get("service"):
        subtotal += vehicle_cost(**vehicle2) * (count - 1)
        services.append(vehicle2.get("service", ""))

    # ── Discounts ──
    discount_total = 0.0
    notes = []

    if count >= 2:
        multi = round(subtotal * MULTI_VEHICLE_RATE, 2)
        discount_total += multi
        notes.append(f"Multi-vehicle 10% (-${multi:.2f})")

    if (referred_by or "").strip() and any(s in REFERRAL_ELIGIBLE_SERVICES for s in services):
        discount_total += REFERRAL_DISCOUNT
        notes.append(f"Referral (-${REFERRAL_DISCOUNT:.2f})")

    total = max(0.0, round(subtotal - discount_total, 2))

    if outside_radius:
        total = round(total + TRAVEL_FEE, 2)
        notes.append(f"Travel fee, outside standard radius (+${TRAVEL_FEE:.2f})")

    if notes:
        discount_summary = "; ".join(notes)
        if discount_total:
            discount_summary += f" | Total saved: ${discount_total:.2f}"
    else:
        discount_summary = "None"

    return total, discount_summary


def media_present(name):
    """True when a media slot exists and has real content (non-empty).

    Only known slot names are checked, so this can't be used to probe arbitrary
    paths on disk.
    """
    if name not in _MEDIA_SET:
        return False
    path = os.path.join(MEDIA_DIR, name)
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


# ──────────────────────────────────────────────────────────────────────────
#  Hero media (server-rendered)
#  The hero used to be built client-side from a /api/media fetch, which meant
#  nothing painted in the hero until that round trip finished. The markup is
#  stamped into the HTML here instead, so the image is in the document the
#  browser first parses. The video stays out of the critical path: it ships
#  with preload="none" and a data-src that a small inline script promotes
#  after load, on desktop only.
# ──────────────────────────────────────────────────────────────────────────
HERO_PLACEHOLDER = '<div class="hero-media" id="heroMedia"></div>'

# page file -> (still image slot, looping video slot or None)
HERO_SLOTS = {
    "rv-detailing.html": ("rv-hero.jpg", None),
    "boat-detailing.html": ("boat-hero.jpg", None),
}


def hero_markup(image_slot, video_slot):
    """Build the hero's inner markup for whichever slots are filled.

    Returns "" when nothing is filled, which leaves the container empty and
    lets the existing `.hero-media:empty` rule fall back to the gradient.
    """
    has_image = media_present(image_slot)
    parts = []
    if has_image:
        # fetchpriority=high: this is the largest contentful paint on the page.
        parts.append(
            f'<img src="/static/media/{image_slot}" alt="" '
            'fetchpriority="high" decoding="async">'
        )
    if video_slot and media_present(video_slot):
        poster = f' poster="/static/media/{image_slot}"' if has_image else ""
        parts.append(
            f'<video data-src="/static/media/{video_slot}"{poster} '
            'preload="none" muted loop playsinline aria-hidden="true"></video>'
        )
    return "".join(parts)


_page_cache = {}


def render_page(filename):
    """Serve a static page with its hero markup stamped in.

    Cached per file, keyed on the page's mtime and which media slots are
    filled, so a media swap (drop the file in, push) shows up without a code
    change and without re-reading the page on every request.
    """
    image_slot, video_slot = HERO_SLOTS[filename]
    path = os.path.join(BASE_DIR, filename)
    try:
        key = (
            os.path.getmtime(path),
            media_present(image_slot),
            bool(video_slot) and media_present(video_slot),
        )
    except OSError:
        return send_from_directory(BASE_DIR, filename)

    cached = _page_cache.get(filename)
    if cached is None or cached[0] != key:
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        markup = hero_markup(image_slot, video_slot)
        if markup:
            html = html.replace(
                HERO_PLACEHOLDER,
                HERO_PLACEHOLDER[:-6] + markup + "</div>",
                1,
            )
        cached = (key, html)
        _page_cache[filename] = cached
    return Response(cached[1], mimetype="text/html; charset=utf-8")


def record_visit_count(conn, email):
    """Loyalty stub: how many times this email has booked, including now."""
    email = (email or "").strip().lower()
    if not email:
        return 1
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM bookings WHERE LOWER(email) = ?", (email,)
    ).fetchone()
    return (row["c"] if row else 0) + 1


# ──────────────────────────────────────────────────────────────────────────
#  Email notification (Resend)
# ──────────────────────────────────────────────────────────────────────────
def send_notification_email(booking):
    """Send a booking notification to the shop. Failures are non-fatal."""
    if not RESEND_API_KEY:
        app.logger.warning("RESEND_API_KEY not set — skipping email notification.")
        return False

    try:
        import resend

        resend.api_key = RESEND_API_KEY

        def row(label, value):
            return (
                f"<tr>"
                f"<td style='padding:8px 14px;color:#8a8a8a;font-size:13px;"
                f"border-bottom:1px solid #eee;white-space:nowrap;'>{label}</td>"
                f"<td style='padding:8px 14px;color:#0a0a0a;font-size:14px;"
                f"border-bottom:1px solid #eee;font-weight:600;'>{value or '—'}</td>"
                f"</tr>"
            )

        def section(label):
            return (
                f"<tr><td colspan='2' style='padding:12px 14px 6px;background:#f4f6f9;"
                f"color:#1e3a5f;font-size:11px;font-weight:700;letter-spacing:.08em;"
                f"text-transform:uppercase;'>{label}</td></tr>"
            )

        vehicle2_rows = ""
        if booking.get("vehicle_type_2") or booking.get("service_2"):
            vehicle2_rows = (
                section("Second Vehicle")
                + row("Vehicle Type", booking.get("vehicle_type_2"))
                + row("Service", booking.get("service_2"))
                + row("Add-ons", booking.get("addons_2"))
                + row("Condition Upcharges", booking.get("upcharges_2"))
            )

        html = f"""
        <div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;">
          <div style="background:#1e3a5f;padding:22px 24px;border-radius:6px 6px 0 0;">
            <h1 style="color:#fff;font-size:20px;margin:0;letter-spacing:.02em;">
              New Booking Request
            </h1>
            <p style="color:#9ab4d4;font-size:13px;margin:6px 0 0;">Tony's Detailing</p>
          </div>
          <table style="width:100%;border-collapse:collapse;background:#fff;
                        border:1px solid #eee;border-top:none;">
            {row("Name", booking["name"])}
            {row("Phone", booking["phone"])}
            {row("Email", booking["email"])}
            {row("Location", booking.get("location"))}
            {row("Outside Service Radius", "Yes — +$15 travel fee" if booking.get("outside_radius") else "No")}
            {row("# Vehicles", booking["num_vehicles"])}
            {section("Vehicle 1")}
            {row("Vehicle Type", booking["vehicle_type"])}
            {row("Service", booking["service"])}
            {row("Add-ons", booking["addons"])}
            {row("Condition Upcharges", booking["upcharges"])}
            {vehicle2_rows}
            {section("Summary")}
            {row("Referred By", booking["referred_by"])}
            {row("Discount Applied", booking["discount_applied"])}
            {row("Estimated Total", f"${booking['total_estimate']:.2f}")}
            {row("Customer Visits", booking["visits"])}
            {row("Notes", booking.get("notes", ""))}
            {row("Submitted", booking["timestamp"])}
          </table>
          <p style="color:#8a8a8a;font-size:12px;margin:16px 0 0;text-align:center;">
            Estimate is calculated automatically and confirmed on arrival.
          </p>
        </div>
        """

        resend.Emails.send(
            {
                "from": RESEND_FROM,
                "to": [SHOP_EMAIL],
                "subject": f"New Booking — {booking['name']} ({booking['service']})",
                "html": html,
                "reply_to": booking["email"] or None,
            }
        )
        return True
    except Exception as exc:  # noqa: BLE001 — email must never break a booking
        app.logger.error("Failed to send Resend email: %s", exc)
        return False


# ──────────────────────────────────────────────────────────────────────────
#  Routes — booking API
# ──────────────────────────────────────────────────────────────────────────
@app.route("/api/book", methods=["POST"])
def book():
    form = request.form
    name = (form.get("name") or "").strip()
    phone = (form.get("phone") or "").strip()
    location = (form.get("location") or "").strip()

    if not name or not phone or not location:
        return jsonify({"ok": False, "error": "Name, phone, and location are required."}), 400

    email = (form.get("email") or "").strip()
    num_vehicles = (form.get("num_vehicles") or "1").strip()
    referred_by = (form.get("referred_by") or "").strip()
    notes = (form.get("notes") or "").strip()

    # Checkbox values arrive only when ticked; treat any present value as True.
    def checkbox(name):
        return bool((form.get(name) or "").strip())

    # Vehicle 1
    vehicle_type = (form.get("vehicle_type") or "").strip()
    service = (form.get("service") or "").strip()
    addons = [a.strip() for a in form.getlist("addons") if a.strip()]
    upcharges = [u.strip() for u in form.getlist("upcharges") if u.strip()]
    outside_radius = checkbox("outside_radius")

    # Vehicle 2 (only meaningful when 2+ vehicles are booked)
    vehicle_type_2 = (form.get("vehicle_type_2") or "").strip()
    service_2 = (form.get("service_2") or "").strip()
    addons_2 = [a.strip() for a in form.getlist("addons_2") if a.strip()]
    upcharges_2 = [u.strip() for u in form.getlist("upcharges_2") if u.strip()]

    has_second = parse_num_vehicles(num_vehicles) >= 2
    if not has_second:
        vehicle_type_2, service_2, addons_2, upcharges_2 = "", "", [], []

    v1 = {"service": service, "vehicle_type": vehicle_type, "addons": addons, "upcharges": upcharges}
    v2 = {"service": service_2, "vehicle_type": vehicle_type_2, "addons": addons_2, "upcharges": upcharges_2}

    total_estimate, discount_applied = calculate_estimate(
        num_vehicles, referred_by, v1, v2,
        outside_radius=outside_radius,
    )

    conn = get_db()
    visits = record_visit_count(conn, email)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn.execute(
        """
        INSERT INTO bookings (
            name, phone, email, location, vehicle_type, service, addons, upcharges,
            vehicle_type_2, service_2, addons_2, upcharges_2, outside_radius,
            num_vehicles, referred_by, discount_applied, total_estimate,
            visits, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name, phone, email, location, vehicle_type, service,
            ", ".join(addons), ", ".join(upcharges),
            vehicle_type_2, service_2, ", ".join(addons_2), ", ".join(upcharges_2),
            int(outside_radius),
            num_vehicles, referred_by, discount_applied, total_estimate, visits, timestamp,
        ),
    )
    conn.commit()
    conn.close()

    booking = {
        "name": name, "phone": phone, "email": email, "location": location,
        "vehicle_type": vehicle_type, "service": service,
        "addons": ", ".join(addons), "upcharges": ", ".join(upcharges),
        "vehicle_type_2": vehicle_type_2, "service_2": service_2,
        "addons_2": ", ".join(addons_2), "upcharges_2": ", ".join(upcharges_2),
        "outside_radius": outside_radius,
        "num_vehicles": num_vehicles, "referred_by": referred_by,
        "discount_applied": discount_applied, "total_estimate": total_estimate,
        "visits": visits, "notes": notes, "timestamp": timestamp,
    }
    send_notification_email(booking)

    return jsonify(
        {
            "ok": True,
            "total_estimate": total_estimate,
            "discount_applied": discount_applied,
            "visits": visits,
        }
    )


# ──────────────────────────────────────────────────────────────────────────
#  Quote requests (v3 lead form)
#  The multi-step form on every page posts here. Each lead is written to
#  SQLite, emailed to the shop (Resend) and — when SHEETS_WEBHOOK_URL is set —
#  appended to a Google Sheet. SQLite on Vercel lives in /tmp and is wiped on
#  cold starts, so a lead only counts as delivered once the email or the sheet
#  accepted it; otherwise the visitor is told to call/text instead of seeing a
#  false "received".
# ──────────────────────────────────────────────────────────────────────────
import json as _json
import re as _re
import urllib.request as _urlreq

SHEETS_WEBHOOK_URL = os.environ.get("SHEETS_WEBHOOK_URL", "")

QUOTE_SERVICES = (
    "Full Interior Detail",
    "Wash n' Wax",
    "Paint Correction",
    "Ceramic Coating",
    "Full Detail",
    "Headlight Restoration",
)
QUOTE_SERVICE_SLUGS = {
    "interior-detailing": "Full Interior Detail",
    "wash-n-wax": "Wash n' Wax",
    "paint-correction": "Paint Correction",
    "ceramic-coating": "Ceramic Coating",
    "full-detail": "Full Detail",
    "headlight-restoration": "Headlight Restoration",
}
CERAMIC_PACKAGES = {
    "3-Year Protection": "Ceramic Coating (3-Year)",
    "5-Year Protection (Elite)": "Ceramic Coating (Elite 5-Year)",
    "Not Sure — I'd Like More Information": None,
}
CORRECTION_TYPES = ("One-Step Correction", "More Extensive (Multi-Step) Correction", "Not Sure")
LAST_DETAILED = ("Within the Last 3 Months", "3–6 Months Ago", "6–12 Months Ago",
                 "More Than a Year Ago", "Never")
CONDITIONS = ("Light Cleaning Needed", "Moderate Dirt and Buildup", "Heavy Dirt or Stains",
              "Pet Hair", "Other")
TIMINGS = ("As Soon as Possible", "Within 1–2 Weeks", "Within a Month", "Just Researching for Now")
UTILITIES = ("Yes", "No", "I'm Not Sure")
CONTACT_METHODS = ("Phone Call", "Text Message", "Email")
CALL_TIMES = ("Morning", "Afternoon", "Evening", "Anytime", "I Prefer Text")

# Service-area tiers, matching the rules on /services (straight-line miles).
AREA_STANDARD_MI = 15
AREA_EXTENDED_MI = 25
_ZIP_PATH = os.path.join(BASE_DIR, "static", "data", "service-zips.json")
try:
    with open(_ZIP_PATH) as _fh:
        SERVICE_ZIPS = _json.load(_fh)
except (OSError, ValueError):
    SERVICE_ZIPS = {}

EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def area_for_zip(zip_code):
    """(tier, miles) for a ZIP: standard / extended / outside / unknown."""
    miles = SERVICE_ZIPS.get(zip_code)
    if miles is None:
        return "unknown", None
    if miles <= AREA_STANDARD_MI:
        return "standard", miles
    if miles <= AREA_EXTENDED_MI:
        return "extended", miles
    return "outside", miles


AREA_LABELS = {
    "standard": "Standard area (within 15 mi)",
    "extended": "Extended area (15–25 mi) — Full Detail minimum + travel fee",
    "outside": "Outside 25 mi — travel quoted case by case",
    "unknown": "ZIP not in service list — check location",
}


def _money(v):
    return f"${v:,.0f}" if float(v).is_integer() else f"${v:,.2f}"


def _price_text(price_key, size):
    row = BASE_PRICES.get(price_key, {})
    if not row:
        return ""
    if size in row:
        return f"{_money(row[size])} ({size})"
    lo, hi = min(row.values()), max(row.values())
    return f"{_money(lo)}–{_money(hi)} (size not given)"


def quote_estimate(services, size, ceramic_package):
    """Human-readable starting prices per requested service, for the email."""
    lines = []
    for svc in services:
        if svc == "Full Interior Detail":
            lines.append(f"{svc}: {_price_text('Interior Detail', size)}")
        elif svc in ("Wash n' Wax", "Full Detail"):
            lines.append(f"{svc}: {_price_text(svc, size)}")
        elif svc == "Ceramic Coating":
            key = CERAMIC_PACKAGES.get(ceramic_package)
            if key:
                lines.append(f"{svc} — {ceramic_package}: {_price_text(key, size)}")
            else:
                lines.append(
                    f"{svc}: 3-Year {_price_text('Ceramic Coating (3-Year)', size)}"
                    f" / Elite {_price_text('Ceramic Coating (Elite 5-Year)', size)}"
                )
        elif svc == "Headlight Restoration":
            lines.append(f"{svc}: {_money(ADDON_PRICES['Headlight Restoration'])} flat")
        elif svc == "Paint Correction":
            lines.append(f"{svc}: quoted after inspection")
    return lines


def _clean(value, allowed=None, limit=120):
    value = (value or "").strip()[:limit]
    if allowed is not None and value not in allowed:
        return ""
    return value


def init_quotes_table():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created TEXT, first_name TEXT, last_name TEXT, phone TEXT, email TEXT,
            vehicle_year TEXT, vehicle_make TEXT, vehicle_model TEXT, vehicle_size TEXT,
            zip TEXT, area TEXT, miles REAL, services TEXT, ceramic_package TEXT,
            correction_type TEXT, last_detailed TEXT, condition TEXT, timing TEXT,
            utilities TEXT, notes TEXT, contact_method TEXT, call_time TEXT,
            source_page TEXT, utm TEXT, estimate TEXT, delivered TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def parse_quote(form):
    """Validate a quote submission. Returns (lead, errors)."""
    errors = {}
    phone_digits = _re.sub(r"\D", "", form.get("phone") or "")
    if len(phone_digits) == 11 and phone_digits.startswith("1"):
        phone_digits = phone_digits[1:]
    services = [s for s in form.getlist("services") if s in QUOTE_SERVICES]
    services = sorted(set(services), key=QUOTE_SERVICES.index)
    lead = {
        "first_name": _clean(form.get("first_name"), limit=60),
        "last_name": _clean(form.get("last_name"), limit=60),
        "phone": phone_digits,
        "email": _clean(form.get("email"), limit=120),
        "vehicle_year": _clean(form.get("vehicle_year"), limit=4),
        "vehicle_make": _clean(form.get("vehicle_make"), limit=40),
        "vehicle_model": _clean(form.get("vehicle_model"), limit=60),
        "vehicle_size": _clean(form.get("vehicle_size"), VEHICLE_TYPES),
        "zip": _re.sub(r"\D", "", form.get("zip") or "")[:5],
        "services": services,
        "ceramic_package": _clean(form.get("ceramic_package"), CERAMIC_PACKAGES)
        if "Ceramic Coating" in services else "",
        "correction_type": _clean(form.get("correction_type"), CORRECTION_TYPES)
        if "Paint Correction" in services else "",
        "last_detailed": _clean(form.get("last_detailed"), LAST_DETAILED),
        "condition": [c for c in form.getlist("condition") if c in CONDITIONS],
        "timing": _clean(form.get("timing"), TIMINGS),
        "utilities": _clean(form.get("utilities"), UTILITIES),
        "notes": _clean(form.get("notes"), limit=2000),
        "contact_method": _clean(form.get("contact_method"), CONTACT_METHODS),
        "call_time": _clean(form.get("call_time"), CALL_TIMES),
        "source_page": _clean(form.get("source_page"), limit=200),
        "utm": _clean(form.get("utm"), limit=400),
    }
    if not lead["first_name"]:
        errors["first_name"] = "Please enter your first name."
    if len(lead["phone"]) != 10:
        errors["phone"] = "Please enter a 10-digit phone number."
    if not EMAIL_RE.match(lead["email"]):
        errors["email"] = "Please enter a valid email address."
    if len(lead["zip"]) != 5:
        errors["zip"] = "Please enter a 5-digit ZIP code."
    if lead["vehicle_year"] and not _re.fullmatch(r"(19|20)\d\d", lead["vehicle_year"]):
        lead["vehicle_year"] = ""
    if not services:
        errors["services"] = "Please choose at least one service."
    return lead, errors


def _fmt_phone(d):
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else d


def send_quote_email(lead):
    """Email the lead to the shop. Returns True only if Resend accepted it."""
    if not RESEND_API_KEY:
        app.logger.warning("RESEND_API_KEY not set — quote email skipped.")
        return False
    try:
        import html as _html
        import resend

        resend.api_key = RESEND_API_KEY
        esc = lambda v: _html.escape(str(v)) if v else "—"  # noqa: E731

        def row(label, value):
            return (
                "<tr><td style='padding:7px 14px;color:#8a8a8a;font-size:13px;"
                "border-bottom:1px solid #eee;white-space:nowrap;vertical-align:top;'>"
                f"{label}</td><td style='padding:7px 14px;color:#0a0a0a;font-size:14px;"
                f"border-bottom:1px solid #eee;font-weight:600;'>{esc(value)}</td></tr>"
            )

        def section(label):
            return (
                "<tr><td colspan='2' style='padding:12px 14px 6px;background:#f4f6f9;"
                "color:#1e3a5f;font-size:11px;font-weight:700;letter-spacing:.08em;"
                f"text-transform:uppercase;'>{label}</td></tr>"
            )

        vehicle = " ".join(
            v for v in (lead["vehicle_year"], lead["vehicle_make"], lead["vehicle_model"]) if v
        )
        miles = f" · ~{lead['miles']} mi" if lead.get("miles") is not None else ""
        body = (
            section("Contact")
            + row("Name", f"{lead['first_name']} {lead['last_name']}".strip())
            + row("Phone", _fmt_phone(lead["phone"]))
            + row("Email", lead["email"])
            + row("Prefers", lead["contact_method"])
            + row("Best time", lead["call_time"])
            + section("Vehicle & location")
            + row("Vehicle", vehicle)
            + row("Size", lead["vehicle_size"])
            + row("ZIP", f"{lead['zip']}{miles}")
            + row("Service area", AREA_LABELS[lead["area"]])
            + section("Services")
            + row("Requested", ", ".join(lead["services"]))
            + row("Ceramic package", lead["ceramic_package"])
            + row("Correction", lead["correction_type"])
            + row("Starting prices", " | ".join(lead["estimate"]))
            + section("Condition & timing")
            + row("Last detailed", lead["last_detailed"])
            + row("Condition", ", ".join(lead["condition"]))
            + row("Timing", lead["timing"])
            + row("Water & power", lead["utilities"])
            + row("Notes", lead["notes"])
            + section("Source")
            + row("Page", lead["source_page"])
            + row("Campaign", lead["utm"])
            + row("Submitted", lead["created"])
        )
        html = (
            "<div style='font-family:Arial,Helvetica,sans-serif;max-width:580px;margin:0 auto;'>"
            "<div style='background:#1e3a5f;padding:20px 24px;border-radius:6px 6px 0 0;'>"
            "<h1 style='color:#fff;font-size:20px;margin:0;'>New Quote Request</h1>"
            f"<p style='color:#9ab4d4;font-size:13px;margin:6px 0 0;'>{esc(lead['timing'] or 'Timing not given')}</p>"
            "</div><table style='width:100%;border-collapse:collapse;background:#fff;"
            f"border:1px solid #eee;border-top:none;'>{body}</table>"
            "<p style='color:#8a8a8a;font-size:12px;margin:14px 0 0;text-align:center;'>"
            "Starting prices are list prices by size — confirm on arrival.</p></div>"
        )
        subject = (
            f"New Quote — {lead['first_name']} {lead['last_name']}".strip()
            + f" · {', '.join(lead['services'])} · {lead['zip']}"
        )
        resend.Emails.send({
            "from": RESEND_FROM,
            "to": [SHOP_EMAIL],
            "subject": subject[:180],
            "html": html,
            "reply_to": lead["email"] or None,
        })
        return True
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Quote email failed: %s", exc)
        return False


def send_quote_to_sheet(lead):
    """Append the lead to Google Sheets via an Apps Script web app (optional)."""
    if not SHEETS_WEBHOOK_URL:
        return False
    payload = dict(lead)
    payload["phone"] = _fmt_phone(lead["phone"])
    for k in ("services", "condition", "estimate"):
        payload[k] = ", ".join(lead[k])
    payload["area"] = AREA_LABELS[lead["area"]]
    try:
        req = _urlreq.Request(
            SHEETS_WEBHOOK_URL,
            data=_json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with _urlreq.urlopen(req, timeout=8) as res:
            return 200 <= res.status < 400
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Quote sheet backup failed: %s", exc)
        return False


def delivery_configured():
    return bool(RESEND_API_KEY or SHEETS_WEBHOOK_URL)


@app.route("/api/quote", methods=["POST"])
def quote():
    form = request.form
    # Honeypot: real visitors never see or fill this field.
    if (form.get("website") or "").strip():
        return jsonify({"ok": True})

    lead, errors = parse_quote(form)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    lead["area"], lead["miles"] = area_for_zip(lead["zip"])
    lead["estimate"] = quote_estimate(
        lead["services"], lead["vehicle_size"], lead["ceramic_package"]
    )
    lead["created"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    emailed = send_quote_email(lead)
    sheeted = send_quote_to_sheet(lead)
    delivered = emailed or sheeted
    channels = ",".join(c for c, ok in (("email", emailed), ("sheet", sheeted)) if ok)

    conn = get_db()
    conn.execute(
        """INSERT INTO quotes (created, first_name, last_name, phone, email,
            vehicle_year, vehicle_make, vehicle_model, vehicle_size, zip, area, miles,
            services, ceramic_package, correction_type, last_detailed, condition,
            timing, utilities, notes, contact_method, call_time, source_page, utm,
            estimate, delivered)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            lead["created"], lead["first_name"], lead["last_name"], lead["phone"],
            lead["email"], lead["vehicle_year"], lead["vehicle_make"],
            lead["vehicle_model"], lead["vehicle_size"], lead["zip"], lead["area"],
            lead["miles"], ", ".join(lead["services"]), lead["ceramic_package"],
            lead["correction_type"], lead["last_detailed"], ", ".join(lead["condition"]),
            lead["timing"], lead["utilities"], lead["notes"], lead["contact_method"],
            lead["call_time"], lead["source_page"], lead["utm"],
            " | ".join(lead["estimate"]), channels or "none",
        ),
    )
    conn.commit()
    conn.close()

    # On Vercel with no channel configured — or every channel failing — the
    # lead would only exist in ephemeral /tmp. Say so, so the visitor calls.
    if not delivered and (os.environ.get("VERCEL") or delivery_configured()):
        return jsonify({"ok": False, "error": "delivery"}), 503

    return jsonify({"ok": True, "first_name": lead["first_name"]})


# ──────────────────────────────────────────────────────────────────────────
#  Routes — static frontend
# ──────────────────────────────────────────────────────────────────────────
# Clean URLs of every public page, in sitemap order. The booking backend and
# any future custom domain both hang off these, so keep this list in sync
# when a page is added.
# Town landing pages, one file per community we serve. Built by
# tools/build_area_pages.py — add a town there and to this tuple together.
AREA_PAGES = (
    "gates-mills",
    "hunting-valley",
    "pepper-pike",
    "moreland-hills",
    "chagrin-falls",
    "bentleyville",
)

# Static pages, as (canonical URL, file on disk), in sitemap order.
# The site is served at clean URLs; the .html form of each is registered as a
# permanent redirect so old links still land, but nothing on the site links to
# it and only the clean form is canonical.
PAGES = (
    ("/booking", "booking.html"),
    ("/rv-detailing", "rv-detailing.html"),
    ("/boat-detailing", "boat-detailing.html"),
    ("/gallery", "gallery.html"),
    ("/reviews", "reviews.html"),
    ("/faq", "faq.html"),
) + tuple((f"/{slug}", f"{slug}.html") for slug in AREA_PAGES)

# Templated (v3) pages: (canonical URL, template, extra context).
# Content lives in site_content.py; shared chrome in templates/base.html.
SERVICE_PAGE_SLUGS = tuple(
    s["slug"] for s in site_content.SERVICES if s["slug"] != "ceramic-coating"
)
TEMPLATE_PAGES = (
    ("/", "home.html", {}),
    ("/services", "services.html", {}),
    ("/ceramic-coating", "ceramic.html", {"service": "ceramic-coating"}),
) + tuple(
    (f"/{slug}", "service.html", {"service": slug}) for slug in SERVICE_PAGE_SLUGS
) + (
    ("/about", "about.html", {}),
    ("/contact", "contact.html", {}),
    ("/quote", "quote.html", {}),
    ("/privacy", "privacy.html", {}),
)

# Meta-ad landing pages: linkable, noindex, kept out of the sitemap.
LANDING_PAGES = tuple(
    (f"/lp/{slug}", "landing.html", {"lp": slug, "service": lp["service"]})
    for slug, lp in site_content.LANDING_PAGES.items()
)

# Old .html files the templates replaced; their URLs still redirect.
LEGACY_HTML = {"/index.html": "/", "/about.html": "/about",
               "/ceramic-coating.html": "/ceramic-coating"}

PUBLIC_PAGES = tuple(url for url, _, _ in TEMPLATE_PAGES) + tuple(url for url, _ in PAGES)

# ──────────────────────────────────────────────────────────────────────────
#  Canonical site URL
#  robots.txt and sitemap.xml are absolute-URL documents, so they must name
#  the production domain no matter which host served the request — otherwise
#  preview deployments publish a sitemap of their own URLs. Matches the
#  <link rel="canonical"> tags in the pages.
# ──────────────────────────────────────────────────────────────────────────
SITE_URL = "https://tonys-detailing.vercel.app"
CANONICAL_HOST = SITE_URL.split("://", 1)[1]


def is_canonical_host():
    """True when this request came in on the production domain."""
    return request.host.split(":", 1)[0] == CANONICAL_HOST


# Only these directories are served by the static catch-all. Everything else
# in the project root (app.py, tests, requirements, any local .env or
# bookings.db) must never be reachable over HTTP.
STATIC_DIRS = ("fonts", "assets", "static")


@app.route("/api/media")
def media_manifest():
    """Report which media slots are filled so the frontend can show only those."""
    return jsonify({name: media_present(name) for name in MEDIA_SLOTS})


def _serve_page(filename):
    """Serve one page file, through the hero renderer where that applies."""
    if filename in HERO_SLOTS:
        return render_page(filename)
    return send_from_directory(BASE_DIR, filename)


def _register_page(url, filename):
    """Register a page at its canonical URL, plus a 301 from the .html form.

    Both forms used to serve the page directly, which left every page
    reachable at two URLs — a split that search engines have to reconcile and
    that made internal links inconsistent. Only the clean URL serves content
    now; /<page>.html permanently redirects to it.
    """
    name = filename[: -len(".html")].replace("-", "_")

    def view(_filename=filename):
        return _serve_page(_filename)

    view.__name__ = f"page_{name}"
    app.add_url_rule(url, view_func=view)

    def redirect_view(_url=url):
        # Carry the query string across: /booking.html?plan=... is a link
        # that exists in the wild, and the booking form reads that param.
        query = request.query_string.decode()
        return redirect(f"{_url}?{query}" if query else _url, code=301)

    redirect_view.__name__ = f"page_{name}_html"
    app.add_url_rule(f"/{filename}", view_func=redirect_view)


for _url, _filename in PAGES:
    _register_page(_url, _filename)


# ── Templated pages ──
with open(os.path.join(BASE_DIR, "templates", "icons.json")) as _fh:
    ICONS = _json.load(_fh)


def icon(name, cls="ic"):
    """Inline Lucide SVG (paths extracted by tools/build_v3_assets.py)."""
    from markupsafe import Markup

    return Markup(
        f'<svg class="{cls}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{ICONS.get(name, "")}</svg>'
    )


def starts_at(svc):
    """'$120' style starting price for a service dict, or '' when quoted."""
    if svc.get("price_key"):
        return _money(min(BASE_PRICES[svc["price_key"]].values()))
    if svc.get("flat_price"):
        return _money(ADDON_PRICES[svc["flat_price"]])
    return ""


@app.context_processor
def _site_context():
    return {
        "c": site_content,
        "icon": icon,
        "money": _money,
        "starts_at": starts_at,
        "BASE_PRICES": BASE_PRICES,
        "ADDON_PRICES": ADDON_PRICES,
        "CLAY_PRICES": CLAY_PRICES,
        "TRAVEL_FEE": TRAVEL_FEE,
        "VEHICLE_TYPES": VEHICLE_TYPES,
        "QUOTE_SERVICE_SLUGS": QUOTE_SERVICE_SLUGS,
        "CERAMIC_PACKAGES": CERAMIC_PACKAGES,
        "CORRECTION_TYPES": CORRECTION_TYPES,
        "LAST_DETAILED": LAST_DETAILED,
        "CONDITIONS": CONDITIONS,
        "TIMINGS": TIMINGS,
        "UTILITIES": UTILITIES,
        "CONTACT_METHODS": CONTACT_METHODS,
        "CALL_TIMES": CALL_TIMES,
        "SITE_URL": SITE_URL,
        "AREA_PAGES": AREA_PAGES,
        "MAINTENANCE_SCOPE_NOTE": MAINTENANCE_SCOPE_NOTE,
        "year": datetime.now().year,
    }


def _register_template(url, template, ctx, noindex=False):
    def view(_t=template, _ctx=ctx, _url=url):
        svc = site_content.SERVICE_BY_SLUG.get(_ctx.get("service", ""))
        return render_template(
            _t,
            path=_url,
            svc=svc,
            noindex=noindex,
            hero_video=media_present("hero-loop.mp4"),
            hero_video_vertical=media_present("hero-loop-vertical.mp4"),
            **_ctx,
        )

    view.__name__ = "tpl_" + (url.strip("/").replace("/", "_").replace("-", "_") or "home")
    app.add_url_rule(url, view_func=view)


for _url, _tpl, _ctx in TEMPLATE_PAGES:
    _register_template(_url, _tpl, _ctx)
for _url, _tpl, _ctx in LANDING_PAGES:
    _register_template(_url, _tpl, _ctx, noindex=True)


def _legacy_redirect(_to):
    def view():
        query = request.query_string.decode()
        return redirect(f"{_to}?{query}" if query else _to, code=301)
    return view


for _old, _new in LEGACY_HTML.items():
    app.add_url_rule(_old, endpoint="legacy_" + _old.strip("/").replace(".", "_").replace("-", "_"),
                     view_func=_legacy_redirect(_new))


@app.route("/robots.txt")
def robots_txt():
    """Crawler policy.

    Built against the canonical domain, never the requested host. These used
    to be derived from request.url_root, which meant every Vercel preview
    deployment served a crawlable robots.txt advertising its own throwaway
    URL. Previews now tell crawlers to stay out entirely, so a preview can
    never compete with production in the index.
    """
    if is_canonical_host():
        body = (
            "User-agent: *\n"
            "Allow: /\n"
            "Disallow: /api/\n"
            f"Sitemap: {SITE_URL}/sitemap.xml\n"
        )
    else:
        body = "User-agent: *\nDisallow: /\n"
    return body, 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/sitemap.xml")
def sitemap_xml():
    # Always the canonical domain: a sitemap that lists preview URLs invites
    # them into the index and splits ranking signals with production.
    urls = "\n".join(
        f"  <url><loc>{SITE_URL + '/' if page == '/' else SITE_URL + page}</loc></url>"
        for page in PUBLIC_PAGES
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n"
        "</urlset>\n"
    )
    return body, 200, {"Content-Type": "application/xml; charset=utf-8"}


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(os.path.join(BASE_DIR, "assets"), "favicon.ico")


@app.route("/google4639bb4a2d8d894a.html")
def google_site_verification():
    return send_from_directory(BASE_DIR, "google4639bb4a2d8d894a.html")


@app.route("/<path:filename>", methods=["GET"])
def static_files(filename):
    """Serve site assets (fonts/, assets/, static/) — and nothing else.

    The project root also holds the app source, tests, and (locally) the
    bookings database and .env, so the resolved path must land inside one of
    the known static directories. realpath() also collapses any ../ tricks
    that would otherwise escape them.
    """
    full_path = os.path.realpath(os.path.join(BASE_DIR, filename))
    allowed = tuple(
        os.path.join(os.path.realpath(BASE_DIR), d) + os.sep for d in STATIC_DIRS
    )
    if not full_path.startswith(allowed):
        abort(404)
    if not os.path.isfile(full_path):
        abort(404)
    return send_file(full_path, conditional=True)


@app.errorhandler(404)
def page_not_found(_error):
    """Branded 404 for page requests; JSON for API paths."""
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Not found."}), 404
    return send_from_directory(BASE_DIR, "404.html"), 404


# ──────────────────────────────────────────────────────────────────────────
#  Response headers — caching + security
# ──────────────────────────────────────────────────────────────────────────
@app.after_request
def set_headers(response):
    path = request.path

    # Overwrite Flask's send_file default ("no-cache") with a policy per
    # path type; only error responses keep their own caching behavior.
    if response.status_code < 400:
        if path.startswith("/fonts/") or path.startswith("/assets/lucide-"):
            # Fonts and version-stamped bundles never change in place.
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path.startswith("/assets/") or path == "/favicon.ico":
            response.headers["Cache-Control"] = "public, max-age=604800, stale-while-revalidate=86400"
        elif path.startswith("/static/"):
            # Media slots are replaced in place (same filename), so keep
            # browser caching short enough for swaps to show up same-day.
            response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
        elif path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        else:
            response.headers["Cache-Control"] = "no-cache"

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# Initialize the database on import (covers both local + serverless cold starts).
init_db()
init_quotes_table()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
