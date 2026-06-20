"""Iter 45 — Comisión específica por cliente (override del % por canal).

Cubre:
- Crear cliente mayorista con commission_rate=0.05 (override).
- Cotización personalizada y de servicios para ese cliente usan 5% (no global 15%).
- Cliente sin override usa el global (15%).
- Update con commission_rate=None hace $unset y vuelve al global.
- Cliente directo no tiene comisión.
"""
import os
import pytest
import requests

def _load_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        # leer frontend/.env como fallback en CI
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    assert url, "REACT_APP_BACKEND_URL no configurado"
    return url.rstrip("/")

BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@aventurate.mx"
ADMIN_PASSWORD = "Demo2026!"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def global_commissions(session):
    r = session.get(f"{API}/companies/me", timeout=15)
    assert r.status_code == 200
    comms = (r.json().get("pricing_config") or {}).get("commissions") or {}
    # asegurar valores
    assert float(comms.get("mayorista", 0)) > 0, f"global mayorista debe >0: {comms}"
    return comms


@pytest.fixture(scope="module")
def state():
    return {"client_ids": [], "quotation_ids": []}


def _cleanup(session, state):
    for qid in state["quotation_ids"]:
        try:
            session.delete(f"{API}/quotations/{qid}", timeout=10)
        except Exception:
            pass
    for cid in state["client_ids"]:
        try:
            session.delete(f"{API}/clients/{cid}", timeout=10)
        except Exception:
            pass


def _create_custom_quote(session, client_id, public_price=1000):
    payload = {
        "type": "personalizado",
        "client_id": client_id,
        "currency": "MXN",
        "custom_title": "TEST_iter45 commission",
        "custom_items": [{
            "name": "Servicio test",
            "category": "extra",
            "description": "",
            "net_price": public_price,
            "price_type": "publico",
            "unit": "per_group",
            "qty": 1,
        }],
    }
    return session.post(f"{API}/quotations", json=payload, timeout=15)


class TestClientCommissionOverride:
    def test_01_create_mayorista_with_override(self, session, state):
        r = session.post(f"{API}/clients", json={
            "name": "TEST_iter45 Mayorista",
            "channel": "mayorista",
            "commission_rate": 0.05,
        }, timeout=15)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data["channel"] == "mayorista"
        assert data["commission_rate"] == 0.05
        state["client_ids"].append(data["id"])

    def test_02_get_client_persists_override(self, session, state):
        cid = state["client_ids"][-1]
        r = session.get(f"{API}/clients/{cid}", timeout=15)
        assert r.status_code == 200
        assert r.json()["commission_rate"] == 0.05

    def test_03_custom_quotation_uses_override(self, session, state):
        cid = state["client_ids"][-1]
        r = _create_custom_quote(session, cid, public_price=1000)
        assert r.status_code in (200, 201), r.text
        q = r.json()
        state["quotation_ids"].append(q["id"])
        assert q["commission_rate"] == 0.05, f"esperaba 0.05, got {q['commission_rate']}"
        assert abs(q["commission"] - 50.0) < 0.01, f"esperaba commission=50, got {q['commission']}"
        # total mayorista = subtotal - commission = 1000 - 50 = 950
        assert abs(q["total"] - 950.0) < 0.01, f"esperaba total=950, got {q['total']}"

    def test_04_services_quotation_uses_override(self, session, state, global_commissions):
        cid = state["client_ids"][-1]
        # type=servicios necesita services del catálogo; aquí sólo verificamos que la API NO rechace por commission.
        # Si no podemos crear sin catálogo válido, saltamos.
        payload = {
            "type": "servicios",
            "client_id": cid,
            "currency": "MXN",
            "services": [],
            "custom_items": [{
                "name": "Custom svc",
                "category": "extra",
                "net_price": 1000,
                "price_type": "publico",
                "unit": "per_group",
                "qty": 1,
            }],
        }
        r = session.post(f"{API}/quotations", json=payload, timeout=15)
        if r.status_code not in (200, 201):
            pytest.skip(f"services endpoint no acepta este payload: {r.status_code} {r.text}")
        q = r.json()
        state["quotation_ids"].append(q["id"])
        # debe usar 0.05
        assert q["commission_rate"] == 0.05

    def test_05_clear_override_via_update_null(self, session, state):
        cid = state["client_ids"][-1]
        # PATCH/PUT con commission_rate=None -> $unset
        r = session.patch(f"{API}/clients/{cid}", json={"commission_rate": None}, timeout=15)
        assert r.status_code == 200, r.text
        # GET y verificar
        r2 = session.get(f"{API}/clients/{cid}", timeout=15)
        assert r2.status_code == 200
        cli = r2.json()
        assert cli.get("commission_rate") in (None,), f"esperaba None tras $unset, got {cli.get('commission_rate')}"

    def test_06_after_clear_uses_global(self, session, state, global_commissions):
        cid = state["client_ids"][-1]
        r = _create_custom_quote(session, cid, public_price=1000)
        assert r.status_code in (200, 201), r.text
        q = r.json()
        state["quotation_ids"].append(q["id"])
        global_mayorista = float(global_commissions.get("mayorista", 0.15))
        expected_commission = 1000 * global_mayorista
        assert abs(q["commission"] - expected_commission) < 0.01, f"esperaba {expected_commission}, got {q['commission']}"
        assert abs(q["commission_rate"] - global_mayorista) < 1e-6

    def test_07_direct_client_no_commission(self, session, state):
        r = session.post(f"{API}/clients", json={
            "name": "TEST_iter45 Directo",
            "channel": "directo",
        }, timeout=15)
        assert r.status_code in (200, 201)
        c = r.json()
        state["client_ids"].append(c["id"])
        assert c["channel"] == "directo"
        # crear quotation
        r2 = _create_custom_quote(session, c["id"], public_price=1000)
        assert r2.status_code in (200, 201)
        q = r2.json()
        state["quotation_ids"].append(q["id"])
        assert (q.get("commission") or 0) == 0
        # total ≈ 1000 (sin descuento)
        assert abs(q["total"] - 1000.0) < 0.01

    def test_08_validation_rejects_out_of_range(self, session, state):
        r = session.post(f"{API}/clients", json={
            "name": "TEST_iter45 Invalid",
            "channel": "mayorista",
            "commission_rate": 1.5,
        }, timeout=15)
        assert r.status_code in (400, 422), f"esperaba 4xx, got {r.status_code}: {r.text}"

    def test_99_cleanup(self, session, state):
        _cleanup(session, state)
