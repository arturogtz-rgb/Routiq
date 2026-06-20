"""Iteration 44 — Custom pricing engine (Cotización a Medida) by unit.

Rule (only for type='personalizado'):
  subtotal = unit_price × multiplier where multiplier depends ONLY on unit:
    per_night  -> number of nights between checkin/checkout (qty IGNORED)
    per_group  -> 1
    per_room / per_person / per_day / per_vehicle -> qty

Check-in / check-out / nights are informational and DO NOT multiply except per_night.

Regression: Paquete Armado + Servicios a la carta — custom_items behavior is
historical: per_night extra still uses qty (NOT nights).
"""
import os
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
LOGIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}
CLIENT_LAURA = "5e4141c0-5a25-4619-8eea-c635455bdbec"  # Laura Ramírez (directo)

PRICE_PUB = 1000.0  # price_type='publico' → unit_price = entered (no divisor)
CHECKIN = "2026-07-01"
CHECKOUT = "2026-07-04"  # 3 nights
NIGHTS = 3
QTY = 5


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json=LOGIN)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def created_ids():
    ids = []
    yield ids


def _hosp_item(unit, qty=QTY, checkin=CHECKIN, checkout=CHECKOUT, nights=NIGHTS):
    return {
        "category": "hospedaje", "name": f"Hosp {unit}", "description": "",
        "net_price": PRICE_PUB, "price_type": "publico", "unit": unit, "qty": qty,
        "service_date": "", "start_time": "", "end_time": "",
        "checkin": checkin, "checkout": checkout, "nights": nights,
    }


def _create_custom(client, items, title="TEST_iter44"):
    payload = {
        "type": "personalizado",
        "client_id": CLIENT_LAURA,
        "custom_title": title,
        "dates": {"start": CHECKIN, "end": CHECKOUT},
        "pax": {"adultos": 4, "menores": 0, "rooms": []},
        "custom_nights": 0,
        "custom_rooms": 1,
        "custom_items": items,
        "custom_itinerary": [],
        "custom_includes": [], "custom_excludes": [],
        "contacts": None, "executive_id": None,
        "notes": "iter44", "presentation_text": "", "important_info": "",
        "show_price_breakdown": True,
    }
    r = client.post(f"{BASE}/api/quotations", json=payload)
    assert r.status_code == 201, f"{r.status_code}: {r.text}"
    return r.json()


# ---------- CUSTOM (programa personalizado) ----------

class TestCustomPricingByUnit:

    def test_per_night_uses_nights_ignores_qty(self, client, created_ids):
        q = _create_custom(client, [_hosp_item("per_night", qty=QTY)])
        created_ids.append(q["id"])
        items = q["items"]
        assert len(items) == 1
        it = items[0]
        # subtotal = 1000 * 3 (NOT 1000*5)
        assert it["unit_price"] == 1000.0
        assert it["nights"] == 3
        assert it["subtotal"] == 3000.0, f"per_night expected 3000, got {it['subtotal']}"
        # qty stored = nights (since engine sets qty=nights for per_night)
        assert it["qty"] == 3
        assert q["subtotal"] == 3000.0
        assert q["total"] == 3000.0  # directo => no commission

    def test_per_room_uses_qty_ignores_nights(self, client, created_ids):
        q = _create_custom(client, [_hosp_item("per_room", qty=QTY)])
        created_ids.append(q["id"])
        it = q["items"][0]
        assert it["subtotal"] == 5000.0, f"per_room expected 5000, got {it['subtotal']}"
        assert it["qty"] == 5
        assert it["nights"] == 3  # informational, persisted

    def test_per_person_uses_qty(self, client, created_ids):
        q = _create_custom(client, [_hosp_item("per_person", qty=4)])
        created_ids.append(q["id"])
        it = q["items"][0]
        assert it["subtotal"] == 4000.0
        assert it["qty"] == 4

    def test_per_group_always_one(self, client, created_ids):
        q = _create_custom(client, [_hosp_item("per_group", qty=QTY)])
        created_ids.append(q["id"])
        it = q["items"][0]
        assert it["subtotal"] == 1000.0, f"per_group expected 1000, got {it['subtotal']}"
        assert it["qty"] == 1

    def test_per_vehicle_uses_qty(self, client, created_ids):
        q = _create_custom(client, [_hosp_item("per_vehicle", qty=3)])
        created_ids.append(q["id"])
        it = q["items"][0]
        assert it["subtotal"] == 3000.0
        assert it["qty"] == 3

    def test_per_day_uses_qty(self, client, created_ids):
        q = _create_custom(client, [_hosp_item("per_day", qty=2)])
        created_ids.append(q["id"])
        it = q["items"][0]
        assert it["subtotal"] == 2000.0
        assert it["qty"] == 2

    def test_multi_items_pdf_and_public_link(self, client, created_ids):
        items = [
            _hosp_item("per_night", qty=99),  # → 3000
            _hosp_item("per_room", qty=2),    # → 2000
            _hosp_item("per_group", qty=10),  # → 1000
        ]
        q = _create_custom(client, items, title="TEST_iter44_multi")
        created_ids.append(q["id"])
        assert q["subtotal"] == 6000.0
        subs = [it["subtotal"] for it in q["items"]]
        assert subs == [3000.0, 2000.0, 1000.0]
        # nights stay informational on all items
        assert all(it["nights"] == 3 for it in q["items"])
        assert all(it["checkin"] == CHECKIN and it["checkout"] == CHECKOUT for it in q["items"])

        # PDF
        rpdf = client.get(f"{BASE}/api/quotations/{q['id']}/pdf")
        assert rpdf.status_code == 200
        assert rpdf.content[:4] == b"%PDF"
        assert len(rpdf.content) > 2000

        # Public link
        rlink = client.post(f"{BASE}/api/quotations/{q['id']}/public-link")
        assert rlink.status_code in (200, 201)
        token = rlink.json().get("token") or rlink.json().get("public_token")
        assert token
        rpub = requests.get(f"{BASE}/api/public/quotations/{token}")
        assert rpub.status_code == 200
        pub = rpub.json().get("quotation") or rpub.json()
        pub_items = pub.get("items") or []
        assert len(pub_items) == 3
        assert [it["subtotal"] for it in pub_items] == [3000.0, 2000.0, 1000.0]
        # informational checkin/checkout/nights still exposed
        assert pub_items[0]["nights"] == 3
        assert pub_items[0]["checkin"] == CHECKIN
        assert pub_items[0]["checkout"] == CHECKOUT


# ---------- REGRESSION: Paquete Armado ----------

class TestPaqueteRegression:

    def test_paquete_extra_per_night_still_uses_qty(self, client, created_ids):
        # Find a package
        r = client.get(f"{BASE}/api/packages")
        assert r.status_code == 200
        packs = r.json()
        # Pick first active package with hotels
        pack = next((p for p in packs if p.get("hotels")), None)
        if not pack:
            pytest.skip("No package with hotels in seed")
        hotel = pack["hotels"][0]
        # An extra per_night concept with qty=5 must use qty (NOT nights between dates)
        extra = {
            "category": "extra", "name": "Extra paquete per_night", "description": "",
            "net_price": 1000.0, "price_type": "publico", "unit": "per_night", "qty": 5,
            "service_date": "", "start_time": "", "end_time": "",
            "checkin": "", "checkout": "", "nights": 0,
        }
        payload = {
            "type": "paquete",
            "client_id": CLIENT_LAURA,
            "package_id": pack["id"],
            "hotel_name": hotel["name"],
            "pax": {"adultos": 2, "menores": 0, "rooms": [{"ocupacion": "doble", "count": 1}]},
            "dates": {"start": CHECKIN, "end": CHECKOUT},
            "selected_services": [],
            "custom_items": [extra],
            "notes": "TEST_iter44_paquete_reg",
        }
        r2 = client.post(f"{BASE}/api/quotations", json=payload)
        assert r2.status_code == 201, r2.text
        q = r2.json()
        created_ids.append(q["id"])
        # Locate the custom extra
        custom_items = [it for it in q["items"] if it.get("kind") == "custom"]
        assert len(custom_items) == 1
        ce = custom_items[0]
        # qty must be 5 (historic behavior — NOT engine custom_engine=True path)
        assert ce["qty"] == 5, f"expected qty=5 (historic), got {ce['qty']}"
        assert ce["subtotal"] == 5000.0, f"expected 1000*5=5000, got {ce['subtotal']}"

    def test_servicios_a_la_carta_custom_per_night_uses_qty(self, client, created_ids):
        # type 'servicios' — no package, only services + custom_items
        extra = {
            "category": "extra", "name": "Extra svc per_night", "description": "",
            "net_price": 1000.0, "price_type": "publico", "unit": "per_night", "qty": 4,
            "service_date": "", "start_time": "", "end_time": "",
            "checkin": "", "checkout": "", "nights": 0,
        }
        payload = {
            "type": "servicios",
            "client_id": CLIENT_LAURA,
            "pax": {"adultos": 2, "menores": 0, "rooms": []},
            "dates": {"start": CHECKIN, "end": CHECKOUT},
            "services": [{"service_id": "842e1125-5873-4fda-8754-7dede0feb011", "qty": 1}],
            "custom_items": [extra],
            "notes": "TEST_iter44_svc_reg",
        }
        r = client.post(f"{BASE}/api/quotations", json=payload)
        assert r.status_code == 201, r.text
        q = r.json()
        created_ids.append(q["id"])
        custom_items = [it for it in q["items"] if it.get("kind") == "custom"]
        assert len(custom_items) == 1
        ce = custom_items[0]
        assert ce["qty"] == 4, f"expected qty=4 (historic svc), got {ce['qty']}"
        assert ce["subtotal"] == 4000.0


# ---------- Cleanup ----------

def test_zz_cleanup(client, created_ids):
    for qid in created_ids:
        try:
            client.delete(f"{BASE}/api/quotations/{qid}")
        except Exception:
            pass
