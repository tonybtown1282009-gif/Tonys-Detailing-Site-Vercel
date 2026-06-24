"""
Backtest suite for the Tony's Detailing booking backend.

Exercises the per-vehicle pricing engine, two-vehicle estimates, discount
rules, the /api/book endpoint (location + second vehicle), loyalty tracking,
input validation, and static file serving.

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


def veh(service="", vehicle_type="", addons=None, upcharges=None):
    return {
        "service": service,
        "vehicle_type": vehicle_type,
        "addons": addons or [],
        "upcharges": upcharges or [],
    }


@pytest.fixture(autouse=True)
def fresh_db():
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
#  vehicle_cost — base matrix + add-ons + upcharges
# ──────────────────────────────────────────────────────────────────────────
def test_base_price_matrix():
    expected = {
        "Exterior Detail": {"Sedan": 75, "SUV/Crossover": 90, "Large SUV/Truck": 110, "Minivan": 100},
        "Interior Detail": {"Sedan": 120, "SUV/Crossover": 135, "Large SUV/Truck": 155, "Minivan": 145},
        "Full Detail": {"Sedan": 195, "SUV/Crossover": 215, "Large SUV/Truck": 240, "Minivan": 225},
        "Deep Clean": {"Sedan": 280, "SUV/Crossover": 300, "Large SUV/Truck": 330, "Minivan": 315},
    }
    assert appmod.BASE_PRICES == expected
    for service, by_vehicle in expected.items():
        for vehicle, price in by_vehicle.items():
            assert appmod.vehicle_cost(service, vehicle, [], []) == price


def test_leather_addon_flat():
    assert appmod.vehicle_cost("Full Detail", "Sedan", ["Leather Conditioning"], []) == 195 + 40


def test_clay_iron_addon_scales_with_vehicle():
    expected = {"Sedan": 40, "SUV/Crossover": 50, "Large SUV/Truck": 60, "Minivan": 50}
    for vehicle, clay in expected.items():
        base = appmod.BASE_PRICES["Exterior Detail"][vehicle]
        cost = appmod.vehicle_cost("Exterior Detail", vehicle, ["Clay & Iron Decontamination"], [])
        assert cost == base + clay, f"{vehicle}: expected {base + clay}, got {cost}"


def test_odor_addon_flat():
    assert appmod.vehicle_cost("Interior Detail", "Sedan", ["Odor Eliminator"], []) == 120 + 50


def test_all_addons_stack():
    # Sedan Full 195 + leather 40 + clay 40 + odor 50 = 325
    cost = appmod.vehicle_cost(
        "Full Detail", "Sedan",
        ["Leather Conditioning", "Clay & Iron Decontamination", "Odor Eliminator"], [],
    )
    assert cost == 325


def test_upcharges_sum():
    # Sedan Interior 120 + 30 + 30 + 40 + 25 = 245
    cost = appmod.vehicle_cost(
        "Interior Detail", "Sedan", [],
        ["Pet Hair", "Heavy Staining", "Smoke/Odor", "Excessive Debris"],
    )
    assert cost == 245


# ──────────────────────────────────────────────────────────────────────────
#  calculate_estimate — single vehicle
# ──────────────────────────────────────────────────────────────────────────
def test_single_vehicle_no_discount():
    total, summary = appmod.calculate_estimate("1", "", veh("Full Detail", "Sedan"))
    assert total == 195
    assert summary == "None"


def test_referral_requires_full_detail_minimum():
    for service in ("Exterior Detail", "Interior Detail"):
        total, summary = appmod.calculate_estimate("1", "A Friend", veh(service, "Sedan"))
        assert "Referral" not in summary
        assert total == appmod.BASE_PRICES[service]["Sedan"]


def test_referral_applies_to_full_and_deep():
    total, summary = appmod.calculate_estimate("1", "A Friend", veh("Full Detail", "Sedan"))
    assert total == 160  # 195 - 35
    assert "Referral (-$35.00)" in summary
    total2, summary2 = appmod.calculate_estimate("1", "A Friend", veh("Deep Clean", "Sedan"))
    assert total2 == 245  # 280 - 35
    assert "Referral" in summary2


def test_referral_ignored_when_blank():
    total, summary = appmod.calculate_estimate("1", "   ", veh("Full Detail", "Sedan"))
    assert total == 195
    assert summary == "None"


# ──────────────────────────────────────────────────────────────────────────
#  calculate_estimate — two vehicles
# ──────────────────────────────────────────────────────────────────────────
def test_two_vehicles_multi_discount():
    # v1 Full SUV 215 + v2 Full SUV 215 = 430, less 10% = 387
    total, summary = appmod.calculate_estimate(
        "2", "", veh("Full Detail", "SUV/Crossover"), veh("Full Detail", "SUV/Crossover")
    )
    assert total == 387.0
    assert "Multi-vehicle 10%" in summary
    assert "Referral" not in summary


def test_three_plus_prices_second_vehicle_twice():
    # v1 Full SUV 215 + v2 Exterior Sedan 75 x 2 = 365, less 10% = 328.5
    total, summary = appmod.calculate_estimate(
        "3+", "", veh("Full Detail", "SUV/Crossover"), veh("Exterior Detail", "Sedan")
    )
    assert total == 328.5
    assert "Multi-vehicle 10%" in summary


def test_referral_eligible_via_second_vehicle():
    # v1 Exterior Sedan 75 (not eligible) + v2 Full Sedan 195 (eligible) = 270
    # multi 27, referral 35 => 270 - 62 = 208
    total, summary = appmod.calculate_estimate(
        "2", "Bob", veh("Exterior Detail", "Sedan"), veh("Full Detail", "Sedan")
    )
    assert total == 208.0
    assert "Multi-vehicle 10% (-$27.00)" in summary
    assert "Referral (-$35.00)" in summary


def test_full_stack_two_vehicles_with_addons():
    # v1 Full SUV 215 + leather 40 + clay(SUV) 50 = 305
    # v2 Interior Sedan 120 + pet hair 30 = 150
    # subtotal 455, multi 45.5, referral 35 => 374.5
    total, summary = appmod.calculate_estimate(
        "2", "Bob",
        veh("Full Detail", "SUV/Crossover", ["Leather Conditioning", "Clay & Iron Decontamination"]),
        veh("Interior Detail", "Sedan", [], ["Pet Hair"]),
    )
    assert total == 374.5
    assert "Multi-vehicle 10% (-$45.50)" in summary
    assert "Referral (-$35.00)" in summary
    assert "Total saved: $80.50" in summary


def test_second_vehicle_ignored_when_count_one():
    # num=1 should ignore the v2 dict entirely
    total, summary = appmod.calculate_estimate(
        "1", "", veh("Exterior Detail", "Sedan"), veh("Deep Clean", "Large SUV/Truck")
    )
    assert total == 75
    assert summary == "None"


# ──────────────────────────────────────────────────────────────────────────
#  calculate_estimate — expecting / new-parent $50 Deep Clean discount
# ──────────────────────────────────────────────────────────────────────────
def test_expecting_discount_on_deep_clean():
    # Deep Clean Sedan 280 - 50 = 230
    total, summary = appmod.calculate_estimate(
        "1", "", veh("Deep Clean", "Sedan"), expecting1=True
    )
    assert total == 230
    assert "Expecting/new parent (-$50.00)" in summary


def test_expecting_discount_ignored_for_non_deep_clean():
    # Checkbox set but service is Full Detail -> no discount
    total, summary = appmod.calculate_estimate(
        "1", "", veh("Full Detail", "Sedan"), expecting1=True
    )
    assert total == 195
    assert "Expecting" not in summary


def test_expecting_discount_defaults_off():
    total, summary = appmod.calculate_estimate("1", "", veh("Deep Clean", "Sedan"))
    assert total == 280
    assert summary == "None"


def test_expecting_discount_via_second_vehicle():
    # v1 Full Sedan 195 + v2 Deep Clean Sedan 280 = 475
    # multi 10% = 47.5; expecting on v2 = 50 => 475 - 47.5 - 50 = 377.5
    total, summary = appmod.calculate_estimate(
        "2", "", veh("Full Detail", "Sedan"), veh("Deep Clean", "Sedan"),
        expecting2=True,
    )
    assert total == 377.5
    assert "Expecting/new parent (-$50.00)" in summary
    assert "Multi-vehicle 10%" in summary


def test_expecting_discount_scales_for_three_plus():
    # v1 Deep Clean Sedan 280 + v2 Deep Clean Sedan 280 x2 = 840
    # multi 10% = 84; expecting v1 50 + v2 50x2 = 150 => 840 - 84 - 150 = 606
    total, summary = appmod.calculate_estimate(
        "3+", "", veh("Deep Clean", "Sedan"), veh("Deep Clean", "Sedan"),
        expecting1=True, expecting2=True,
    )
    assert total == 606.0
    assert "Expecting/new parent (-$150.00)" in summary


def test_expecting_and_referral_stack():
    # Deep Clean Sedan 280, referral 35 + expecting 50 => 195
    total, summary = appmod.calculate_estimate(
        "1", "A Friend", veh("Deep Clean", "Sedan"), expecting1=True
    )
    assert total == 195
    assert "Referral (-$35.00)" in summary
    assert "Expecting/new parent (-$50.00)" in summary


# ──────────────────────────────────────────────────────────────────────────
#  /api/book endpoint
# ──────────────────────────────────────────────────────────────────────────
def test_book_endpoint_success_two_vehicles(client):
    res = client.post("/api/book", data={
        "name": "Jane Doe", "phone": "4405550192", "email": "jane@example.com",
        "location": "Chardon, OH", "num_vehicles": "2", "referred_by": "Bob",
        "vehicle_type": "SUV/Crossover", "service": "Full Detail",
        "addons": ["Leather Conditioning", "Clay & Iron Decontamination"],
        "vehicle_type_2": "Sedan", "service_2": "Interior Detail",
        "upcharges_2": ["Pet Hair"],
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["total_estimate"] == 374.5
    assert "Referral" in data["discount_applied"]


def test_book_endpoint_persists_second_vehicle(client):
    client.post("/api/book", data={
        "name": "Carl", "phone": "2165551234", "location": "Munson",
        "num_vehicles": "2", "vehicle_type": "Sedan", "service": "Full Detail",
        "vehicle_type_2": "Minivan", "service_2": "Deep Clean",
        "addons_2": ["Odor Eliminator"], "upcharges_2": ["Smoke/Odor"],
    })
    conn = appmod.get_db()
    row = conn.execute("SELECT * FROM bookings WHERE name = 'Carl'").fetchone()
    conn.close()
    assert row["location"] == "Munson"
    assert row["vehicle_type_2"] == "Minivan"
    assert row["service_2"] == "Deep Clean"
    assert row["addons_2"] == "Odor Eliminator"
    assert row["upcharges_2"] == "Smoke/Odor"
    # v1 Full Sedan 195 + v2 Deep Clean Minivan (315 + odor 50 + smoke 40 = 405)
    # subtotal 600, multi 10% 60 => 540
    assert row["total_estimate"] == 540.0


def test_book_endpoint_clears_v2_when_single(client):
    client.post("/api/book", data={
        "name": "Solo", "phone": "111", "location": "Chardon",
        "num_vehicles": "1", "vehicle_type": "Sedan", "service": "Exterior Detail",
        "vehicle_type_2": "Minivan", "service_2": "Deep Clean",  # should be dropped
    })
    conn = appmod.get_db()
    row = conn.execute("SELECT * FROM bookings WHERE name = 'Solo'").fetchone()
    conn.close()
    assert row["vehicle_type_2"] == ""
    assert row["service_2"] == ""
    assert row["total_estimate"] == 75  # only vehicle 1 counted


def test_book_endpoint_applies_and_persists_expecting_discount(client):
    res = client.post("/api/book", data={
        "name": "Parent", "phone": "440", "location": "Chardon",
        "num_vehicles": "1", "vehicle_type": "Sedan", "service": "Deep Clean",
        "expecting_discount_1": "1",
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["total_estimate"] == 230  # 280 - 50
    assert "Expecting" in data["discount_applied"]

    conn = appmod.get_db()
    row = conn.execute("SELECT * FROM bookings WHERE name = 'Parent'").fetchone()
    conn.close()
    assert row["expecting_discount_1"] == 1
    assert row["expecting_discount_2"] == 0


def test_book_endpoint_ignores_expecting_when_not_deep_clean(client):
    res = client.post("/api/book", data={
        "name": "NotEligible", "phone": "440", "location": "Chardon",
        "num_vehicles": "1", "vehicle_type": "Sedan", "service": "Full Detail",
        "expecting_discount_1": "1",
    })
    data = res.get_json()
    assert data["total_estimate"] == 195  # no discount
    assert "Expecting" not in data["discount_applied"]

    conn = appmod.get_db()
    row = conn.execute("SELECT * FROM bookings WHERE name = 'NotEligible'").fetchone()
    conn.close()
    # Stored flag is normalized to off because the service doesn't qualify.
    assert row["expecting_discount_1"] == 0


@pytest.mark.parametrize("payload", [
    {"phone": "1", "location": "x"},        # missing name
    {"name": "n", "location": "x"},         # missing phone
    {"name": "n", "phone": "1"},            # missing location
    {},                                     # missing all
])
def test_book_endpoint_validation(client, payload):
    res = client.post("/api/book", data=payload)
    assert res.status_code == 400
    assert res.get_json()["ok"] is False


def test_loyalty_visits_increment(client):
    for expected in (1, 2, 3):
        res = client.post("/api/book", data={
            "name": "Repeat", "phone": "440", "email": "Loyal@Example.com",
            "location": "Chardon", "service": "Exterior Detail", "vehicle_type": "Sedan",
        })
        assert res.get_json()["visits"] == expected


# ──────────────────────────────────────────────────────────────────────────
#  Schema + static frontend
# ──────────────────────────────────────────────────────────────────────────
def test_schema_has_new_columns():
    conn = appmod.get_db()
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(bookings)")}
    conn.close()
    for c in (
        "location", "vehicle_type_2", "service_2", "addons_2", "upcharges_2",
        "expecting_discount_1", "expecting_discount_2",
    ):
        assert c in cols


def test_home_serves_index(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Tony's Detailing" in res.data


def test_booking_page_serves(client):
    assert client.get("/booking").status_code == 200
    assert client.get("/booking.html").status_code == 200


def test_deep_clean_page_serves(client):
    res = client.get("/deep-clean")
    assert res.status_code == 200
    assert b"Deep Clean" in res.data
    assert client.get("/deep-clean.html").status_code == 200


def test_static_assets_serve(client):
    assert client.get("/fonts/Inter-Regular.ttf").status_code == 200
    assert client.get("/assets/logo.png").status_code == 200


def test_unknown_path_404(client):
    assert client.get("/does-not-exist.xyz").status_code == 404
