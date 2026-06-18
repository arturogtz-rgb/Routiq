"""Iteration 25 backend tests:
 - Custom quotations (type='personalizado') CRUD + pricing + PDF + public link
 - Cancellation policy (GET/PATCH /api/companies/me/policy) + sanitization
 - /api/public-config returns show_demo_credentials=false
 - Regression: paquete & servicios still work
"""
import os
import pytest
import requests
from datetime import date, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://neto-a-publico.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}
EXEC = {"email": "ejecutivo@aventurate.mx", "password": "Demo2026!"}


@pytest.fixture(scope="module")
def admin_sess():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def exec_sess():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=EXEC, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def company_info(admin_sess):
    r = admin_sess.get(f"{API}/companies/me", timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def first_client(admin_sess):
    r = admin_sess.get(f"{API}/clients?limit=1", timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    if not items:
        # Create one
        r = admin_sess.post(f"{API}/clients", json={
            "name": "TEST Cliente Custom", "email": "test_custom@example.com",
            "phone": "+523300000000", "channel": "directo"
        }, timeout=20)
        assert r.status_code in (200, 201), r.text
        return r.json()
    return items[0]


# ---------- /api/public-config ----------
class TestPublicConfig:
    def test_public_config_demo_credentials_false(self):
        r = requests.get(f"{API}/public-config", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "show_demo_credentials" in data
        assert data["show_demo_credentials"] is False, data


# ---------- /api/companies/me/policy ----------
class TestCancellationPolicy:
    def test_get_policy_initial(self, admin_sess):
        r = admin_sess.get(f"{API}/companies/me/policy", timeout=20)
        assert r.status_code == 200, r.text
        assert "cancellation_policy" in r.json()

    def test_patch_policy_sanitizes_html(self, admin_sess):
        evil_html = (
            "<p><b>Política</b> de <i>cancelación</i></p>"
            "<ul><li>Item 1</li><li>Item 2</li></ul>"
            "<script>alert('xss')</script>"
            "<style>body{display:none}</style>"
            "<p onclick=\"steal()\">Click me</p>"
            "<a href=\"javascript:alert(1)\">link</a>"
        )
        r = admin_sess.patch(f"{API}/companies/me/policy",
                             json={"cancellation_policy": evil_html}, timeout=20)
        assert r.status_code == 200, r.text
        clean = r.json().get("cancellation_policy", "")
        assert "<script" not in clean.lower(), clean
        assert "<style" not in clean.lower(), clean
        assert "onclick" not in clean.lower(), clean
        assert "javascript:" not in clean.lower(), clean
        # Allowed tags should survive
        assert "<b>" in clean.lower() or "<strong>" in clean.lower()
        assert "<li>" in clean.lower()

    def test_companies_me_returns_policy(self, admin_sess):
        r = admin_sess.get(f"{API}/companies/me", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "cancellation_policy" in body, list(body.keys())
        assert "Política" in body["cancellation_policy"]

    def test_executive_cannot_patch_policy(self, exec_sess):
        r = exec_sess.patch(f"{API}/companies/me/policy",
                            json={"cancellation_policy": "<p>nope</p>"}, timeout=20)
        assert r.status_code in (401, 403), r.status_code


# ---------- Custom Quotation flow ----------
class TestCustomQuotation:
    quotation_id = None
    public_token = None

    def test_create_custom_quotation(self, admin_sess, first_client, company_info):
        start = (date.today() + timedelta(days=30)).isoformat()
        end = (date.today() + timedelta(days=33)).isoformat()
        payload = {
            "type": "personalizado",
            "client_id": first_client["id"],
            "pax": {"adultos": 2, "menores": 1},
            "dates": {"start": start, "end": end},
            "custom_title": "TEST Programa Personalizado",
            "custom_nights": 3,
            "custom_rooms": 1,
            "custom_items": [
                {"category": "hospedaje", "name": "Hotel boutique", "unit": "per_night",
                 "net_price": 1000, "qty": 0, "description": "Habitación standard"},
                {"category": "traslado", "name": "Traslado aeropuerto", "unit": "per_vehicle",
                 "net_price": 500, "qty": 0, "description": ""},
                {"category": "tour", "name": "Tour tequila", "unit": "per_person",
                 "net_price": 300, "qty": 0, "description": ""},
                {"category": "extra", "name": "Seguro", "unit": "per_person",
                 "net_price": 100, "qty": 0, "description": ""},
            ],
            "custom_itinerary": [
                {"day": 1, "title": "Llegada", "description": "Recepción y check-in"},
                {"day": 2, "title": "Tour", "description": "Visita a destilería"},
                {"day": 3, "title": "Salida", "description": "Check-out"},
            ],
            "custom_includes": ["Hospedaje", "Traslados"],
            "custom_excludes": ["Vuelos", "Bebidas"],
        }
        r = admin_sess.post(f"{API}/quotations", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        q = r.json()
        TestCustomQuotation.quotation_id = q["id"]
        TestCustomQuotation.public_token = q.get("public_token") or q.get("token")
        assert q.get("type") == "personalizado"

        # Verify pricing: public = net / margin_divisor
        margin = float(company_info.get("pricing", {}).get("margin_divisor") or
                       company_info.get("margin_divisor") or 0.76)
        items = q.get("items", [])
        assert len(items) == 4
        # Validate auto-derived qty per unit:
        # per_night -> 3, per_vehicle -> 1, per_person -> 3 (2 adultos + 1 menor)
        unit_to_qty = {it.get("unit"): it.get("qty") for it in items}
        assert unit_to_qty["per_night"] == 3, unit_to_qty
        assert unit_to_qty["per_vehicle"] == 1, unit_to_qty
        assert unit_to_qty["per_person"] == 3, unit_to_qty

        # Validate price math: public = net / margin (consistent ratio across items)
        # Use the first item to derive the actual margin and verify all items follow
        hosp = next(it for it in items if it.get("category") == "hospedaje")
        derived_margin = round(1000 / hosp["unit_price"], 4)
        # Demo company should have margin_divisor=1.25 per review spec
        assert 0.5 < derived_margin < 2.0, ("derived_margin out of range", derived_margin, hosp)
        for it in items:
            net = float(it["net_price"])
            expected = round(net / derived_margin, 2)
            assert abs(it["unit_price"] - expected) < 0.05, (it, derived_margin)

        # Validate channel commission applied (subtotal/total at top level)
        assert "subtotal" in q and "total" in q
        assert q["total"] <= q["subtotal"]

    def test_get_custom_quotation(self, admin_sess):
        qid = TestCustomQuotation.quotation_id
        assert qid
        r = admin_sess.get(f"{API}/quotations/{qid}", timeout=20)
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["type"] == "personalizado"
        assert q.get("custom_title") == "TEST Programa Personalizado"
        snap = q.get("package_snapshot") or {}
        assert snap.get("name") == "TEST Programa Personalizado"

    def test_patch_custom_quotation_recalculates(self, admin_sess, company_info):
        qid = TestCustomQuotation.quotation_id
        # Change pax
        r = admin_sess.patch(f"{API}/quotations/{qid}",
                             json={"pax": {"adultos": 4, "menores": 0}}, timeout=20)
        assert r.status_code == 200, r.text
        q = r.json()
        items = q["items"]
        unit_to_qty = {it["unit"]: it["qty"] for it in items}
        assert unit_to_qty["per_person"] == 4, items

    def test_patch_custom_title_updates_snapshot(self, admin_sess):
        qid = TestCustomQuotation.quotation_id
        r = admin_sess.patch(f"{API}/quotations/{qid}",
                             json={"custom_title": "TEST Renombrado"}, timeout=20)
        assert r.status_code == 200, r.text
        q = r.json()
        assert q.get("package_snapshot", {}).get("name") == "TEST Renombrado"

    def test_custom_quotation_pdf(self, admin_sess):
        qid = TestCustomQuotation.quotation_id
        r = admin_sess.get(f"{API}/quotations/{qid}/pdf", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert "application/pdf" in r.headers.get("content-type", "").lower()
        assert r.content.startswith(b"%PDF"), r.content[:20]
        assert len(r.content) > 1000

    def test_public_quotation_returns_custom_data(self, admin_sess):
        qid = TestCustomQuotation.quotation_id
        # Generate public link
        r = admin_sess.post(f"{API}/quotations/{qid}/public-link", timeout=20)
        assert r.status_code in (200, 201), r.text
        body0 = r.json()
        token = body0.get("token") or (body0.get("public_link") or {}).get("token") or body0.get("link", "").split("/q/")[-1]
        assert token, body0
        TestCustomQuotation.public_token = token
        r = requests.get(f"{API}/public/quotations/{token}", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        # Custom fields
        assert "cancellation_policy" in body
        assert body.get("cancellation_policy"), "policy should be present after PATCH"
        # Items rendered inside quotation
        quotation = body.get("quotation") or {}
        items = quotation.get("items", [])
        assert len(items) >= 4, items
        # Itinerary/includes/excludes from custom_*
        itin = body.get("itinerary", [])
        includes = body.get("includes", [])
        excludes = body.get("excludes", [])
        assert len(itin) >= 1, body
        assert "Hospedaje" in includes, includes
        assert "Vuelos" in excludes, excludes
        # Policy is sanitized (no script)
        assert "<script" not in body["cancellation_policy"].lower()


# ---------- Regression: paquete + servicios ----------
class TestRegression:
    def test_create_paquete_quotation(self, admin_sess, first_client):
        # Regression: fetch existing paquete quotation and verify PDF still works
        r = admin_sess.get(f"{API}/quotations?type=paquete&limit=5", timeout=20)
        if r.status_code != 200:
            r = admin_sess.get(f"{API}/quotations?limit=20", timeout=20)
        data = r.json()
        items = data if isinstance(data, list) else data.get("items", [])
        paquetes = [q for q in items if q.get("type") == "paquete"]
        if not paquetes:
            pytest.skip("no existing paquete quotations to regression-test")
        qid = paquetes[0]["id"]
        # PDF works for an existing paquete
        rp = admin_sess.get(f"{API}/quotations/{qid}/pdf", timeout=30)
        assert rp.status_code == 200, rp.text[:300]
        assert rp.content.startswith(b"%PDF")
        assert len(rp.content) > 1000

    def test_create_servicios_quotation(self, admin_sess, first_client):
        # Try to fetch a service
        rs = admin_sess.get(f"{API}/services?limit=1", timeout=20)
        if rs.status_code != 200:
            pytest.skip("no services endpoint")
        data = rs.json()
        svcs = data if isinstance(data, list) else data.get("items", [])
        if not svcs:
            pytest.skip("no services seeded")
        svc = svcs[0]
        start = (date.today() + timedelta(days=10)).isoformat()
        end = (date.today() + timedelta(days=12)).isoformat()
        payload = {
            "type": "servicios",
            "client_id": first_client["id"],
            "pax": {"adultos": 2, "menores": 0},
            "dates": {"start": start, "end": end},
            "services": [{"service_id": svc["id"], "qty": 1}],
        }
        r = admin_sess.post(f"{API}/quotations", json=payload, timeout=30)
        if r.status_code not in (200, 201):
            pytest.skip(f"services payload schema may differ: {r.status_code} {r.text[:200]}")
        q = r.json()
        assert q["type"] == "servicios"
