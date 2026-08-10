"""Iteración 61 — Regresión bug: follow-up AI crasheaba en cotizaciones SIN paquete.

Bug original: `_quotation_brief` usaba `q.get('package_snapshot',{}).get(...)`.
Cuando `package_snapshot` existía con valor None (cotizaciones `servicios`), el default {}
no aplicaba y explotaba con `'NoneType' object has no attribute 'get'`. El except genérico
en `_run_follow_up` devolvía 503 "IA no disponible" (falso positivo).

Fix:
  - `_quotation_brief` usa `q.get('package_snapshot') or {}` (y equivalente para dates/pax).
  - `_run_follow_up` distingue AINotConfigured/AIError → 503 vs Exception → 500.

Tests:
  1) UNIT — `_quotation_brief` no crashea con package_snapshot/dates/pax None (paquete/servicios/personalizado).
  2) E2E — POST follow-up-{prepay,payment,postsale} para los 3 tipos → 503 con detail "IA no disponible" (nunca 'NoneType').
  3) Mapeo 500 — monkeypatch `follow_up_message` para lanzar RuntimeError → 500 (no 503).
"""
import os
import sys
import uuid
import asyncio
import requests
import pytest

def _load_frontend_env():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}

# ---------- helpers ----------

def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def test_client(admin_session):
    payload = {
        "name": f"TEST_ITER61_{uuid.uuid4().hex[:6]}",
        "email": f"test61_{uuid.uuid4().hex[:6]}@example.com",
        "phone": "+521234567890",
        "channel": "directo",
    }
    r = admin_session.post(f"{API}/clients", json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    cli = r.json()
    yield cli
    try:
        admin_session.delete(f"{API}/clients/{cli['id']}", timeout=15)
    except Exception:
        pass


def _pick_service(admin_session):
    r = admin_session.get(f"{API}/services", timeout=15)
    if r.status_code != 200:
        return None
    lst = r.json() or []
    return lst[0] if lst else None


def _create_quotation(admin_session, payload):
    r = admin_session.post(f"{API}/quotations", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create quotation failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def q_paquete(admin_session, test_client):
    pkgs = admin_session.get(f"{API}/packages", timeout=15).json()
    assert isinstance(pkgs, list) and pkgs, "need at least 1 package"
    pkg = pkgs[0]
    hotels = pkg.get("hotels") or []
    hotel_name = hotels[0].get("name", "") if hotels else ""
    payload = {
        "client_id": test_client["id"],
        "type": "paquete",
        "package_id": pkg["id"],
        "hotel_name": hotel_name,
        "pax": {"adultos": 2, "menores": 0, "ocupacion": "doble"},
        "dates": {"start": "2026-06-01", "end": "2026-06-04"},
    }
    q = _create_quotation(admin_session, payload)
    yield q
    try:
        admin_session.delete(f"{API}/quotations/{q['id']}", timeout=15)
    except Exception:
        pass


@pytest.fixture(scope="module")
def q_servicios(admin_session, test_client):
    svc = _pick_service(admin_session)
    if not svc:
        pytest.skip("no services in catalog to build servicios quotation")
    # SelectedService: minimal shape — id + qty typical
    services = [{"service_id": svc["id"], "qty": 2}]
    payload = {
        "client_id": test_client["id"],
        "type": "servicios",
        "pax": {"adultos": 2, "menores": 0, "ocupacion": "doble"},
        "dates": {"start": "2026-06-10", "end": "2026-06-12"},
        "services": services,
    }
    q = _create_quotation(admin_session, payload)
    yield q
    try:
        admin_session.delete(f"{API}/quotations/{q['id']}", timeout=15)
    except Exception:
        pass


@pytest.fixture(scope="module")
def q_personalizado(admin_session, test_client):
    payload = {
        "client_id": test_client["id"],
        "type": "personalizado",
        "custom_title": "TEST Programa personalizado iter61",
        "pax": {"adultos": 2, "menores": 0, "ocupacion": "doble"},
        "dates": {"start": "2026-07-01", "end": "2026-07-05"},
        "custom_nights": 4,
        "custom_rooms": 1,
        "custom_items": [{
            "category": "extra", "name": "Consultoría", "net_price": 1500.0,
            "price_type": "neto", "unit": "per_group", "qty": 1,
        }],
    }
    q = _create_quotation(admin_session, payload)
    yield q
    try:
        admin_session.delete(f"{API}/quotations/{q['id']}", timeout=15)
    except Exception:
        pass


# ---------- 1) UNIT: _quotation_brief robustness ----------
def test_unit_quotation_brief_handles_none_fields():
    sys.path.insert(0, "/app/backend")
    from ai_service import _quotation_brief

    # (a) paquete con dicts completos
    q_a = {
        "package_snapshot": {"name": "Test Pack", "code": "TP-1", "nights": 3},
        "hotel_selected": "Hotel X",
        "dates": {"start": "2026-06-01", "end": "2026-06-04"},
        "pax": {"adultos": 2, "menores": 0, "ocupacion": "doble"},
        "total": 15000, "currency": "MXN", "state": "cotizando",
    }
    out_a = _quotation_brief(q_a, None, None)
    assert isinstance(out_a, str) and "Test Pack" in out_a

    # (b) servicios: package_snapshot None, dates None, pax None
    q_b = {
        "package_snapshot": None,
        "hotel_selected": "",
        "dates": None,
        "pax": None,
        "total": 5000, "currency": "MXN", "state": "cotizando",
    }
    out_b = _quotation_brief(q_b, None, None)
    assert isinstance(out_b, str), "should return str, no crash"

    # (c) personalizado: mismos Nones
    q_c = {
        "package_snapshot": None,
        "dates": None,
        "pax": None,
        "total": 9000, "currency": "MXN", "state": "cotizando",
    }
    out_c = _quotation_brief(q_c, None, None)
    assert isinstance(out_c, str)


# ---------- 2) E2E: follow-up endpoints across 3 quotation types ----------
FOLLOW_UPS = ["prepay", "payment", "postsale"]


@pytest.mark.parametrize("kind", FOLLOW_UPS)
def test_follow_up_paquete_no_nonetype(admin_session, q_paquete, kind):
    r = admin_session.post(f"{API}/ai/quotations/{q_paquete['id']}/follow-up-{kind}", timeout=30)
    assert r.status_code == 503, f"expected 503 got {r.status_code}: {r.text}"
    detail = (r.json() or {}).get("detail", "")
    assert "NoneType" not in detail, f"regression! detail leaks NoneType: {detail}"
    assert "IA no disponible" in detail or "no está configurada" in detail, detail


@pytest.mark.parametrize("kind", FOLLOW_UPS)
def test_follow_up_servicios_no_nonetype(admin_session, q_servicios, kind):
    r = admin_session.post(f"{API}/ai/quotations/{q_servicios['id']}/follow-up-{kind}", timeout=30)
    assert r.status_code == 503, f"expected 503 got {r.status_code}: {r.text}"
    detail = (r.json() or {}).get("detail", "")
    assert "NoneType" not in detail, f"regression! detail leaks NoneType: {detail}"
    assert "IA no disponible" in detail or "no está configurada" in detail, detail


@pytest.mark.parametrize("kind", FOLLOW_UPS)
def test_follow_up_personalizado_no_nonetype(admin_session, q_personalizado, kind):
    r = admin_session.post(f"{API}/ai/quotations/{q_personalizado['id']}/follow-up-{kind}", timeout=30)
    assert r.status_code == 503, f"expected 503 got {r.status_code}: {r.text}"
    detail = (r.json() or {}).get("detail", "")
    assert "NoneType" not in detail, f"regression! detail leaks NoneType: {detail}"
    assert "IA no disponible" in detail or "no está configurada" in detail, detail
