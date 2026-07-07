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
    request,
    send_file,
    send_from_directory,
)

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
    "hero-video.mp4",
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
    "Exterior Detail": {"Sedan": 75, "SUV/Crossover": 90, "Large SUV/Truck": 110, "Minivan": 100},
    "Interior Detail": {"Sedan": 120, "SUV/Crossover": 135, "Large SUV/Truck": 155, "Minivan": 145},
    "Full Detail": {"Sedan": 195, "SUV/Crossover": 215, "Large SUV/Truck": 240, "Minivan": 225},
    "Deep Clean": {"Sedan": 280, "SUV/Crossover": 300, "Large SUV/Truck": 330, "Minivan": 315},
}

# Add-on pricing. Clay & Iron Decontamination scales with vehicle size.
CLAY_PRICES = {"Sedan": 40, "SUV/Crossover": 50, "Large SUV/Truck": 60, "Minivan": 50}
ADDON_PRICES = {
    "Leather Conditioning": 40,
    "Odor Eliminator": 50,  # mid-point of the advertised $40–$75 range
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
REFERRAL_ELIGIBLE_SERVICES = {"Full Detail", "Deep Clean"}
REFERRAL_DISCOUNT = 35
MULTI_VEHICLE_RATE = 0.10  # 10% off for 2+ vehicles

# Expecting / new-parent courtesy: $50 off a Deep Clean, per qualifying vehicle.
DEEP_CLEAN_SERVICE = "Deep Clean"
EXPECTING_DISCOUNT = 50

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
        "expecting_discount_1": "INTEGER DEFAULT 0",
        "expecting_discount_2": "INTEGER DEFAULT 0",
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
    base = BASE_PRICES.get(service, {}).get(vehicle, 0)

    addon_total = 0
    for addon in addons:
        if addon == "Clay & Iron Decontamination":
            addon_total += CLAY_PRICES.get(vehicle, 50)
        else:
            addon_total += ADDON_PRICES.get(addon, 0)

    upcharge_total = sum(UPCHARGE_PRICES.get(u, 0) for u in upcharges)
    return base + addon_total + upcharge_total


def calculate_estimate(
    num_vehicles, referred_by, vehicle1, vehicle2=None,
    expecting1=False, expecting2=False,
):
    """
    Returns (total_estimate, discount_summary).

    Each vehicle (a dict of service/vehicle_type/addons/upcharges) is priced on
    its own. Vehicle 1 is always counted; when 2+ vehicles are booked, vehicle 2
    is priced and applied to each additional vehicle (so "3+" charges vehicle 2
    twice — additional vehicles are estimated at the same rate).

    Discounts: 10% for 2+ vehicles, a flat $35 referral credit (the order must
    include at least a Full Detail to qualify), and a $50 expecting/new-parent
    courtesy per Deep Clean vehicle where the customer checked the box. All can
    stack. The referral and expecting credits are applied as flat amounts after
    the multi-vehicle percentage.
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

    # Expecting / new-parent courtesy — only on Deep Clean vehicles.
    expecting_total = 0.0
    if expecting1 and vehicle1.get("service") == DEEP_CLEAN_SERVICE:
        expecting_total += EXPECTING_DISCOUNT
    if (
        count >= 2 and expecting2 and vehicle2
        and vehicle2.get("service") == DEEP_CLEAN_SERVICE
    ):
        expecting_total += EXPECTING_DISCOUNT * (count - 1)
    if expecting_total:
        discount_total += expecting_total
        notes.append(f"Expecting/new parent (-${expecting_total:.2f})")

    total = max(0.0, round(subtotal - discount_total, 2))

    if notes:
        discount_summary = "; ".join(notes) + f" | Total saved: ${discount_total:.2f}"
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

        vehicle1_expecting = ""
        if booking.get("expecting_discount_1"):
            vehicle1_expecting = row("Expecting / New Parent", "Yes — $50 off Deep Clean")

        vehicle2_rows = ""
        if any(
            booking.get(k)
            for k in ("vehicle_type_2", "service_2", "addons_2", "upcharges_2")
        ):
            vehicle2_rows = (
                section("Second Vehicle")
                + row("Vehicle Type", booking.get("vehicle_type_2"))
                + row("Service", booking.get("service_2"))
                + row("Add-ons", booking.get("addons_2"))
                + row("Condition Upcharges", booking.get("upcharges_2"))
                + (
                    row("Expecting / New Parent", "Yes — $50 off Deep Clean")
                    if booking.get("expecting_discount_2") else ""
                )
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
            {row("# Vehicles", booking["num_vehicles"])}
            {section("Vehicle 1")}
            {row("Vehicle Type", booking["vehicle_type"])}
            {row("Service", booking["service"])}
            {row("Add-ons", booking["addons"])}
            {row("Condition Upcharges", booking["upcharges"])}
            {vehicle1_expecting}
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
    expecting_1 = checkbox("expecting_discount_1")

    # Vehicle 2 (only meaningful when 2+ vehicles are booked)
    vehicle_type_2 = (form.get("vehicle_type_2") or "").strip()
    service_2 = (form.get("service_2") or "").strip()
    addons_2 = [a.strip() for a in form.getlist("addons_2") if a.strip()]
    upcharges_2 = [u.strip() for u in form.getlist("upcharges_2") if u.strip()]
    expecting_2 = checkbox("expecting_discount_2")

    has_second = parse_num_vehicles(num_vehicles) >= 2
    if not has_second:
        vehicle_type_2, service_2, addons_2, upcharges_2 = "", "", [], []
        expecting_2 = False
    elif not service_2:
        # Without a service the second vehicle can't be priced, so the 10%
        # multi-vehicle discount would apply to a single car's total.
        return jsonify(
            {"ok": False, "error": "Please select a service for your second vehicle."}
        ), 400

    # The expecting discount only applies to Deep Clean vehicles.
    expecting_1 = expecting_1 and service == DEEP_CLEAN_SERVICE
    expecting_2 = expecting_2 and service_2 == DEEP_CLEAN_SERVICE

    v1 = {"service": service, "vehicle_type": vehicle_type, "addons": addons, "upcharges": upcharges}
    v2 = {"service": service_2, "vehicle_type": vehicle_type_2, "addons": addons_2, "upcharges": upcharges_2}

    total_estimate, discount_applied = calculate_estimate(
        num_vehicles, referred_by, v1, v2,
        expecting1=expecting_1, expecting2=expecting_2,
    )

    conn = get_db()
    visits = record_visit_count(conn, email)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn.execute(
        """
        INSERT INTO bookings (
            name, phone, email, location, vehicle_type, service, addons, upcharges,
            vehicle_type_2, service_2, addons_2, upcharges_2,
            expecting_discount_1, expecting_discount_2,
            num_vehicles, referred_by, discount_applied, total_estimate,
            visits, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name, phone, email, location, vehicle_type, service,
            ", ".join(addons), ", ".join(upcharges),
            vehicle_type_2, service_2, ", ".join(addons_2), ", ".join(upcharges_2),
            int(expecting_1), int(expecting_2),
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
        "expecting_discount_1": expecting_1, "expecting_discount_2": expecting_2,
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
#  Routes — static frontend
# ──────────────────────────────────────────────────────────────────────────
# Clean URLs of every public page, in sitemap order. The booking backend and
# any future custom domain both hang off these, so keep this list in sync
# when a page is added.
PUBLIC_PAGES = (
    "/",
    "/booking",
    "/deep-clean",
    "/rv-detailing",
    "/boat-detailing",
    "/about",
    "/gallery",
    "/reviews",
    "/faq",
)

# Only these directories are served by the static catch-all. Everything else
# in the project root (app.py, tests, requirements, any local .env or
# bookings.db) must never be reachable over HTTP.
STATIC_DIRS = ("fonts", "assets", "static")


@app.route("/")
@app.route("/index.html")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/booking")
@app.route("/booking.html")
def booking_page():
    return send_from_directory(BASE_DIR, "booking.html")


@app.route("/deep-clean")
@app.route("/deep-clean.html")
def deep_clean_page():
    return send_from_directory(BASE_DIR, "deep-clean.html")


@app.route("/api/media")
def media_manifest():
    """Report which media slots are filled so the frontend can show only those."""
    return jsonify({name: media_present(name) for name in MEDIA_SLOTS})


@app.route("/rv-detailing")
@app.route("/rv-detailing.html")
def rv_detailing_page():
    return send_from_directory(BASE_DIR, "rv-detailing.html")


@app.route("/boat-detailing")
@app.route("/boat-detailing.html")
def boat_detailing_page():
    return send_from_directory(BASE_DIR, "boat-detailing.html")


@app.route("/about")
@app.route("/about.html")
def about_page():
    return send_from_directory(BASE_DIR, "about.html")


@app.route("/gallery")
@app.route("/gallery.html")
def gallery_page():
    return send_from_directory(BASE_DIR, "gallery.html")


@app.route("/reviews")
@app.route("/reviews.html")
def reviews_page():
    return send_from_directory(BASE_DIR, "reviews.html")


@app.route("/faq")
@app.route("/faq.html")
def faq_page():
    return send_from_directory(BASE_DIR, "faq.html")


@app.route("/robots.txt")
def robots_txt():
    """Crawler policy, built against whatever host the site is served from."""
    base = request.url_root.rstrip("/")
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    return body, 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/sitemap.xml")
def sitemap_xml():
    base = request.url_root.rstrip("/")
    urls = "\n".join(
        f"  <url><loc>{base + '/' if page == '/' else base + page}</loc></url>"
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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
