"""
Backtest suite for the Tony's Detailing booking backend.

Exercises the pricing/estimate engine and discount rules across a matrix of
scenarios, plus the /api/book endpoint, loyalty tracking, input validation,
and static file serving.

Run with:  pytest -v
"""

import os
import tempfile

import pytest

# Point the app at a throwaway DB and ensure no real emails are sent before
# the module is imported (DB_PATH + RESEND_API_KEY are read at import time).
_TMP_DB = os.path.join(tempfile.mkdtemp(), "test_bookings.db")
os.environ["DATABASE_PATH"] = _TMP_DB
os.environ.pop("RESEND_API_KEY", None)

import app as appmod  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    """Start every test with an empty bookings table."""
    if os.path.exists(_TMP_DB):
        os.remove(_TMP_DB)
    appmod.init_db()
    yield


@pytest.fixture
def client():
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


# ──────────────────────────────────────────────────────────────────────────
#  parse_num_vehicles
# ──────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "raw,expected",
    [("1", 1), ("2", 2), ("3+", 3), ("", 1), ("abc", 1), (None, 1), ("0", 1)],
)
def test_parse_num_vehicles(raw, expected):
    assert appmod.parse_num_vehicles(raw) == expected


# ──────────────────────────────────────────────────────────────────────────
#  Base pricing matrix — every service × vehicle type
# ──────────────────────────────────────────────────────────────────────────
def test_base_price_matrix():
    for service, by_vehicle in appmod.BASE_PRICES.items():
        for vehicle, price in by_vehicle.items():
            total, summary = appmod.calculate_estimate(
                service, vehicle, [], [], "1", ""
            )
            assert total == price, f"{service}/{vehicle} expected {price}, got {total}"
            assert summary == "None"


# ──────────────────────────────────────────────────────────────────────────
#  Add-ons
# ──────────────────────────────────────────────────────────────────────────
def test_leather_addon_flat():
    total, _ = appmod.calculate_estimate("Full Detail", "Sedan", ["Leather Conditioning"], [], "1", "")
    assert total == 150 + 40


def test_clay_addon_scales_with_vehicle():
    expected = {"Sedan": 40, "SUV/Crossover": 50, "Large SUV/Truck": 60, "Minivan": 50}
    for vehicle, clay in expected.items():
        base = appmod.BASE_PRICES["Exterior Detail"][vehicle]
        total, _ = appmod.calculate_estimate("Exterior Detail", vehicle, ["Clay Decontamination"], [], "1", "")
        assert total == base + clay, f"{vehicle}: expected {base + clay}, got {total}"


def test_odor_addon_flat():
    total, _ = appmod.calculate_estimate("Interior Detail", "Sedan", ["Odor Eliminator"], [], "1", "")
    assert total == 95 + 50


def test_all_addons_stack():
    # Sedan Full Detail 150 + leather 40 + clay 40 + odor 50 = 280
    total, _ = appmod.calculate_estimate(
        "Full Detail", "Sedan",
        ["Leather Conditioning", "Clay Decontamination", "Odor Eliminator"], [], "1", "",
    )
    assert total == 280


# ──────────────────────────────────────────────────────────────────────────
#  Condition upcharges
# ──────────────────────────────────────────────────────────────────────────
def test_upcharges_sum():
    # Sedan Interior 95 + pet hair 30 + heavy staining 30 + smoke 40 + debris 25 = 220
    total, _ = appmod.calculate_estimate(
        "Interior Detail", "Sedan", [],
        ["Pet Hair", "Heavy Staining", "Smoke/Odor", "Excessive Debris"], "1", "",
    )
    assert total == 220


# ──────────────────────────────────────────────────────────────────────────
#  Discounts
# ──────────────────────────────────────────────────────────────────────────
def test_multi_vehicle_discount():
    # SUV Full Detail 160 x 2 = 320, less 10% = 288
    total, summary = appmod.calculate_estimate("Full Detail", "SUV/Crossover", [], [], "2", "")
    assert total == 288.0
    assert "Multi-vehicle 10%" in summary
    assert "Referral" not in summary


def test_referral_requires_full_detail_minimum():
    # Exterior + Interior should NOT get the referral discount even if referred
    for service in ("Exterior Detail", "Interior Detail"):
        total, summary = appmod.calculate_estimate(service, "Sedan", [], [], "1", "A Friend")
        assert "Referral" not in summary
        assert total == appmod.BASE_PRICES[service]["Sedan"]


def test_referral_applies_to_full_and_deep():
    # Full Detail Sedan 150 - 35 = 115
    total, summary = appmod.calculate_estimate("Full Detail", "Sedan", [], [], "1", "A Friend")
    assert total == 115
    assert "Referral (-$35.00)" in summary
    # Deep Clean Sedan 230 - 35 = 195
    total2, summary2 = appmod.calculate_estimate("Deep Clean", "Sedan", [], [], "1", "A Friend")
    assert total2 == 195
    assert "Referral" in summary2


def test_referral_ignored_when_blank():
    total, summary = appmod.calculate_estimate("Full Detail", "Sedan", [], [], "1", "   ")
    assert total == 150
    assert summary == "None"


def test_discounts_stack():
    # SUV Full Detail 160 x 2 = 320, + leather 40 + clay 50 + pet hair 30 = 440
    # multi 10% = 44, referral 35 => 79 off => 361
    total, summary = appmod.calculate_estimate(
        "Full Detail", "SUV/Crossover",
        ["Leather Conditioning", "Clay Decontamination"], ["Pet Hair"], "2", "Bob Smith",
    )
    assert total == 361.0
    assert "Multi-vehicle 10% (-$44.00)" in summary
    assert "Referral (-$35.00)" in summary
    assert "Total saved: $79.00" in summary


def test_total_never_negative():
    # Tiny base, large referral can't push below zero (defensive)
    total, _ = appmod.calculate_estimate("Full Detail", "Sedan", [], [], "1", "Ref")
    assert total >= 0


# ──────────────────────────────────────────────────────────────────────────
#  /api/book endpoint
# ──────────────────────────────────────────────────────────────────────────
def test_book_endpoint_success(client):
    res = client.post("/api/book", data={
        "name": "Jane Doe", "phone": "4405550192", "email": "jane@example.com",
        "vehicle_type": "SUV/Crossover", "num_vehicles": "2", "service": "Full Detail",
        "addons": ["Leather Conditioning", "Clay Decontamination"],
        "upcharges": ["Pet Hair"], "referred_by": "Bob Smith", "notes": "garage parked",
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["total_estimate"] == 361.0
    assert "Referral" in data["discount_applied"]
    assert data["visits"] == 1


def test_book_endpoint_persists_row(client):
    client.post("/api/book", data={
        "name": "Carl", "phone": "2165551234", "service": "Deep Clean",
        "vehicle_type": "Minivan", "num_vehicles": "1",
        "addons": ["Odor Eliminator"], "upcharges": ["Smoke/Odor"],
    })
    conn = appmod.get_db()
    row = conn.execute("SELECT * FROM bookings WHERE name = 'Carl'").fetchone()
    conn.close()
    assert row is not None
    assert row["service"] == "Deep Clean"
    assert row["addons"] == "Odor Eliminator"
    assert row["upcharges"] == "Smoke/Odor"
    # Minivan Deep Clean 260 + odor 50 + smoke 40 = 350
    assert row["total_estimate"] == 350.0
    assert row["timestamp"]


@pytest.mark.parametrize("payload", [
    {"phone": "4405550192"},                 # missing name
    {"name": "No Phone"},                    # missing phone
    {},                                      # missing both
])
def test_book_endpoint_validation(client, payload):
    res = client.post("/api/book", data=payload)
    assert res.status_code == 400
    assert res.get_json()["ok"] is False


def test_loyalty_visits_increment(client):
    for expected in (1, 2, 3):
        res = client.post("/api/book", data={
            "name": "Repeat Customer", "phone": "4400000000",
            "email": "Loyal@Example.com", "service": "Exterior Detail",
            "vehicle_type": "Sedan", "num_vehicles": "1",
        })
        assert res.get_json()["visits"] == expected


def test_loyalty_email_case_insensitive(client):
    client.post("/api/book", data={"name": "A", "phone": "1", "email": "x@y.com", "service": "Exterior Detail", "vehicle_type": "Sedan"})
    res = client.post("/api/book", data={"name": "A", "phone": "1", "email": "X@Y.COM", "service": "Exterior Detail", "vehicle_type": "Sedan"})
    assert res.get_json()["visits"] == 2


# ──────────────────────────────────────────────────────────────────────────
#  Static frontend
# ──────────────────────────────────────────────────────────────────────────
def test_home_serves_index(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Tony's Detailing" in res.data


def test_booking_page_serves(client):
    assert client.get("/booking").status_code == 200
    assert client.get("/booking.html").status_code == 200


def test_static_assets_serve(client):
    assert client.get("/fonts/Inter-Regular.ttf").status_code == 200
    assert client.get("/assets/logo.png").status_code == 200


def test_unknown_path_404(client):
    assert client.get("/does-not-exist.xyz").status_code == 404
