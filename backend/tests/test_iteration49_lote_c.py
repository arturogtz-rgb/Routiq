"""Iter 49 — Lote C: ServiceEditor página independiente, is_private badge,
DnD orden persistido en booking confirmation, calendario ISO en fechas y
PDF de confirmación con _fmt_date."""
import io
import os
import time

import pytest
import pdfplumber
import requests


def _load_backend_url():
    env = os.environ.get("REACT_APP_BACKEND_URL")
    if env:
        return env.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    except Exception:
        pass
    return "http://localhost:8001"


BASE_URL = _load_backend_url()
ADMIN_EMAIL = "admin@aventurate.mx"
ADMIN_PASSWORD = "Demo2026!"
DEMO_SLUG = "aventurate"
PAQUETE_GANADA_CODE = "COT-2026056"


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.text}"
    return s


@pytest.fixture(scope="session")
def ganada_id(session):
    r = session.get(f"{BASE_URL}/api/quotations")
    assert r.status_code == 200
    q = next((x for x in r.json() if x["code"] == PAQUETE_GANADA_CODE), None)
    assert q, f"No encuentro {PAQUETE_GANADA_CODE}"
    return q["id"]


# ============================================================================
# 8.1 — Crear servicio via POST /api/services (backend del ServiceEditor)
# ============================================================================
class TestServiceCRUD:
    def test_create_service(self, session):
        payload = {
            "name": "TEST_C81_Nuevo",
            "category": "tour",
            "description": "Servicio creado por test de iter49",
            "net_price": 500.0,
            "public_price": 800.0,
            "unit": "per_person",
            "is_private": False,
            "status": "active",
        }
        r = session.post(f"{BASE_URL}/api/services", json=payload)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data["name"] == "TEST_C81_Nuevo"
        assert data["net_price"] == 500.0
        assert data["public_price"] == 800.0
        assert data.get("is_private", False) is False
        # Verify in list
        r2 = session.get(f"{BASE_URL}/api/services")
        assert r2.status_code == 200
        ids = {s["id"] for s in r2.json()}
        assert data["id"] in ids
        # cleanup
        session.delete(f"{BASE_URL}/api/services/{data['id']}")

    def test_edit_service_patch(self, session):
        # create
        c = session.post(f"{BASE_URL}/api/services", json={
            "name": "TEST_C81_Edit", "category": "extra",
            "net_price": 100, "public_price": 200, "unit": "per_group",
            "is_private": False, "status": "active",
        })
        assert c.status_code in (200, 201)
        sid = c.json()["id"]
        # patch
        p = session.patch(f"{BASE_URL}/api/services/{sid}",
                          json={"name": "TEST_C81_Edit_Updated", "public_price": 333})
        assert p.status_code == 200
        assert p.json()["name"] == "TEST_C81_Edit_Updated"
        assert p.json()["public_price"] == 333
        # verify persistence via list (NOTA: no existe GET /api/services/{id})
        listing = session.get(f"{BASE_URL}/api/services").json()
        found = next((x for x in listing if x["id"] == sid), None)
        assert found is not None
        assert found["name"] == "TEST_C81_Edit_Updated"
        assert found["public_price"] == 333
        # cleanup
        session.delete(f"{BASE_URL}/api/services/{sid}")


# ============================================================================
# 8.2 — is_private (badge en listado, excluído del catálogo público)
# ============================================================================
class TestServicePrivate:
    def test_private_flag_and_public_exclusion(self, session):
        # Create a PRIVATE service (tour category so shows in public catalog)
        priv = session.post(f"{BASE_URL}/api/services", json={
            "name": "TEST_C82_Private", "category": "tour",
            "description": "Privado de prueba",
            "net_price": 100, "public_price": 200, "unit": "per_group",
            "is_private": True, "status": "active",
        })
        assert priv.status_code in (200, 201)
        priv_id = priv.json()["id"]
        assert priv.json()["is_private"] is True

        # Create a PUBLIC (non-private) service same category
        pub = session.post(f"{BASE_URL}/api/services", json={
            "name": "TEST_C82_Public", "category": "tour",
            "description": "Público de prueba",
            "net_price": 100, "public_price": 200, "unit": "per_group",
            "is_private": False, "status": "active",
        })
        assert pub.status_code in (200, 201)
        pub_id = pub.json()["id"]

        try:
            # Interno GET /api/services muestra ambos
            r = session.get(f"{BASE_URL}/api/services")
            ids = {s["id"] for s in r.json()}
            assert priv_id in ids
            assert pub_id in ids

            # Público /api/public/company/{slug}/services SOLO muestra el público
            pr = requests.get(f"{BASE_URL}/api/public/company/{DEMO_SLUG}/services")
            assert pr.status_code == 200, pr.text
            body = pr.json()
            all_public_ids = []
            for g in body.get("groups", []):
                for it in g.get("items", []):
                    all_public_ids.append(it["id"])
            assert pub_id in all_public_ids, "El servicio no-privado DEBE aparecer en /public/.../services"
            assert priv_id not in all_public_ids, "El servicio privado NO debe aparecer en /public/.../services"

            # También el detalle público debe fallar para privado
            r_priv_detail = requests.get(f"{BASE_URL}/api/public/company/{DEMO_SLUG}/service/{priv_id}")
            assert r_priv_detail.status_code == 404
            r_pub_detail = requests.get(f"{BASE_URL}/api/public/company/{DEMO_SLUG}/service/{pub_id}")
            assert r_pub_detail.status_code == 200
        finally:
            session.delete(f"{BASE_URL}/api/services/{priv_id}")
            session.delete(f"{BASE_URL}/api/services/{pub_id}")


# ============================================================================
# 9.3 — DnD order persistido + calendario ISO en fechas + PDF con _fmt_date
# ============================================================================
class TestBookingConfirmationDnDAndDates:
    def test_save_services_order_and_dates_persist(self, session, ganada_id):
        # GET current conf (or prefill)
        r = session.get(f"{BASE_URL}/api/quotations/{ganada_id}/booking-confirmation")
        assert r.status_code == 200
        base = r.json()
        # Build 3 services with ISO dates and specific order A→B→C
        services = [
            {"date": "2026-06-15", "service": "TEST_A_First", "details": "d1", "persons": "2", "observations": "o1"},
            {"date": "2026-06-16", "service": "TEST_B_Second", "details": "d2", "persons": "2", "observations": "o2"},
            {"date": "2026-06-17", "service": "TEST_C_Third", "details": "d3", "persons": "2", "observations": "o3"},
        ]
        payload = {
            "agent_name": base.get("agent_name", "") or "Test Agent",
            "agent_phone": base.get("agent_phone", ""),
            "agent_company": base.get("agent_company", ""),
            "agent_email": base.get("agent_email", ""),
            "reservation_date": "2026-06-10",
            "passenger_name": base.get("passenger_name", "") or "Test Passenger",
            "passenger_phone": base.get("passenger_phone", ""),
            "num_persons": base.get("num_persons", "2"),
            "services": services,
            "lodging": base.get("lodging") or [],
            "general_observations": base.get("general_observations", ""),
            "price_per_person": base.get("price_per_person", 0),
            "total_amount": base.get("total_amount", 0),
        }
        s1 = session.post(f"{BASE_URL}/api/quotations/{ganada_id}/booking-confirmation",
                          json=payload)
        assert s1.status_code == 200, s1.text
        saved = s1.json()
        assert [x["service"] for x in saved["services"]] == ["TEST_A_First", "TEST_B_Second", "TEST_C_Third"]
        # verify persisted order via fresh GET
        g = session.get(f"{BASE_URL}/api/quotations/{ganada_id}/booking-confirmation")
        assert g.status_code == 200
        assert [x["service"] for x in g.json()["services"]] == ["TEST_A_First", "TEST_B_Second", "TEST_C_Third"]

        # Now REORDER: C→A→B (simulates drag reorder)
        reordered = [services[2], services[0], services[1]]
        payload["services"] = reordered
        s2 = session.post(f"{BASE_URL}/api/quotations/{ganada_id}/booking-confirmation",
                          json=payload)
        assert s2.status_code == 200
        assert [x["service"] for x in s2.json()["services"]] == ["TEST_C_Third", "TEST_A_First", "TEST_B_Second"]
        # persist check
        g2 = session.get(f"{BASE_URL}/api/quotations/{ganada_id}/booking-confirmation")
        assert [x["service"] for x in g2.json()["services"]] == ["TEST_C_Third", "TEST_A_First", "TEST_B_Second"]
        # ISO dates preserved
        assert g2.json()["services"][0]["date"] == "2026-06-17"
        assert g2.json()["reservation_date"] == "2026-06-10"

    def test_pdf_download_200_and_dates_formatted(self, session, ganada_id):
        # ensure conf saved (previous test does this; but re-save to be safe)
        gc = session.get(f"{BASE_URL}/api/quotations/{ganada_id}/booking-confirmation")
        conf = gc.json()
        conf_id = conf.get("id")
        assert conf_id, "Confirmation must exist"
        r = session.get(f"{BASE_URL}/api/booking-confirmations/{conf_id}/pdf")
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert len(r.content) > 1000
        # Parse pdf and look for formatted date like "15 JUN" or "17 JUN"
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        # Since we saved reservation_date=2026-06-10 and service dates 2026-06-15/16/17,
        # backend _fmt_date should produce Spanish short form. Check any of the expected tokens.
        assert any(tok in text.upper() for tok in ["15 JUN", "16 JUN", "17 JUN", "10 JUN"]), \
            f"PDF debería contener fecha formateada, obtenido: {text[:500]}"
        # And should NOT contain raw ISO for those dates in reservation cell
        # (raw ISO would look like 2026-06-10; _fmt_date should convert it)
        assert "2026-06-10" not in text, "reservation_date debe estar formateado, no ISO crudo"


# ============================================================================
# Regression: precios de paquete NO tocados (guard)
# ============================================================================
class TestRegressionPackagePricing:
    def test_paquete_ganada_prices_still_valid(self, session, ganada_id):
        r = session.get(f"{BASE_URL}/api/quotations/{ganada_id}")
        assert r.status_code == 200
        q = r.json()
        # subtotal = sum(items.subtotal), total = subtotal + commission
        items = q.get("items", [])
        if items:
            sub = round(sum(float(i.get("subtotal", 0)) for i in items), 2)
            assert abs(sub - float(q.get("subtotal", 0))) < 0.5
            comm = float(q.get("commission", 0))
            assert abs((sub + comm) - float(q.get("total", 0))) < 0.5
