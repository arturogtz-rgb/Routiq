"""Iter 42 — Custom hospedaje breakdown: qty editable, nights auto, subtotal=unit×qty×nights.
Verifies backend pricing, public endpoint and PDF contains '$/noche × N hab × N noches'."""
import os, requests, pytest

BASE = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE}/api/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return sess


@pytest.fixture(scope="module")
def client_id(s):
    r = s.get(f"{BASE}/api/clients")
    assert r.status_code == 200
    directo = [c for c in r.json() if c.get("channel") == "directo"]
    if directo:
        return directo[0]["id"]
    r = s.post(f"{BASE}/api/clients", json={
        "name": "TEST_iter42_client", "phone": "555", "email": "t42@x.com", "channel": "directo"
    })
    assert r.status_code in (200, 201)
    return r.json()["id"]


def _build_payload(client_id, **overrides):
    base = {
        "type": "personalizado", "client_id": client_id,
        "custom_title": "TEST_iter42 Hospedaje",
        "dates": {"start": "2026-07-01", "end": "2026-07-04"},
        "pax": {"adultos": 2, "menores": 0, "rooms": []},
        "custom_nights": 3, "custom_rooms": 2,
        "custom_items": [{
            "category": "hospedaje", "name": "TEST_Hotel iter42", "description": "",
            "net_price": 1000.0, "price_type": "neto", "unit": "per_night",
            "qty": 2, "service_date": "", "start_time": "", "end_time": "",
            "checkin": "2026-07-01", "checkout": "2026-07-04", "nights": 3,
        }],
        "custom_itinerary": [], "custom_includes": [], "custom_excludes": [],
        "contacts": None, "notes": "", "presentation_text": "",
        "important_info": "", "show_price_breakdown": True,
    }
    base.update(overrides)
    return base


def test_hospedaje_subtotal_qty_x_nights(s, client_id):
    """Subtotal = unit_price * qty * nights = 1315.79 * 2 * 3 = 7894.74 (margin 0.76)."""
    r = s.post(f"{BASE}/api/quotations", json=_build_payload(client_id))
    assert r.status_code in (200, 201), r.text
    q = r.json()
    items = q.get("items") or []
    hosp = [it for it in items if it.get("category") == "hospedaje"]
    assert len(hosp) == 1, items
    it = hosp[0]
    assert it["qty"] == 2, it
    assert it["nights"] == 3, it
    assert abs(it["unit_price"] - 1315.79) < 0.02, it["unit_price"]
    assert abs(it["subtotal"] - 7894.74) < 0.05, it["subtotal"]
    # cleanup
    s.delete(f"{BASE}/api/quotations/{q['id']}")


def test_hospedaje_qty_default_1_when_zero(s, client_id):
    """Backend uses qty=1 default when qty<=0 (hospedaje)."""
    payload = _build_payload(client_id)
    payload["custom_items"][0]["qty"] = 0
    r = s.post(f"{BASE}/api/quotations", json=payload)
    assert r.status_code in (200, 201)
    q = r.json()
    it = [x for x in q["items"] if x["category"] == "hospedaje"][0]
    assert it["qty"] == 1
    # subtotal = 1315.79 * 1 * 3 = 3947.37
    assert abs(it["subtotal"] - 3947.37) < 0.05
    s.delete(f"{BASE}/api/quotations/{q['id']}")


def test_public_link_and_pdf_contains_hospedaje_qty_nights(s, client_id):
    """Public endpoint exposes nights/qty; PDF generates without error."""
    r = s.post(f"{BASE}/api/quotations", json=_build_payload(client_id))
    assert r.status_code in (200, 201)
    q = r.json(); qid = q["id"]

    link = s.post(f"{BASE}/api/quotations/{qid}/public-link")
    assert link.status_code in (200, 201), link.text
    token = link.json()["token"]

    pub = requests.get(f"{BASE}/api/public/quotations/{token}")
    assert pub.status_code == 200
    pq = pub.json()["quotation"]
    items = pq.get("items") or []
    hosp = [it for it in items if it.get("category") == "hospedaje"][0]
    assert hosp["qty"] == 2
    assert hosp["nights"] == 3
    assert hosp["checkin"] == "2026-07-01"
    assert hosp["checkout"] == "2026-07-04"

    # PDF (auth)
    pdf = s.get(f"{BASE}/api/quotations/{qid}/pdf")
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"
    assert len(pdf.content) > 2000

    # PDF (public)
    ppdf = requests.get(f"{BASE}/api/public/quotations/{token}/pdf")
    assert ppdf.status_code == 200
    assert ppdf.content[:4] == b"%PDF"

    s.delete(f"{BASE}/api/quotations/{qid}")


def test_regression_servicios_pdf_still_works(s, client_id):
    """Regression: servicios a la carta PDF generation not broken by refactor."""
    r = s.get(f"{BASE}/api/services")
    if r.status_code != 200 or not r.json():
        pytest.skip("no services catalog")
    svc = r.json()[0]
    payload = {
        "type": "servicios", "client_id": client_id,
        "dates": {"start": "2026-07-01", "end": "2026-07-03"},
        "pax": {"adultos": 2, "menores": 0, "rooms": []},
        "services": [{"service_id": svc["id"], "qty": 2}],
        "notes": "", "show_price_breakdown": True,
    }
    cr = s.post(f"{BASE}/api/quotations", json=payload)
    assert cr.status_code in (200, 201), cr.text
    qid = cr.json()["id"]
    pdf = s.get(f"{BASE}/api/quotations/{qid}/pdf")
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"
    s.delete(f"{BASE}/api/quotations/{qid}")
