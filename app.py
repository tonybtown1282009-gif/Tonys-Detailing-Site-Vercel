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
    "Exterior Detail": {"Sedan": 65, "SUV/Crossover": 75, "Large SUV/Truck": 95, "Minivan": 85},
    "Interior Detail": {"Sedan": 95, "SUV/Crossover": 105, "Large SUV/Truck": 125, "Minivan": 115},
    "Full Detail": {"Sedan": 150, "SUV/Crossover": 160, "Large SUV/Truck": 185, "Minivan": 170},
    "Deep Clean": {"Sedan": 230, "SUV/Crossover": 250, "Large SUV/Truck": 275, "Minivan": 260},
}

# Add-on pricing. Clay Decontamination scales with vehicle size.
CLAY_PRICES = {"Sedan": 40, "SUV/Crossover": 50, "Large SUV/Truck": 60, "Minivan": 50}
ADDON_PRICES = {
    "Leather Conditioning": 40,
    "Odor Eliminator": 50,  # mid-point of the advertised $40–$75 range
    # "Clay Decontamination" handled separately (size dependent)
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

app = Flask(__name__, static_folder=None)


# ──────────────────────────────────────────────────────────────────────────
#  Database
# ──────────────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the bookings table if it doesn't exist."""
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT    NOT NULL,
            phone            TEXT    NOT NULL,
            email            TEXT,
            vehicle_type     TEXT,
            service          TEXT,
            addons           TEXT,
            upcharges        TEXT,
            num_vehicles     TEXT,
            referred_by      TEXT,
            discount_applied TEXT,
            total_estimate   REAL,
            visits           INTEGER DEFAULT 1,
            timestamp        TEXT
        )
        """
    )
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


def calculate_estimate(service, vehicle_type, addons, upcharges, num_vehicles, referred_by):
    """
    Returns (total_estimate, discount_summary).

    Pricing: base (by service + vehicle) × number of vehicles, plus selected
    add-ons and condition upcharges. Discounts: 10% for 2+ vehicles and a flat
    $35 referral credit (Full Detail minimum). Both can stack.
    """
    vehicle = vehicle_type if vehicle_type in VEHICLE_TYPES else "Sedan"
    base = BASE_PRICES.get(service, {}).get(vehicle, 0)

    addon_total = 0
    for addon in addons:
        if addon == "Clay Decontamination":
            addon_total += CLAY_PRICES.get(vehicle, 50)
        else:
            addon_total += ADDON_PRICES.get(addon, 0)

    upcharge_total = sum(UPCHARGE_PRICES.get(u, 0) for u in upcharges)

    count = parse_num_vehicles(num_vehicles)
    subtotal = (base * count) + addon_total + upcharge_total

    # ── Discounts ──
    discount_total = 0.0
    notes = []

    if count >= 2:
        multi = round(subtotal * MULTI_VEHICLE_RATE, 2)
        discount_total += multi
        notes.append(f"Multi-vehicle 10% (-${multi:.2f})")

    if (referred_by or "").strip() and service in REFERRAL_ELIGIBLE_SERVICES:
        discount_total += REFERRAL_DISCOUNT
        notes.append(f"Referral (-${REFERRAL_DISCOUNT:.2f})")

    total = max(0.0, round(subtotal - discount_total, 2))

    if notes:
        discount_summary = "; ".join(notes) + f" | Total saved: ${discount_total:.2f}"
    else:
        discount_summary = "None"

    return total, discount_summary


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
            {row("Vehicle Type", booking["vehicle_type"])}
            {row("# Vehicles", booking["num_vehicles"])}
            {row("Service", booking["service"])}
            {row("Add-ons", booking["addons"])}
            {row("Condition Upcharges", booking["upcharges"])}
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

    if not name or not phone:
        return jsonify({"ok": False, "error": "Name and phone are required."}), 400

    email = (form.get("email") or "").strip()
    vehicle_type = (form.get("vehicle_type") or "").strip()
    service = (form.get("service") or "").strip()
    num_vehicles = (form.get("num_vehicles") or "1").strip()
    referred_by = (form.get("referred_by") or "").strip()
    notes = (form.get("notes") or "").strip()

    addons = [a.strip() for a in form.getlist("addons") if a.strip()]
    upcharges = [u.strip() for u in form.getlist("upcharges") if u.strip()]

    total_estimate, discount_applied = calculate_estimate(
        service, vehicle_type, addons, upcharges, num_vehicles, referred_by
    )

    conn = get_db()
    visits = record_visit_count(conn, email)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn.execute(
        """
        INSERT INTO bookings (
            name, phone, email, vehicle_type, service, addons, upcharges,
            num_vehicles, referred_by, discount_applied, total_estimate,
            visits, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name, phone, email, vehicle_type, service,
            ", ".join(addons), ", ".join(upcharges), num_vehicles,
            referred_by, discount_applied, total_estimate, visits, timestamp,
        ),
    )
    conn.commit()
    conn.close()

    booking = {
        "name": name, "phone": phone, "email": email, "vehicle_type": vehicle_type,
        "service": service, "addons": ", ".join(addons), "upcharges": ", ".join(upcharges),
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
@app.route("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/booking")
@app.route("/booking.html")
def booking_page():
    return send_from_directory(BASE_DIR, "booking.html")


@app.route("/<path:filename>", methods=["GET"])
def static_files(filename):
    """Serve any existing file from the project root (fonts, assets, images)."""
    full_path = os.path.join(BASE_DIR, filename)
    if os.path.isfile(full_path):
        return send_from_directory(BASE_DIR, filename)
    abort(404)


# Initialize the database on import (covers both local + serverless cold starts).
init_db()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
