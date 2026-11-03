"""v3 quote form backend (/api/quote) and templated pages."""
import os
import sys
import tempfile
import types

import pytest

os.environ.setdefault("DATABASE_PATH", os.path.join(tempfile.mkdtemp(), "test_quotes.db"))
os.environ.pop("RESEND_API_KEY", None)

import app as appmod  # noqa: E402

GOOD = {
    "first_name": "Jane", "last_name": "Doe", "phone": "(440) 555-0123",
    "email": "jane@example.com", "vehicle_year": "2021", "vehicle_make": "Volvo",
    "vehicle_model": "XC60", "vehicle_size": "SUV/Crossover", "zip": "44024",
    "services": ["Ceramic Coating", "Full Detail"],
    "ceramic_package": "3-Year Protection", "condition": ["Pet Hair"],
    "timing": "As Soon as Possible", "utilities": "Yes",
    "contact_method": "Text Message", "call_time": "Evening",
    "source_page": "/lp/ceramic-coating", "utm": "source=facebook",
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr(appmod, "RESEND_API_KEY", "")
    monkeypatch.setattr(appmod, "SHEETS_WEBHOOK_URL", "")
    appmod.init_quotes_table()
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def last_quote():
    conn = appmod.get_db()
    row = conn.execute("SELECT * FROM quotes ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row)


def test_quote_success_is_stored(client):
    res = client.post("/api/quote", data=GOOD)
    assert res.status_code == 200 and res.get_json()["ok"] is True
    row = last_quote()
    assert row["phone"] == "4405550123"
    assert row["area"] == "standard" and row["miles"] == 0.0
    assert row["services"] == "Ceramic Coating, Full Detail"
    assert "$849.99 (SUV/Crossover)" in row["estimate"]
    assert "$215 (SUV/Crossover)" in row["estimate"]


@pytest.mark.parametrize("field,value", [
    ("first_name", ""), ("phone", "555-12"), ("email", "nope"), ("zip", "440"),
    ("services", []),
])
def test_quote_required_fields(client, field, value):
    data = dict(GOOD, **{field: value})
    res = client.post("/api/quote", data=data)
    assert res.status_code == 400
    assert field in res.get_json()["errors"]


def test_quote_ignores_unknown_choices_and_hidden_followups(client):
    data = dict(GOOD, services=["Full Detail", "Hacked"], ceramic_package="5-Year Protection (Elite)",
                timing="Tomorrow!!", vehicle_year="abcd")
    assert client.post("/api/quote", data=data).status_code == 200
    row = last_quote()
    assert row["services"] == "Full Detail"
    assert row["ceramic_package"] == ""  # ceramic not selected -> follow-up dropped
    assert row["timing"] == "" and row["vehicle_year"] == ""


def test_honeypot_is_silently_dropped(client):
    before = appmod.get_db().execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
    res = client.post("/api/quote", data=dict(GOOD, website="spam.biz"))
    assert res.get_json()["ok"] is True
    assert appmod.get_db().execute("SELECT COUNT(*) FROM quotes").fetchone()[0] == before


def test_undelivered_lead_on_vercel_is_reported(client, monkeypatch):
    """No email/sheet on Vercel means the lead only lives in /tmp — say so."""
    monkeypatch.setenv("VERCEL", "1")
    res = client.post("/api/quote", data=GOOD)
    assert res.status_code == 503 and res.get_json()["error"] == "delivery"


def test_failed_email_is_reported(client, monkeypatch):
    monkeypatch.setattr(appmod, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(appmod, "send_quote_email", lambda lead: False)
    assert client.post("/api/quote", data=GOOD).status_code == 503


def test_sheet_alone_counts_as_delivered(client, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(appmod, "SHEETS_WEBHOOK_URL", "https://example.invalid/hook")
    monkeypatch.setattr(appmod, "send_quote_to_sheet", lambda lead: True)
    assert client.post("/api/quote", data=GOOD).status_code == 200
    assert last_quote()["delivered"] == "sheet"


def test_quote_email_payload(client, monkeypatch):
    sent = {}
    fake = types.SimpleNamespace(api_key=None, Emails=types.SimpleNamespace(send=lambda p: sent.update(p)))
    monkeypatch.setitem(sys.modules, "resend", fake)
    monkeypatch.setattr(appmod, "RESEND_API_KEY", "re_test")
    monkeypatch.setenv("VERCEL", "1")
    data = dict(GOOD, notes="<script>alert(1)</script>", zip="44139")
    assert client.post("/api/quote", data=data).status_code == 200
    assert sent["to"] == [appmod.SHOP_EMAIL]
    assert sent["reply_to"] == "jane@example.com"
    assert "Jane Doe" in sent["subject"] and "44139" in sent["subject"]
    assert "Extended area" in sent["html"]
    assert "<script>" not in sent["html"]  # customer text is escaped
    assert last_quote()["delivered"] == "email"


@pytest.mark.parametrize("zip_code,tier", [
    ("44024", "standard"), ("44022", "standard"), ("44139", "extended"),
    ("44236", "outside"), ("90210", "unknown"),
])
def test_service_area_tiers(zip_code, tier):
    assert appmod.area_for_zip(zip_code)[0] == tier


def test_old_service_name_still_prices():
    assert appmod.vehicle_cost("Wash, Clay, Seal", "Sedan", [], []) == 140


def test_template_pages_serve_with_quote_form(client):
    for url, _, _ in appmod.TEMPLATE_PAGES + appmod.LANDING_PAGES:
        res = client.get(url)
        assert res.status_code == 200, url
        assert 'id="qf"' in res.data.decode(), url


def test_service_pages_preselect_their_service(client):
    for slug in appmod.QUOTE_SERVICE_SLUGS:
        html = client.get(f"/{slug}").data.decode()
        assert f'data-preselect="{slug}"' in html, slug


def test_landing_pages_noindex_and_out_of_sitemap(client):
    sitemap = client.get("/sitemap.xml").data.decode()
    for url, _, _ in appmod.LANDING_PAGES:
        html = client.get(url).data.decode()
        assert 'name="robots" content="noindex' in html
        assert url not in sitemap
        assert 'class="nav-links"' not in html  # no menu to leak ad traffic


def test_cards_show_server_prices(client):
    html = client.get("/").data.decode()
    assert "From $799.99" in html          # ceramic 3-Year sedan
    assert "$195 – $240" in html           # full detail sedan → large SUV/truck
    assert "Quoted after inspection" in html  # paint correction
    assert "Premium Detail" not in html


def test_legacy_html_urls_redirect(client):
    for old, new in appmod.LEGACY_HTML.items():
        res = client.get(old + "?service=full-detail")
        assert res.status_code == 301
        assert res.headers["Location"] == new + "?service=full-detail"


def test_no_placeholder_social_links(client):
    html = client.get("/").data.decode()
    assert 'href="https://www.facebook.com/"' not in html
    assert 'href="https://nextdoor.com/"' not in html
