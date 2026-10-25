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
        "Wash, Clay, Seal": {"Sedan": 140, "SUV/Crossover": 150, "Large SUV/Truck": 180, "Minivan": 165},
        "Interior Detail": {"Sedan": 120, "SUV/Crossover": 135, "Large SUV/Truck": 155, "Minivan": 145},
        "Full Detail": {"Sedan": 195, "SUV/Crossover": 215, "Large SUV/Truck": 240, "Minivan": 225},
        "Ceramic Coating (2-Year)": {
            "Sedan": 299.99, "SUV/Crossover": 349.99, "Large SUV/Truck": 399.99, "Minivan": 374.99,
        },
        "Ceramic Coating (5-Year)": {
            "Sedan": 799.99, "SUV/Crossover": 849.99, "Large SUV/Truck": 1049.99, "Minivan": 949.99,
        },
        "Ceramic Coating (Elite 8-Year)": {
            "Sedan": 1099.99, "SUV/Crossover": 1149.99, "Large SUV/Truck": 1349.99, "Minivan": 1249.99,
        },
        "Monthly Maintenance Visit": {"Sedan": 150, "SUV/Crossover": 160, "Large SUV/Truck": 180, "Minivan": 170},
        "Biweekly Maintenance Visit": {"Sedan": 140, "SUV/Crossover": 150, "Large SUV/Truck": 170, "Minivan": 160},
    }
    assert appmod.BASE_PRICES == expected
    for service, by_vehicle in expected.items():
        for vehicle, price in by_vehicle.items():
            assert appmod.vehicle_cost(service, vehicle, [], []) == price


def test_leather_addon_flat():
    assert appmod.vehicle_cost("Full Detail", "Sedan", ["Leather Conditioning"], []) == 195 + 40


def test_clay_iron_addon_scales_with_vehicle():
    expected = {"Sedan": 60, "SUV/Crossover": 70, "Large SUV/Truck": 80, "Minivan": 70}
    for vehicle, clay in expected.items():
        base = appmod.BASE_PRICES["Wash, Clay, Seal"][vehicle]
        cost = appmod.vehicle_cost("Wash, Clay, Seal", vehicle, ["Clay & Iron Decontamination"], [])
        assert cost == base + clay, f"{vehicle}: expected {base + clay}, got {cost}"


def test_headlight_addon_flat_any_size():
    for vehicle in appmod.VEHICLE_TYPES:
        base = appmod.BASE_PRICES["Full Detail"][vehicle]
        cost = appmod.vehicle_cost("Full Detail", vehicle, ["Headlight Restoration"], [])
        assert cost == base + 100, f"{vehicle}: expected {base + 100}, got {cost}"


def test_ceramic_tiers_priced_by_size():
    assert appmod.vehicle_cost("Ceramic Coating (2-Year)", "Sedan", [], []) == 299.99
    assert appmod.vehicle_cost("Ceramic Coating (5-Year)", "SUV/Crossover", [], []) == 849.99
    assert appmod.vehicle_cost("Ceramic Coating (Elite 8-Year)", "Large SUV/Truck", [], []) == 1349.99


def test_odor_addon_flat():
    assert appmod.vehicle_cost("Interior Detail", "Sedan", ["Odor Eliminator"], []) == 120 + 50


def test_all_addons_stack():
    # Sedan Full 195 + leather 40 + clay 60 + odor 50 = 345
    cost = appmod.vehicle_cost(
        "Full Detail", "Sedan",
        ["Leather Conditioning", "Clay & Iron Decontamination", "Odor Eliminator"], [],
    )
    assert cost == 345


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
    for service in ("Wash, Clay, Seal", "Interior Detail"):
        total, summary = appmod.calculate_estimate("1", "A Friend", veh(service, "Sedan"))
        assert "Referral" not in summary
        assert total == appmod.BASE_PRICES[service]["Sedan"]


def test_referral_applies_to_full_detail():
    total, summary = appmod.calculate_estimate("1", "A Friend", veh("Full Detail", "Sedan"))
    assert total == 160  # 195 - 35
    assert "Referral (-$35.00)" in summary


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
    # v1 Full SUV 215 + v2 Wash/Clay/Seal Sedan 140 x 2 = 495, less 10% = 445.5
    total, summary = appmod.calculate_estimate(
        "3+", "", veh("Full Detail", "SUV/Crossover"), veh("Wash, Clay, Seal", "Sedan")
    )
    assert total == 445.5
    assert "Multi-vehicle 10%" in summary


def test_referral_eligible_via_second_vehicle():
    # v1 Wash/Clay/Seal Sedan 140 (not eligible) + v2 Full Sedan 195 (eligible) = 335
    # multi 33.5, referral 35 => 335 - 68.5 = 266.5
    total, summary = appmod.calculate_estimate(
        "2", "Bob", veh("Wash, Clay, Seal", "Sedan"), veh("Full Detail", "Sedan")
    )
    assert total == 266.5
    assert "Multi-vehicle 10% (-$33.50)" in summary
    assert "Referral (-$35.00)" in summary


def test_full_stack_two_vehicles_with_addons():
    # v1 Full SUV 215 + leather 40 + clay(SUV) 70 = 325
    # v2 Interior Sedan 120 + pet hair 30 = 150
    # subtotal 475, multi 47.5, referral 35 => 392.5
    total, summary = appmod.calculate_estimate(
        "2", "Bob",
        veh("Full Detail", "SUV/Crossover", ["Leather Conditioning", "Clay & Iron Decontamination"]),
        veh("Interior Detail", "Sedan", [], ["Pet Hair"]),
    )
    assert total == 392.5
    assert "Multi-vehicle 10% (-$47.50)" in summary
    assert "Referral (-$35.00)" in summary
    assert "Total saved: $82.50" in summary


def test_second_vehicle_ignored_when_count_one():
    # num=1 should ignore the v2 dict entirely
    total, summary = appmod.calculate_estimate(
        "1", "", veh("Wash, Clay, Seal", "Sedan"), veh("Full Detail", "Large SUV/Truck")
    )
    assert total == 140
    assert summary == "None"


# ──────────────────────────────────────────────────────────────────────────
#  calculate_estimate — maintenance plans + travel fee
# ──────────────────────────────────────────────────────────────────────────
def test_maintenance_plan_priced_by_size():
    expected = {
        "Monthly Maintenance Visit": {"Sedan": 150, "SUV/Crossover": 160, "Large SUV/Truck": 180, "Minivan": 170},
        "Biweekly Maintenance Visit": {"Sedan": 140, "SUV/Crossover": 150, "Large SUV/Truck": 170, "Minivan": 160},
    }
    for service, by_vehicle in expected.items():
        for vehicle, price in by_vehicle.items():
            total, summary = appmod.calculate_estimate("1", "", veh(service, vehicle))
            assert total == price
            assert summary == "None"


def test_travel_fee_added_outside_radius():
    total, summary = appmod.calculate_estimate(
        "1", "", veh("Monthly Maintenance Visit", "Sedan"), outside_radius=True
    )
    assert total == 165
    assert "Travel fee, outside standard radius (+$15.00)" in summary


def test_travel_fee_not_added_by_default():
    total, summary = appmod.calculate_estimate("1", "", veh("Monthly Maintenance Visit", "Sedan"))
    assert total == 150
    assert "Travel fee" not in summary


def test_travel_fee_flat_regardless_of_vehicle_count():
    # v1 + v2 Biweekly Sedan (140 each) - 10% multi = 252, travel fee is once, not per vehicle.
    total, summary = appmod.calculate_estimate(
        "2", "", veh("Biweekly Maintenance Visit", "Sedan"), veh("Biweekly Maintenance Visit", "Sedan"),
        outside_radius=True,
    )
    assert total == 252 + 15
    assert "Travel fee, outside standard radius (+$15.00)" in summary


def test_travel_fee_stacks_with_referral_and_discounts():
    # Referral only applies to Full Detail, so a maintenance plan visit
    # ignores it — travel fee still applies on top of the base price.
    total, summary = appmod.calculate_estimate(
        "1", "A Friend", veh("Monthly Maintenance Visit", "Sedan"), outside_radius=True
    )
    assert total == 165
    assert "Referral" not in summary


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
    assert data["total_estimate"] == 392.5
    assert "Referral" in data["discount_applied"]


def test_book_endpoint_persists_second_vehicle(client):
    client.post("/api/book", data={
        "name": "Carl", "phone": "2165551234", "location": "Munson",
        "num_vehicles": "2", "vehicle_type": "Sedan", "service": "Full Detail",
        "vehicle_type_2": "Minivan", "service_2": "Interior Detail",
        "addons_2": ["Odor Eliminator"], "upcharges_2": ["Smoke/Odor"],
    })
    conn = appmod.get_db()
    row = conn.execute("SELECT * FROM bookings WHERE name = 'Carl'").fetchone()
    conn.close()
    assert row["location"] == "Munson"
    assert row["vehicle_type_2"] == "Minivan"
    assert row["service_2"] == "Interior Detail"
    assert row["addons_2"] == "Odor Eliminator"
    assert row["upcharges_2"] == "Smoke/Odor"
    # v1 Full Sedan 195 + v2 Interior Detail Minivan (145 + odor 50 + smoke 40 = 235)
    # subtotal 430, multi 10% 43 => 387
    assert row["total_estimate"] == 387.0


def test_book_endpoint_clears_v2_when_single(client):
    client.post("/api/book", data={
        "name": "Solo", "phone": "111", "location": "Chardon",
        "num_vehicles": "1", "vehicle_type": "Sedan", "service": "Wash, Clay, Seal",
        "vehicle_type_2": "Minivan", "service_2": "Full Detail",  # should be dropped
    })
    conn = appmod.get_db()
    row = conn.execute("SELECT * FROM bookings WHERE name = 'Solo'").fetchone()
    conn.close()
    assert row["vehicle_type_2"] == ""
    assert row["service_2"] == ""
    assert row["total_estimate"] == 140  # only vehicle 1 counted


def test_book_endpoint_maintenance_plan_with_travel_fee(client):
    res = client.post("/api/book", data={
        "name": "Recurring Rita", "phone": "440", "location": "Beachwood",
        "num_vehicles": "1", "vehicle_type": "SUV/Crossover",
        "service": "Monthly Maintenance Visit", "outside_radius": "1",
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["total_estimate"] == 175  # 160 + 15 travel fee
    assert "Travel fee" in data["discount_applied"]

    conn = appmod.get_db()
    row = conn.execute("SELECT * FROM bookings WHERE name = 'Recurring Rita'").fetchone()
    conn.close()
    assert row["outside_radius"] == 1
    assert row["service"] == "Monthly Maintenance Visit"


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
            "location": "Chardon", "service": "Wash, Clay, Seal", "vehicle_type": "Sedan",
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
        "outside_radius",
    ):
        assert c in cols


def test_home_serves_index(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Tony's Detailing" in res.data


def test_booking_page_serves(client):
    assert client.get("/booking").status_code == 200


def test_rv_detailing_page_serves(client):
    res = client.get("/rv-detailing")
    assert res.status_code == 200
    # One package with size-bracket pricing.
    assert b"Full Deep Detail" in res.data
    assert b"$550" in res.data and b"$700" in res.data and b"$1,000" in res.data
    assert b"Contact for Quote" not in res.data


def test_boat_detailing_page_serves(client):
    res = client.get("/boat-detailing")
    assert res.status_code == 200
    assert b"Pontoon" in res.data
    assert b"Contact for Quote" in res.data


def test_home_links_to_rv_and_boat_pages_without_their_content(client):
    """RV/boat content lives only on the dedicated pages; the homepage
    carries nothing beyond nav/footer links to them."""
    html = client.get("/").data.decode("utf-8")

    assert 'href="/rv-detailing"' in html
    assert 'href="/boat-detailing"' in html

    # No RV/boat sections, cards, or pricing on the homepage.
    for marker in (
        "Full Deep Detail", "$550", "Travel Trailer", "Class A", "Class C",
        "Contact for Quote", "Jet Ski", "Pontoon", "Bowrider", "Cabin Cruiser",
    ):
        assert marker not in html, f"homepage should not contain RV/boat content: {marker!r}"


@pytest.mark.parametrize("path,marker", [
    ("/about", b"Owner-Operated"),
    ("/about", b"Meet Tony"),
    ("/gallery", b"Our Work"),
    ("/gallery", b"galGrid"),
    ("/reviews", b"reviews-embed"),
    ("/reviews", b"Trusted By Local Drivers"),
    ("/faq", b"Frequently Asked"),
    ("/faq", b"FAQPage"),
])
def test_content_pages_serve(client, path, marker):
    res = client.get(path)
    assert res.status_code == 200
    assert marker in res.data


def test_content_pages_have_unique_titles(client):
    import re
    titles = {}
    for path in ("/", "/booking", "/rv-detailing", "/boat-detailing",
                 "/about", "/gallery", "/reviews", "/faq"):
        html = client.get(path).data.decode("utf-8")
        m = re.search(r"<title>(.*?)</title>", html, re.S)
        assert m, f"{path} has no <title>"
        titles[path] = m.group(1).strip()
    # Every page's SEO title is unique.
    assert len(set(titles.values())) == len(titles), titles


def test_faq_has_valid_faqpage_jsonld(client):
    import json, re
    html = client.get("/faq").data.decode("utf-8")
    blocks = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S
    )
    assert blocks, "FAQ page is missing JSON-LD"
    data = json.loads(blocks[0])  # must be valid JSON
    assert data["@type"] == "FAQPage"
    assert len(data["mainEntity"]) >= 6


def test_static_assets_serve(client):
    assert client.get("/fonts/Inter-Regular.ttf").status_code == 200
    assert client.get("/assets/logo.png").status_code == 200


# ──────────────────────────────────────────────────────────────────────────
#  Media slots + manifest
# ──────────────────────────────────────────────────────────────────────────
def test_media_manifest_lists_all_slots(client):
    res = client.get("/api/media")
    assert res.status_code == 200
    data = res.get_json()
    # Every named slot is reported...
    assert set(data.keys()) == set(appmod.MEDIA_SLOTS)
    # ...and each slot reflects whether its committed file has content
    # (e.g. the hero video ships filled; unfilled placeholders stay hidden).
    for name, filled in data.items():
        size = os.path.getsize(os.path.join(appmod.MEDIA_DIR, name))
        assert filled == (size > 0), name


def test_media_present_requires_nonempty_known_slot(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "MEDIA_DIR", str(tmp_path))

    # Unknown slot names are never reported present (no arbitrary path probing).
    assert appmod.media_present("../app.py") is False
    assert appmod.media_present("not-a-slot.jpg") is False

    slot = tmp_path / "rv-hero.jpg"
    slot.write_bytes(b"")          # empty placeholder → hidden
    assert appmod.media_present("rv-hero.jpg") is False
    slot.write_bytes(b"\xff\xd8\xff\xe0")  # real content → shown
    assert appmod.media_present("rv-hero.jpg") is True


def test_media_manifest_reflects_filled_slot(client, tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "MEDIA_DIR", str(tmp_path))
    (tmp_path / "hero-video.mp4").write_bytes(b"\x00\x00\x00\x18ftyp")
    data = client.get("/api/media").get_json()
    assert data["hero-video.mp4"] is True
    assert data["rv-hero.jpg"] is False


def test_media_placeholder_files_exist():
    # The named slots are committed (as empty placeholders) so they can be
    # replaced in place without touching code.
    for slot in appmod.MEDIA_SLOTS:
        assert os.path.isfile(os.path.join(appmod.MEDIA_DIR, slot)), slot


# ──────────────────────────────────────────────────────────────────────────
#  Gallery placeholders (static/gallery/) — always visible, swapped in place
# ──────────────────────────────────────────────────────────────────────────
def test_gallery_placeholder_images_serve(client):
    # Gallery images ship with real content so the strip and grid are always
    # visible. Slots 7-34 are real customer-vehicle photos.
    for i in range(7, 35):
        res = client.get(f"/static/gallery/placeholder-{i}.jpg")
        assert res.status_code == 200
        assert len(res.data) > 1000, f"placeholder-{i}.jpg looks empty"


def test_homepage_our_work_strip(client):
    html = client.get("/").data.decode("utf-8")
    assert "Our Work" in html
    assert "work-strip" in html
    for i in range(7, 35):
        assert f"/static/gallery/placeholder-{i}.jpg" in html
    # The hover overlay links through to the full gallery page.
    assert "work-overlay" in html
    assert 'href="/gallery"' in html


def test_gallery_page_grid_lists_all_placeholders(client):
    html = client.get("/gallery").data.decode("utf-8")
    for i in range(7, 35):
        assert f"/static/gallery/placeholder-{i}.jpg" in html


def test_unknown_path_404(client):
    assert client.get("/does-not-exist.xyz").status_code == 404


# ──────────────────────────────────────────────────────────────────────────
#  Static route lockdown — only fonts/, assets/, static/ are servable
# ──────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("path", [
    "/app.py",
    "/bookings.db",
    "/.env",
    "/.env.example",
    "/requirements.txt",
    "/requirements-dev.txt",
    "/tests/test_booking.py",
    "/tools/build_fonts.py",
    "/.git/config",
    "/vercel.json",
    "/README.md",
    "/Phone Preview.html",
    "/fonts/../app.py",
])
def test_sensitive_paths_blocked(client, path):
    assert client.get(path).status_code == 404, f"{path} must not be served"


def test_allowed_static_dirs_still_serve(client):
    for path in (
        "/fonts/Inter-Regular.ttf",
        "/fonts/Inter-Regular.woff2",
        "/fonts/Montserrat-ExtraBold.woff2",
        "/assets/logo.png",
        "/assets/og-card.jpg",
        "/assets/favicon-32x32.png",
        "/assets/favicon-16x16.png",
        "/assets/apple-touch-icon.png",
        "/assets/lucide-1.23.0.min.js",
        "/favicon.ico",
    ):
        assert client.get(path).status_code == 200, path


def test_index_html_redirects_to_root(client):
    res = client.get("/index.html")
    assert res.status_code == 301
    assert res.headers["Location"] == "/"


# ──────────────────────────────────────────────────────────────────────────
#  robots.txt + sitemap.xml
# ──────────────────────────────────────────────────────────────────────────
def test_robots_txt_on_production_host(client):
    res = client.get("/robots.txt", headers={"Host": appmod.CANONICAL_HOST})
    assert res.status_code == 200
    body = res.data.decode()
    assert "User-agent: *" in body
    assert "Allow: /" in body
    assert "Disallow: /api/" in body
    # Always the production sitemap, never the requested host.
    assert f"Sitemap: {appmod.SITE_URL}/sitemap.xml" in body


def test_robots_txt_blocks_crawlers_on_preview_hosts(client):
    """A Vercel preview must not invite crawlers to index a throwaway URL."""
    res = client.get(
        "/robots.txt",
        headers={"Host": "tonys-detailing-git-some-branch.vercel.app"},
    )
    assert res.status_code == 200
    body = res.data.decode()
    assert body == "User-agent: *\nDisallow: /\n"


def test_sitemap_always_names_the_production_domain(client):
    """Served off a preview host, the sitemap still lists production URLs."""
    res = client.get(
        "/sitemap.xml",
        headers={"Host": "tonys-detailing-git-some-branch.vercel.app"},
    )
    body = res.data.decode()
    assert "some-branch" not in body
    assert appmod.SITE_URL + "/booking" in body


def test_sitemap_lists_every_public_page(client):
    import xml.etree.ElementTree as ET

    res = client.get("/sitemap.xml")
    assert res.status_code == 200
    root = ET.fromstring(res.data)  # must be valid XML
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = {el.text for el in root.findall("sm:url/sm:loc", ns)}
    expected = {
        appmod.SITE_URL + ("/" if page == "/" else page)
        for page in appmod.PUBLIC_PAGES
    }
    assert locs == expected


# ──────────────────────────────────────────────────────────────────────────
#  Cache + security headers
# ──────────────────────────────────────────────────────────────────────────
def test_cache_headers_by_path_type(client):
    assert "immutable" in client.get("/fonts/Inter-Regular.woff2").headers["Cache-Control"]
    assert "immutable" in client.get("/assets/lucide-1.23.0.min.js").headers["Cache-Control"]
    assert "max-age=604800" in client.get("/assets/logo.png").headers["Cache-Control"]
    assert "max-age=3600" in client.get("/static/gallery/placeholder-7.jpg").headers["Cache-Control"]
    assert client.get("/").headers["Cache-Control"] == "no-cache"
    assert client.get("/api/media").headers["Cache-Control"] == "no-store"


def test_security_headers_on_all_responses(client):
    for path in ("/", "/booking", "/api/media", "/does-not-exist"):
        headers = client.get(path).headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "SAMEORIGIN"
        assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


# ──────────────────────────────────────────────────────────────────────────
#  Branded 404 + SEO head tags
# ──────────────────────────────────────────────────────────────────────────
def test_branded_404_page(client):
    res = client.get("/no-such-page")
    assert res.status_code == 404
    assert b"Page Not Found" in res.data
    assert b"Back to Homepage" in res.data


def test_api_404_stays_json(client):
    res = client.get("/api/no-such-endpoint")
    assert res.status_code == 404
    assert res.get_json()["ok"] is False


def test_every_page_has_seo_head_tags(client):
    for page in appmod.PUBLIC_PAGES:
        html = client.get(page).data.decode("utf-8")
        assert 'rel="canonical"' in html, page
        assert 'property="og:title"' in html, page
        assert 'property="og:image"' in html, page
        assert 'name="twitter:card"' in html, page
        assert 'rel="icon"' in html, page
        assert "woff2" in html, page
        assert "unpkg.com" not in html, page
        assert "/assets/lucide-1.23.0.min.js" in html, page


def test_homepage_has_localbusiness_jsonld(client):
    import json, re
    html = client.get("/").data.decode("utf-8")
    blocks = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S
    )
    assert blocks, "homepage is missing JSON-LD"
    data = json.loads(blocks[0])
    assert data["@type"] == "AutoWash"
    assert data["telephone"] == "+12169034783"


def test_fonts_are_real_binaries():
    """Guard against the base64-text corruption that broke every font."""
    import glob
    ttfs = glob.glob(os.path.join(appmod.BASE_DIR, "fonts", "*.ttf"))
    woff2s = glob.glob(os.path.join(appmod.BASE_DIR, "fonts", "*.woff2"))
    assert len(ttfs) == 8 and len(woff2s) == 8
    for path in ttfs:
        with open(path, "rb") as fh:
            assert fh.read(4) == b"\x00\x01\x00\x00", f"{path} is not a TTF"
    for path in woff2s:
        with open(path, "rb") as fh:
            assert fh.read(4) == b"wOF2", f"{path} is not a WOFF2"


# ──────────────────────────────────────────────────────────────────────────
#  Service-area (town) pages
# ──────────────────────────────────────────────────────────────────────────
def test_area_pages_serve_at_the_clean_url(client):
    for slug in appmod.AREA_PAGES:
        res = client.get(f"/{slug}")
        assert res.status_code == 200, slug
        assert b"</html>" in res.data, slug


def test_area_pages_have_unique_town_h1(client):
    """Each town page needs its own H1 naming the town and the service."""
    import re
    seen = {}
    for slug in appmod.AREA_PAGES:
        html = client.get(f"/{slug}").data.decode("utf-8")
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
        assert m, f"{slug} has no <h1>"
        h1 = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        town = slug.replace("-", " ")
        assert town in h1.lower(), f"{slug} H1 omits the town: {h1}"
        assert "detailing" in h1.lower(), f"{slug} H1 omits the service: {h1}"
        seen[slug] = h1
    assert len(set(seen.values())) == len(seen), seen


def test_area_pages_seo_field_lengths(client):
    """Titles and descriptions have to fit what search results actually show."""
    import re
    titles, descs = {}, {}
    for slug in appmod.AREA_PAGES:
        html = client.get(f"/{slug}").data.decode("utf-8")
        title = re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()
        desc = re.search(
            r'<meta name="description" content="(.*?)">', html, re.S
        ).group(1).strip()
        assert len(title) < 60, f"{slug} title is {len(title)} chars: {title}"
        assert len(desc) < 160, f"{slug} description is {len(desc)} chars"
        titles[slug], descs[slug] = title, desc
    assert len(set(titles.values())) == len(titles), titles
    assert len(set(descs.values())) == len(descs), descs


def test_area_pages_intro_copy_is_not_boilerplate(client):
    """Guard the one thing a templated town page gets wrong: identical copy."""
    import re
    intros = {}
    for slug in appmod.AREA_PAGES:
        html = client.get(f"/{slug}").data.decode("utf-8")
        intro = re.search(r'<p class="hero-sub">(.*?)</p>', html, re.S).group(1)
        intros[slug] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", intro)).strip()
    assert len(set(intros.values())) == len(intros), "town intros are duplicated"
    # The same paragraph with the town swapped would still be unique, so also
    # require the wording itself to diverge.
    for slug, text in intros.items():
        words = set(text.lower().split())
        for other, other_text in intros.items():
            if other == slug:
                continue
            overlap = len(words & set(other_text.lower().split())) / len(words)
            assert overlap < 0.6, f"{slug} and {other} share {overlap:.0%} of words"


def test_area_pages_service_and_localbusiness_jsonld(client):
    import json, re
    for slug in appmod.AREA_PAGES:
        html = client.get(f"/{slug}").data.decode("utf-8")
        block = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.S
        )
        assert block, f"{slug} has no JSON-LD"
        graph = json.loads(block.group(1))["@graph"]
        nodes = {node["@type"]: node for node in graph}
        assert "Service" in nodes and "AutoWash" in nodes, slug
        # The Service hangs off the shared business entity, not a stray one.
        assert nodes["Service"]["provider"]["@id"] == nodes["AutoWash"]["@id"]
        town = nodes["Service"]["areaServed"]["name"]
        assert town.lower().replace(" ", "-") == slug, slug
        assert nodes["AutoWash"]["areaServed"]["name"] == town, slug


def test_area_page_pricing_matches_homepage_table(client):
    """Town pricing is lifted from index.html — it must not drift from it."""
    import re

    def base_rows(html):
        body = re.search(
            r"<h3>Base Pricing by Vehicle Size</h3>.*?<tbody>(.*?)</tbody>",
            html,
            re.S,
        ).group(1)
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "|", body)).strip()

    home = base_rows(client.get("/").data.decode("utf-8"))
    assert "$" in home
    for slug in appmod.AREA_PAGES:
        page = base_rows(client.get(f"/{slug}").data.decode("utf-8"))
        assert page == home, f"{slug} pricing differs from the homepage table"


def test_homepage_links_every_area_page(client):
    """Nav dropdown and the Service Area section both have to carry the towns."""
    html = client.get("/").data.decode("utf-8")
    start = html.index('<section id="area">')
    area_section = html[start : html.index("</section>", start)]
    for slug in appmod.AREA_PAGES:
        assert f'href="/{slug}"' in html, f"nav is missing /{slug}"
        assert f'href="/{slug}"' in area_section, f"#area is missing /{slug}"


def test_area_pages_in_sitemap(client):
    body = client.get("/sitemap.xml").data.decode("utf-8")
    for slug in appmod.AREA_PAGES:
        assert f"/{slug}</loc>" in body, slug


# ──────────────────────────────────────────────────────────────────────────
#  Server-rendered hero media
# ──────────────────────────────────────────────────────────────────────────
def test_hero_image_is_in_the_served_html(client):
    """The hero must paint from the document, not from a later fetch."""
    html = client.get("/").data.decode("utf-8")
    assert '<div class="hero-media" id="heroMedia"><img' in html
    assert 'src="/static/media/hero-fallback.jpg"' in html
    assert 'fetchpriority="high"' in html


def test_hero_does_not_fetch_the_media_manifest(client):
    """No page builds its hero from /api/media any more."""
    for path in ("/", "/rv-detailing", "/boat-detailing"):
        html = client.get(path).data.decode("utf-8")
        assert "fetch('/api/media')" not in html, path


def test_hero_video_is_lazy_not_eager(client):
    """The 1.7MB video must not be a blocking src in the initial HTML."""
    import re
    html = client.get("/").data.decode("utf-8")
    tag = re.search(r"<video[^>]*>", html).group(0)
    assert 'preload="none"' in tag, tag
    assert 'data-src="/static/media/hero-video.mp4"' in tag, tag
    assert " src=" not in tag, "video should carry data-src, not src"
    assert 'poster="/static/media/hero-fallback.jpg"' in tag, tag


def test_empty_media_slot_renders_an_empty_hero(client):
    """A 0-byte slot leaves the container empty so the gradient shows."""
    for path, slot in (("/rv-detailing", "rv-hero.jpg"),
                       ("/boat-detailing", "boat-hero.jpg")):
        html = client.get(path).data.decode("utf-8")
        if appmod.media_present(slot):
            assert f'src="/static/media/{slot}"' in html, path
        else:
            assert '<div class="hero-media" id="heroMedia"></div>' in html, path


def test_hero_rerenders_when_a_media_slot_changes(client, tmp_path, monkeypatch):
    """Dropping a file in has to show up without a code change or redeploy."""
    monkeypatch.setattr(appmod, "MEDIA_DIR", str(tmp_path))
    appmod._page_cache.clear()

    empty = tmp_path / "rv-hero.jpg"
    empty.write_bytes(b"")
    assert '<div class="hero-media" id="heroMedia"></div>' in (
        client.get("/rv-detailing").data.decode("utf-8")
    )

    empty.write_bytes(b"\xff\xd8\xff" + b"x" * 128)
    html = client.get("/rv-detailing").data.decode("utf-8")
    assert 'src="/static/media/rv-hero.jpg"' in html, "cache did not invalidate"
    appmod._page_cache.clear()


def test_hero_video_is_not_oversized():
    """Guard the regression that started this: a 12MB autoplaying hero."""
    path = os.path.join(appmod.MEDIA_DIR, "hero-video.mp4")
    if not appmod.media_present("hero-video.mp4"):
        return
    size_mb = os.path.getsize(path) / (1024 * 1024)
    assert size_mb < 4, f"hero video is {size_mb:.1f}MB — compress it"


def test_hero_pages_still_serve_html(client):
    for path in ("/", "/rv-detailing", "/boat-detailing"):
        res = client.get(path)
        assert res.status_code == 200, path
        assert res.mimetype == "text/html", path
        assert b"</html>" in res.data, path


# ──────────────────────────────────────────────────────────────────────────
#  Canonical URLs
# ──────────────────────────────────────────────────────────────────────────
def test_html_form_redirects_to_the_clean_url(client):
    """Every page has exactly one URL that serves content."""
    for url, filename in appmod.PAGES:
        res = client.get(f"/{filename}")
        assert res.status_code == 301, filename
        assert res.headers["Location"] == url, filename


def test_clean_urls_serve_and_html_forms_never_do(client):
    for url, filename in appmod.PAGES:
        assert client.get(url).status_code == 200, url
        assert client.get(f"/{filename}").status_code == 301, filename


def test_no_page_links_to_a_dot_html_url():
    """Internal links all use the canonical form — no link should eat a 301."""
    import glob
    import re
    offenders = {}
    for path in glob.glob(os.path.join(appmod.BASE_DIR, "*.html")):
        html = open(path, encoding="utf-8").read()
        hits = re.findall(r'href="(?!https?://)[^"]*\.html[^"]*"', html)
        if hits:
            offenders[os.path.basename(path)] = sorted(set(hits))
    assert not offenders, offenders


def test_canonical_tags_match_the_registered_urls(client):
    """<link rel="canonical"> must point at the URL that actually serves."""
    import re
    for url, _ in appmod.PAGES:
        html = client.get(url).data.decode("utf-8")
        m = re.search(r'<link rel="canonical" href="([^"]+)"', html)
        if not m:
            continue
        expected = appmod.SITE_URL + ("" if url == "/" else url)
        assert m.group(1).rstrip("/") == expected.rstrip("/"), url


def test_sitemap_lists_only_clean_urls(client):
    body = client.get("/sitemap.xml").data.decode("utf-8")
    assert ".html" not in body


def test_redirect_preserves_the_query_string(client):
    """/booking.html?plan=... is a link in the wild; the form reads that param."""
    res = client.get("/booking.html?plan=Monthly%20Maintenance%20Visit")
    assert res.status_code == 301
    assert res.headers["Location"] == "/booking?plan=Monthly%20Maintenance%20Visit"


# ──────────────────────────────────────────────────────────────────────────
#  Service + Offer JSON-LD on the ceramic / RV / boat pages
# ──────────────────────────────────────────────────────────────────────────
def _service_graph(client, url):
    import json, re
    html = client.get(url).data.decode("utf-8")
    block = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S
    )
    assert block, f"{url} has no JSON-LD"
    nodes = {n["@type"]: n for n in json.loads(block.group(1))["@graph"]}
    assert "Service" in nodes and "AutoWash" in nodes, url
    # The Service hangs off the shared business entity, not a stray one.
    assert nodes["Service"]["provider"]["@id"] == nodes["AutoWash"]["@id"]
    assert nodes["AutoWash"]["@id"] == appmod.SITE_URL + "/#business"
    return html, nodes["Service"]


def test_ceramic_offers_match_the_tier_table(client):
    """Coating prices are published as Offers — they must not drift from the page."""
    import re
    html, svc = _service_graph(client, "/ceramic-coating")
    tiers = svc["hasOfferCatalog"]["itemListElement"]
    assert [t["name"] for t in tiers] == re.findall(
        r'<h3 class="cer-name">(.*?)</h3>', html
    )
    schema_prices = [o["price"] for t in tiers for o in t["itemListElement"]]
    page_prices = [
        amt.replace(",", "")
        for amt in re.findall(r'<span class="amt">\$([\d,.]+)</span>', html)
    ]
    assert schema_prices == page_prices


def test_rv_offers_match_the_size_table(client):
    """RV brackets are ranges — each Offer's low/high comes from the table."""
    import re
    html, svc = _service_graph(client, "/rv-detailing")
    rows = re.findall(
        r'<td>[^<]*<span class="pr-size">[^<]*</span></td>'
        r"<td>\$([\d,]+)&ndash;\$([\d,]+)</td>",
        html,
    )
    assert rows, "RV pricing table did not parse"
    assert [
        (o["lowPrice"], o["highPrice"])
        for o in svc["hasOfferCatalog"]["itemListElement"]
    ] == [(lo.replace(",", ""), hi.replace(",", "")) for lo, hi in rows]


def test_boat_offers_carry_no_invented_price(client):
    """Every boat row reads "Contact for Quote" — the schema must not claim one."""
    import re
    html, svc = _service_graph(client, "/boat-detailing")
    offers = svc["hasOfferCatalog"]["itemListElement"]
    assert [o["name"] for o in offers] == re.findall(
        r"<tr><td>([^<]+)</td><td>Contact for Quote</td></tr>", html
    )
    for o in offers:
        assert "price" not in o and "lowPrice" not in o, o["name"]
