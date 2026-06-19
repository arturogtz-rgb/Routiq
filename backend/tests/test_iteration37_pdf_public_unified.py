"""
Iteration 37 — PDF + Public quotation unified breakdown
- PDF endpoint returns 200 + application/pdf + %PDF binary (ejecutivo + admin, at least one package + one custom)
- Public endpoint exposes quotation.items (used for unified breakdown), price_note, and itinerary
- show_all_occupancies=false → occupancy_prices is empty
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')

EXEC_CREDS = {"email": "ejecutivo@aventurate.mx", "password": "Demo2026!"}
ADMIN_CREDS = {"email": "admin@aventurate.mx", "password": "Demo2026!"}

TOKEN_CUSTOM = "JX4Q1xHuqEgQ92QH45Z_rMfI"      # personalizado COT-2026011
TOKEN_PACKAGE_NO_SHOW_ALL = "E4cWS--ucnOiioZotwHcD8OM"  # paquete show_all=false


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


def _list_quotations(session):
    r = session.get(f"{BASE_URL}/api/quotations", timeout=20)
    assert r.status_code == 200, f"list quotations failed: {r.status_code}"
    data = r.json()
    return data if isinstance(data, list) else data.get("items", data.get("quotations", []))


def _pick_one_by_type(quotations, qtype):
    """Return first quotation with given type ('paquete' or other)."""
    for q in quotations:
        t = (q.get("type") or "").lower()
        if qtype == "paquete" and t == "paquete":
            return q
        if qtype == "custom" and t in ("personalizada", "servicios", "custom"):
            return q
    return None


# ---------------------------- PDF ENDPOINT ----------------------------

@pytest.fixture(scope="module")
def exec_session():
    return _login(EXEC_CREDS)


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN_CREDS)


def _assert_pdf_response(resp):
    assert resp.status_code == 200, f"status={resp.status_code} body={resp.content[:200]!r}"
    ctype = resp.headers.get("content-type", "")
    assert "application/pdf" in ctype, f"content-type={ctype}"
    assert resp.content[:4] == b"%PDF", f"magic={resp.content[:8]!r}"
    assert len(resp.content) > 1000, f"pdf too small: {len(resp.content)}"


def test_exec_pdf_package(exec_session):
    qs = _list_quotations(exec_session)
    assert qs, "no quotations available for executive"
    pkg = _pick_one_by_type(qs, "paquete")
    if not pkg:
        pytest.skip("no package quotation visible to executive")
    r = exec_session.get(f"{BASE_URL}/api/quotations/{pkg['id']}/pdf", timeout=30)
    _assert_pdf_response(r)


def test_exec_pdf_custom(exec_session):
    qs = _list_quotations(exec_session)
    assert qs
    custom = _pick_one_by_type(qs, "custom")
    if not custom:
        pytest.skip("no custom quotation visible to executive")
    r = exec_session.get(f"{BASE_URL}/api/quotations/{custom['id']}/pdf", timeout=30)
    _assert_pdf_response(r)


def test_admin_pdf_package(admin_session):
    qs = _list_quotations(admin_session)
    assert qs
    pkg = _pick_one_by_type(qs, "paquete")
    if not pkg:
        pytest.skip("no package quotation visible to admin")
    r = admin_session.get(f"{BASE_URL}/api/quotations/{pkg['id']}/pdf", timeout=30)
    _assert_pdf_response(r)


def test_admin_pdf_custom(admin_session):
    qs = _list_quotations(admin_session)
    assert qs
    custom = _pick_one_by_type(qs, "custom")
    if not custom:
        pytest.skip("no custom quotation visible to admin")
    r = admin_session.get(f"{BASE_URL}/api/quotations/{custom['id']}/pdf", timeout=30)
    _assert_pdf_response(r)


# ---------------------------- PUBLIC ENDPOINT ----------------------------

def test_public_custom_loads_and_has_items():
    r = requests.get(f"{BASE_URL}/api/public/quotations/{TOKEN_CUSTOM}", timeout=20)
    assert r.status_code == 200, f"public load failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert "quotation" in data
    q = data["quotation"]
    # essential fields for unified breakdown
    assert isinstance(q.get("items"), list), "quotation.items missing or not a list"
    assert len(q["items"]) >= 1, "expected at least 1 line item for unified breakdown"
    # each item has label and subtotal so frontend can render public-line-item-{i}
    for it in q["items"]:
        assert "label" in it
        assert "subtotal" in it
    # totals
    assert q.get("total") is not None or q.get("final_total") is not None
    assert q.get("currency")
    # client name for greeting
    assert q.get("client_name"), "client_name needed for greeting"


def test_public_custom_has_itinerary_top_level():
    r = requests.get(f"{BASE_URL}/api/public/quotations/{TOKEN_CUSTOM}", timeout=20)
    assert r.status_code == 200
    data = r.json()
    itin = data.get("itinerary") or []
    assert isinstance(itin, list)
    assert len(itin) >= 1, "expected itinerary with >=1 day for public-itinerary section"


def test_public_package_no_show_all_has_empty_occupancy():
    r = requests.get(f"{BASE_URL}/api/public/quotations/{TOKEN_PACKAGE_NO_SHOW_ALL}", timeout=20)
    assert r.status_code == 200
    data = r.json()
    q = data["quotation"]
    occ = q.get("occupancy_prices") or []
    assert occ == [], f"expected empty occupancy_prices when show_all_occupancies=false, got {occ}"
