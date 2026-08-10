"""Iteration 64 — 'Precio por persona según ocupación' (presentation-only helper).

Tests:
  1) UNIT: build_per_person_breakdown — exact-to-the-cent balance across scenarios
     (multi-occupancy, rounding residual absorption, custom/services single row,
     final_total with discount).
  2) E2E: GET /api/quotations/{id} exposes per_person_breakdown when show_per_person
     is True (and hides it when False). PATCH persists the flag.
  3) E2E public: GET /api/public/quotations/{token} exposes show_per_person and
     per_person_breakdown; sum(rows.subtotal) == final_total.
  4) PDF: GET /api/quotations/{id}/pdf returns application/pdf (200).
"""

import os
import sys
import pytest
import requests

# So `from pricing_breakdown import ...` works when running pytest from /app.
sys.path.insert(0, "/app/backend")

from pricing_breakdown import build_per_person_breakdown  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "admin@aventurate.mx"
ADMIN_PASS = "Demo2026!"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


# --------------------------------------------------------------------------- #
# 1) UNIT: helper logic — exact sum == total (to the cent).
# --------------------------------------------------------------------------- #
class TestUnitBreakdown:
    def test_spec_example_8pax_2triples_1doble(self):
        """Spec: 8 pax (2 triples=6 + 1 doble=2). Triple lodging 1500pp, Doble 2000pp.
        Group service 3200 (÷8=400/persona) + per_person service 500 → shared=900/pax.
        Expected: Triple=2400, Doble=2900, total=6*2400 + 2*2900 = 20200."""
        q = {
            "currency": "MXN",
            "pax": {"rooms": [{"ocupacion": "triple", "count": 2},
                              {"ocupacion": "doble", "count": 1}], "menores": 0},
            "items": [
                {"kind": "hospedaje", "ocupacion": "triple", "qty": 6, "unit_price": 1500, "subtotal": 9000},
                {"kind": "hospedaje", "ocupacion": "doble", "qty": 2, "unit_price": 2000, "subtotal": 4000},
                {"kind": "servicio", "qty": 1, "subtotal": 3200},
                {"kind": "servicio", "qty": 8, "subtotal": 4000},  # 500 per person * 8
            ],
            "total": 20200,
        }
        bd = build_per_person_breakdown(q)
        assert bd is not None
        by_key = {r["key"]: r for r in bd["rows"]}
        assert by_key["triple"]["price_per_person"] == 2400.0
        assert by_key["triple"]["pax"] == 6
        assert by_key["doble"]["price_per_person"] == 2900.0
        assert by_key["doble"]["pax"] == 2
        assert sum(r["subtotal"] for r in bd["rows"]) == 20200.0
        assert bd["total"] == 20200.0
        assert bd["total_pax"] == 8

    def test_rounding_residual_absorbed_in_largest_row(self):
        """3200 group / 7 pax = 457.1428... — residual must land on the biggest row so
        the SUM equals total exactly (to the cent)."""
        q = {
            "currency": "MXN",
            "pax": {"rooms": [{"ocupacion": "triple", "count": 2},
                              {"ocupacion": "sencilla", "count": 1}], "menores": 0},
            "items": [
                {"kind": "hospedaje", "ocupacion": "triple", "qty": 6, "unit_price": 1000, "subtotal": 6000},
                {"kind": "hospedaje", "ocupacion": "sencilla", "qty": 1, "unit_price": 3000, "subtotal": 3000},
                {"kind": "servicio", "qty": 1, "subtotal": 3200},
            ],
            "total": 12200,
        }
        bd = build_per_person_breakdown(q)
        assert bd is not None
        assert sum(r["subtotal"] for r in bd["rows"]) == 12200.0
        # Residual should ride on the row with the most pax (triple=6).
        big = max(bd["rows"], key=lambda r: r["pax"])
        assert big["key"] == "triple"

    def test_custom_single_row(self):
        """Personalizado sin ocupación → 1 sola fila 'Por persona'."""
        q = {
            "currency": "MXN",
            "pax": {"adultos": 4, "menores": 0},
            "items": [{"kind": "custom", "qty": 1, "subtotal": 10000}],
            "total": 10000,
        }
        bd = build_per_person_breakdown(q)
        assert bd is not None
        assert len(bd["rows"]) == 1
        assert bd["rows"][0]["key"] == "persona"
        assert bd["rows"][0]["price_per_person"] == 2500.0
        assert sum(r["subtotal"] for r in bd["rows"]) == 10000.0

    def test_final_total_with_discount(self):
        """final_total (después de descuento) debe ser el objetivo, no `total`."""
        q = {
            "currency": "MXN",
            "pax": {"rooms": [{"ocupacion": "doble", "count": 1}]},
            "items": [
                {"kind": "hospedaje", "ocupacion": "doble", "qty": 2, "unit_price": 5000, "subtotal": 10000},
            ],
            "total": 10000,
            "final_total": 9000,  # 10% off
        }
        bd = build_per_person_breakdown(q)
        assert bd is not None
        assert bd["total"] == 9000.0
        assert sum(r["subtotal"] for r in bd["rows"]) == 9000.0

    def test_with_menores(self):
        q = {
            "currency": "MXN",
            "pax": {"rooms": [{"ocupacion": "doble", "count": 1}], "menores": 1},
            "items": [
                {"kind": "hospedaje", "ocupacion": "doble", "qty": 2, "unit_price": 2000, "subtotal": 4000},
                {"kind": "hospedaje", "label": "Hospedaje menor", "qty": 1, "subtotal": 1000},
                {"kind": "servicio", "qty": 1, "subtotal": 3000},
            ],
            "total": 8000,
        }
        bd = build_per_person_breakdown(q)
        assert bd is not None
        assert sum(r["subtotal"] for r in bd["rows"]) == 8000.0
        keys = {r["key"] for r in bd["rows"]}
        assert "doble" in keys and "menor" in keys

    def test_returns_none_when_total_zero(self):
        assert build_per_person_breakdown({"total": 0, "items": []}) is None
        assert build_per_person_breakdown({"total": 100, "items": [],
                                           "pax": {"adultos": 0, "menores": 0}}) is None


# --------------------------------------------------------------------------- #
# Helpers to create real quotations end-to-end.
# --------------------------------------------------------------------------- #
def _ensure_client(sess) -> str:
    r = sess.get(f"{BASE_URL}/api/clients", timeout=15)
    assert r.status_code == 200
    items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    if items:
        return items[0]["id"]
    r = sess.post(f"{BASE_URL}/api/clients",
                  json={"name": "TEST_ClientPP", "channel": "directo",
                        "phone": "5555555555", "email": "test_pp@example.com"},
                  timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _get_any_package(sess) -> dict | None:
    r = sess.get(f"{BASE_URL}/api/packages", timeout=15)
    if r.status_code != 200:
        return None
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    return items[0] if items else None


# --------------------------------------------------------------------------- #
# 2) E2E backend — auth'd endpoints
# --------------------------------------------------------------------------- #
class TestQuotationEndpoint:
    _created_ids: list[str] = []

    def test_create_package_quotation_with_show_per_person(self, admin_session):
        pack = _get_any_package(admin_session)
        if not pack:
            pytest.skip("No packages available in seed")
        client_id = _ensure_client(admin_session)
        hotels = pack.get("hotels") or []
        hotel_name = hotels[0]["name"] if hotels else ""
        payload = {
            "client_id": client_id,
            "type": "paquete",
            "package_id": pack["id"],
            "hotel_name": hotel_name,
            "pax": {"rooms": [{"ocupacion": "triple", "count": 2},
                              {"ocupacion": "doble", "count": 1}], "menores": 0},
            "dates": {"start": "2026-06-01", "end": "2026-06-03"},
            "services": [],
            "custom_items": [],
            "show_per_person": True,
        }
        r = admin_session.post(f"{BASE_URL}/api/quotations", json=payload, timeout=30)
        assert r.status_code == 201, r.text
        q = r.json()
        assert q.get("show_per_person") is True
        TestQuotationEndpoint._created_ids.append(q["id"])

    def test_get_quotation_returns_breakdown_and_sum_matches(self, admin_session):
        if not TestQuotationEndpoint._created_ids:
            pytest.skip("no quotation created")
        qid = TestQuotationEndpoint._created_ids[0]
        r = admin_session.get(f"{BASE_URL}/api/quotations/{qid}", timeout=15)
        assert r.status_code == 200
        q = r.json()
        bd = q.get("per_person_breakdown")
        assert bd is not None, "per_person_breakdown should be present when show_per_person=True"
        target = q.get("final_total") if q.get("final_total") is not None else q.get("total")
        s = round(sum(r["subtotal"] for r in bd["rows"]), 2)
        assert s == round(float(target), 2), f"sum {s} != total {target}"
        # If pax has multiple occupancies, breakdown should show them
        rooms = (q.get("pax") or {}).get("rooms") or []
        occs = {r_.get("ocupacion") for r_ in rooms}
        row_keys = {r_["key"] for r_ in bd["rows"]}
        # Every declared occupancy should be represented in the rows
        assert occs.issubset(row_keys), f"missing occ rows: {occs - row_keys}"

    def test_patch_show_per_person_persists(self, admin_session):
        if not TestQuotationEndpoint._created_ids:
            pytest.skip("no quotation created")
        qid = TestQuotationEndpoint._created_ids[0]
        # Turn it off
        r = admin_session.patch(f"{BASE_URL}/api/quotations/{qid}",
                                json={"show_per_person": False}, timeout=15)
        assert r.status_code == 200, r.text
        r = admin_session.get(f"{BASE_URL}/api/quotations/{qid}", timeout=15)
        q = r.json()
        assert q.get("show_per_person") in (False, None)
        assert not q.get("per_person_breakdown"), "breakdown must not be present when show_per_person=False"
        # Turn back on to enable public + PDF tests
        r = admin_session.patch(f"{BASE_URL}/api/quotations/{qid}",
                                json={"show_per_person": True}, timeout=15)
        assert r.status_code == 200
        r = admin_session.get(f"{BASE_URL}/api/quotations/{qid}", timeout=15)
        assert r.json().get("show_per_person") is True


# --------------------------------------------------------------------------- #
# 3) E2E public
# --------------------------------------------------------------------------- #
class TestPublic:
    def test_public_quotation_shows_breakdown(self, admin_session):
        if not TestQuotationEndpoint._created_ids:
            pytest.skip("no quotation created")
        qid = TestQuotationEndpoint._created_ids[0]
        r = admin_session.post(f"{BASE_URL}/api/quotations/{qid}/public-link", timeout=15)
        assert r.status_code == 200, r.text
        token = r.json()["token"]
        r = requests.get(f"{BASE_URL}/api/public/quotations/{token}", timeout=15)
        assert r.status_code == 200, r.text
        pub = r.json().get("quotation") or {}
        assert pub.get("show_per_person") is True
        bd = pub.get("per_person_breakdown")
        assert bd is not None
        final_total = pub["final_total"]
        s = round(sum(r_["subtotal"] for r_ in bd["rows"]), 2)
        assert s == round(float(final_total), 2), f"public sum {s} != final_total {final_total}"


# --------------------------------------------------------------------------- #
# 4) PDF
# --------------------------------------------------------------------------- #
class TestPDF:
    def test_pdf_generates_ok(self, admin_session):
        if not TestQuotationEndpoint._created_ids:
            pytest.skip("no quotation created")
        qid = TestQuotationEndpoint._created_ids[0]
        r = admin_session.get(f"{BASE_URL}/api/quotations/{qid}/pdf", timeout=30)
        assert r.status_code == 200, f"pdf failed: {r.status_code} {r.text[:200]}"
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"


# --------------------------------------------------------------------------- #
# Cleanup — delete the TEST_ quotation.
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session", autouse=True)
def _cleanup(admin_session):
    yield
    for qid in TestQuotationEndpoint._created_ids:
        try:
            admin_session.delete(f"{BASE_URL}/api/quotations/{qid}", timeout=15)
        except Exception:
            pass
