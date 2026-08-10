"""Iteration 65 — Precio por persona según ocupación en Programa personalizado / Servicios a la carta.

Feature: CustomItem now has `ocupacion` (only for category=hospedaje). Pricing_breakdown
reads it from raw `q['custom_items']` (aligned by index with items kind='custom') to
group per-occupancy and differentiate the per-person price for lodging conceptos.

Tests:
 1) UNIT — build_per_person_breakdown with custom (no pack): dos hospedajes (triple + doble)
    + un servicio de grupo. Debe: (a) doble > triple, (b) sum(rows.subtotal) == total EXACTO.
 2) UNIT — con menores (menores no llevan hospedaje custom → shared_pool uniform).
 3) UNIT — rounding: valores con residual → sigue cuadrando al centavo.
 4) UNIT — Fallback: hospedaje custom SIN ocupacion → single-row uniforme, cuadra.
 5) E2E — POST /api/quotations personalizado con custom_items[].ocupacion → GET devuelve
    per_person_breakdown con filas Doble y Triple diferenciadas (doble>triple), sum==total.
 6) E2E — GET público idéntico + PDF 200.
 7) E2E — Persistencia CustomItem.ocupacion (roundtrip) y ocupacion=null si categoría!=hospedaje.
"""

import os
import sys
import pytest
import requests

sys.path.insert(0, "/app/backend")

from pricing_breakdown import build_per_person_breakdown  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "admin@aventurate.mx"
ADMIN_PASS = "Demo2026!"


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


# --------------------------------------------------------------------------- #
# UNIT tests — helper only. No pricing engine involved (we craft the doc).
# --------------------------------------------------------------------------- #
class TestUnitCustomOccupancyBreakdown:
    def test_custom_doble_triple_differentiated_and_balances(self):
        """Spec example:
        - triple lodging 4500 / 3 pax = 1500pp + group 2000/5 = 400 → 1900pp
        - doble lodging 4000 / 2 pax = 2000pp + shared 400pp → 2400pp
        - total = 3*1900 + 2*2400 = 5700 + 4800 = 10500
        """
        q = {
            "currency": "MXN",
            "pax": {"adultos": 5, "menores": 0},
            "custom_items": [
                {"category": "hospedaje", "name": "H triple", "ocupacion": "triple",
                 "unit": "per_room", "qty": 1},
                {"category": "hospedaje", "name": "H doble", "ocupacion": "doble",
                 "unit": "per_room", "qty": 1},
                {"category": "traslado", "name": "Trans", "unit": "per_group", "qty": 1},
            ],
            "items": [
                {"kind": "custom", "category": "hospedaje", "unit": "per_room",
                 "qty": 1, "subtotal": 4500},
                {"kind": "custom", "category": "hospedaje", "unit": "per_room",
                 "qty": 1, "subtotal": 4000},
                {"kind": "custom", "category": "traslado", "unit": "per_group",
                 "qty": 1, "subtotal": 2000},
            ],
            "total": 10500,
        }
        bd = build_per_person_breakdown(q)
        assert bd is not None
        by_key = {r["key"]: r for r in bd["rows"]}
        assert "doble" in by_key and "triple" in by_key, f"got rows: {bd['rows']}"
        assert by_key["triple"]["pax"] == 3
        assert by_key["doble"]["pax"] == 2
        assert by_key["triple"]["price_per_person"] == 1900.0
        assert by_key["doble"]["price_per_person"] == 2400.0
        # Core check (b) → doble > triple
        assert by_key["doble"]["price_per_person"] > by_key["triple"]["price_per_person"]
        # Core check (a) → sum EXACTO al centavo
        assert round(sum(r["subtotal"] for r in bd["rows"]), 2) == 10500.0
        assert bd["total_pax"] == 5

    def test_custom_with_menores_uniform_shared(self):
        """1 doble + 1 triple + 2 menores; extra service of 3000 shared across ALL 7 pax."""
        q = {
            "currency": "MXN",
            "pax": {"adultos": 5, "menores": 2},
            "custom_items": [
                {"category": "hospedaje", "ocupacion": "doble", "unit": "per_room", "qty": 1},
                {"category": "hospedaje", "ocupacion": "triple", "unit": "per_room", "qty": 1},
                {"category": "tour", "unit": "per_group", "qty": 1},
            ],
            "items": [
                {"kind": "custom", "category": "hospedaje", "unit": "per_room", "qty": 1, "subtotal": 2000},  # 1000pp doble
                {"kind": "custom", "category": "hospedaje", "unit": "per_room", "qty": 1, "subtotal": 3000},  # 1000pp triple
                {"kind": "custom", "category": "tour", "unit": "per_group", "qty": 1, "subtotal": 3500},  # 500pp shared
            ],
            "total": 8500,
        }
        bd = build_per_person_breakdown(q)
        assert bd is not None
        assert round(sum(r["subtotal"] for r in bd["rows"]), 2) == 8500.0
        # menores may be shown as its own row when the helper detects lodging split
        keys = {r["key"] for r in bd["rows"]}
        assert "doble" in keys and "triple" in keys

    def test_custom_rounding_absorbs_residual(self):
        """Group 1000 / 7 pax = 142.857... → residual on the largest occ row."""
        q = {
            "currency": "MXN",
            "pax": {"adultos": 7, "menores": 0},
            "custom_items": [
                {"category": "hospedaje", "ocupacion": "cuadruple", "unit": "per_room", "qty": 1},
                {"category": "hospedaje", "ocupacion": "triple", "unit": "per_room", "qty": 1},
                {"category": "tour", "unit": "per_group", "qty": 1},
            ],
            "items": [
                {"kind": "custom", "category": "hospedaje", "unit": "per_room", "qty": 1, "subtotal": 2000},
                {"kind": "custom", "category": "hospedaje", "unit": "per_room", "qty": 1, "subtotal": 1500},
                {"kind": "custom", "category": "tour", "unit": "per_group", "qty": 1, "subtotal": 1000},
            ],
            "total": 4500,
        }
        bd = build_per_person_breakdown(q)
        assert bd is not None
        assert round(sum(r["subtotal"] for r in bd["rows"]), 2) == 4500.0
        big = max(bd["rows"], key=lambda r: r["pax"])
        assert big["key"] == "cuadruple"

    def test_fallback_old_data_no_ocupacion(self):
        """Datos viejos: hospedaje custom SIN ocupacion → single 'persona' row, cuadra."""
        q = {
            "currency": "MXN",
            "pax": {"adultos": 4, "menores": 0},
            "custom_items": [
                {"category": "hospedaje", "unit": "per_room", "qty": 2},  # no ocupacion
                {"category": "tour", "unit": "per_group", "qty": 1},
            ],
            "items": [
                {"kind": "custom", "category": "hospedaje", "unit": "per_room", "qty": 2, "subtotal": 6000},
                {"kind": "custom", "category": "tour", "unit": "per_group", "qty": 1, "subtotal": 2000},
            ],
            "total": 8000,
        }
        bd = build_per_person_breakdown(q)
        assert bd is not None
        assert len(bd["rows"]) == 1
        assert bd["rows"][0]["key"] == "persona"
        assert bd["rows"][0]["price_per_person"] == 2000.0
        assert round(sum(r["subtotal"] for r in bd["rows"]), 2) == 8000.0


# --------------------------------------------------------------------------- #
# Helpers for E2E
# --------------------------------------------------------------------------- #
def _ensure_client(sess) -> str:
    r = sess.get(f"{BASE_URL}/api/clients", timeout=15)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    if items:
        return items[0]["id"]
    r = sess.post(f"{BASE_URL}/api/clients",
                  json={"name": "TEST_ClientOcc", "channel": "directo",
                        "phone": "5551110000", "email": "test_occ@example.com"},
                  timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# --------------------------------------------------------------------------- #
# E2E tests — Personalizado con doble + triple
# --------------------------------------------------------------------------- #
class TestE2EPersonalizadoOccupancy:
    _created_ids: list[str] = []

    def test_create_personalizado_with_doble_and_triple(self, admin_session):
        client_id = _ensure_client(admin_session)
        payload = {
            "client_id": client_id,
            "type": "personalizado",
            "custom_title": "TEST_PersonalizadoOccBreakdown",
            "pax": {"adultos": 5, "menores": 0},
            "dates": {"start": "2026-07-01", "end": "2026-07-03"},
            "services": [],
            "custom_items": [
                {"category": "hospedaje", "name": "Hotel doble", "net_price": 2000,
                 "price_type": "neto", "unit": "per_night", "qty": 2, "ocupacion": "doble"},
                {"category": "hospedaje", "name": "Hotel triple", "net_price": 1500,
                 "price_type": "neto", "unit": "per_night", "qty": 2, "ocupacion": "triple"},
                {"category": "traslado", "name": "Traslado grupo", "net_price": 2000,
                 "price_type": "neto", "unit": "per_group", "qty": 1},
            ],
            "custom_nights": 2,
            "custom_rooms": 2,
            "show_per_person": True,
        }
        r = admin_session.post(f"{BASE_URL}/api/quotations", json=payload, timeout=30)
        assert r.status_code == 201, r.text
        q = r.json()
        TestE2EPersonalizadoOccupancy._created_ids.append(q["id"])
        # Persistencia CustomItem.ocupacion
        cis = q.get("custom_items") or []
        occs = [ci.get("ocupacion") for ci in cis]
        assert "doble" in occs and "triple" in occs, f"ocupacion missing: {occs}"
        # Non-lodging item should have ocupacion=None
        for ci in cis:
            if ci.get("category") != "hospedaje":
                assert ci.get("ocupacion") in (None, ""), f"non-lodging has ocupacion: {ci}"

    def test_get_returns_breakdown_doble_gt_triple(self, admin_session):
        if not TestE2EPersonalizadoOccupancy._created_ids:
            pytest.skip("no quotation created")
        qid = TestE2EPersonalizadoOccupancy._created_ids[0]
        r = admin_session.get(f"{BASE_URL}/api/quotations/{qid}", timeout=15)
        assert r.status_code == 200
        q = r.json()
        bd = q.get("per_person_breakdown")
        assert bd is not None, f"expected per_person_breakdown; q keys={list(q.keys())}"
        by_key = {row["key"]: row for row in bd["rows"]}
        assert "doble" in by_key and "triple" in by_key, f"rows: {bd['rows']}"
        # doble > triple (lodging per persona doble > lodging per persona triple)
        assert by_key["doble"]["price_per_person"] > by_key["triple"]["price_per_person"], \
            f"doble={by_key['doble']['price_per_person']} vs triple={by_key['triple']['price_per_person']}"
        # sum al centavo
        target = q.get("final_total") if q.get("final_total") is not None else q.get("total")
        s = round(sum(row["subtotal"] for row in bd["rows"]), 2)
        assert s == round(float(target), 2), f"sum {s} != total {target}"

    def test_public_endpoint_shows_same_breakdown(self, admin_session):
        if not TestE2EPersonalizadoOccupancy._created_ids:
            pytest.skip("no quotation")
        qid = TestE2EPersonalizadoOccupancy._created_ids[0]
        r = admin_session.post(f"{BASE_URL}/api/quotations/{qid}/public-link", timeout=15)
        assert r.status_code == 200, r.text
        token = r.json()["token"]
        r = requests.get(f"{BASE_URL}/api/public/quotations/{token}", timeout=15)
        assert r.status_code == 200
        pub = r.json().get("quotation") or {}
        bd = pub.get("per_person_breakdown")
        assert bd is not None, "public should have per_person_breakdown"
        by_key = {row["key"]: row for row in bd["rows"]}
        assert "doble" in by_key and "triple" in by_key
        assert by_key["doble"]["price_per_person"] > by_key["triple"]["price_per_person"]
        s = round(sum(row["subtotal"] for row in bd["rows"]), 2)
        assert s == round(float(pub["final_total"]), 2)

    def test_pdf_ok(self, admin_session):
        if not TestE2EPersonalizadoOccupancy._created_ids:
            pytest.skip("no quotation")
        qid = TestE2EPersonalizadoOccupancy._created_ids[0]
        r = admin_session.get(f"{BASE_URL}/api/quotations/{qid}/pdf", timeout=30)
        assert r.status_code == 200, f"pdf failed: {r.status_code}"
        assert r.content[:4] == b"%PDF"


# --------------------------------------------------------------------------- #
# E2E — Edit persistence: PATCH updating custom_items[].ocupacion
# --------------------------------------------------------------------------- #
class TestE2EEditPersistence:
    def test_patch_custom_items_ocupacion_persists(self, admin_session):
        if not TestE2EPersonalizadoOccupancy._created_ids:
            pytest.skip("no quotation")
        qid = TestE2EPersonalizadoOccupancy._created_ids[0]
        # Get current
        q = admin_session.get(f"{BASE_URL}/api/quotations/{qid}", timeout=15).json()
        new_items = []
        for ci in q.get("custom_items") or []:
            new_ci = {k: v for k, v in ci.items() if k != "id"}
            # Swap doble <-> triple
            if new_ci.get("category") == "hospedaje":
                if new_ci.get("ocupacion") == "doble":
                    new_ci["ocupacion"] = "cuadruple"
            new_items.append(new_ci)
        r = admin_session.patch(f"{BASE_URL}/api/quotations/{qid}",
                                json={"custom_items": new_items}, timeout=20)
        assert r.status_code == 200, r.text
        q2 = admin_session.get(f"{BASE_URL}/api/quotations/{qid}", timeout=15).json()
        occs = [ci.get("ocupacion") for ci in q2.get("custom_items") or []]
        assert "cuadruple" in occs, f"expected cuadruple after patch; got {occs}"
        # Breakdown re-computes and still balances
        bd = q2.get("per_person_breakdown")
        assert bd is not None
        target = q2.get("final_total") if q2.get("final_total") is not None else q2.get("total")
        s = round(sum(row["subtotal"] for row in bd["rows"]), 2)
        assert s == round(float(target), 2)


# --------------------------------------------------------------------------- #
# Cleanup
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session", autouse=True)
def _cleanup(admin_session):
    yield
    for qid in TestE2EPersonalizadoOccupancy._created_ids:
        try:
            admin_session.delete(f"{BASE_URL}/api/quotations/{qid}", timeout=15)
        except Exception:
            pass
