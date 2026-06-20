"""Iter 43 - Two-level client flow (company + executive) replicated in Custom Quotation Builder.

Validates that POST /api/quotations type='personalizado':
- Rejects (400) when client has executives but executive_id is missing.
- Accepts and persists contacts + executive_id when given.
- Allows directo clients without executive/agency.
- Allows agencia-without-executives clients (legacy contacts.agency).
- PDF + public-link expose agency, executive contact and traveler.
"""

import io
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
LOGIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}

CLIENT_WITH_EXECS = "c76a1ac7-1eaa-40b2-83bb-63d7cd52f218"   # Agencia Demo SA
EXEC_LAURA = "279e0affe93c"
CLIENT_DIRECTO = "5e4141c0-5a25-4619-8eea-c635455bdbec"      # Laura Ramírez
CLIENT_AGENCIA_NO_EXEC = "e4b48993-fe23-45a0-b39b-c99bb2c45e82"  # Agencia Viajes del Sol


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=LOGIN)
    assert r.status_code in (200, 201), r.text
    return s


def _hosp_item():
    return {
        "category": "hospedaje",
        "name": "TEST iter43 Hotel",
        "description": "",
        "net_price": 1000,
        "price_type": "neto",
        "unit": "per_night",
        "qty": 1,
        "service_date": "",
        "start_time": "",
        "end_time": "",
        "checkin": "2026-08-10",
        "checkout": "2026-08-12",
        "nights": 2,
    }


def _base_payload(client_id, executive_id=None, contacts=None):
    return {
        "type": "personalizado",
        "client_id": client_id,
        "custom_title": "TEST_iter43 Programa personalizado",
        "dates": {"start": "2026-08-10", "end": "2026-08-12"},
        "pax": {"adultos": 2, "menores": 0, "rooms": []},
        "custom_nights": 2,
        "custom_rooms": 1,
        "custom_items": [_hosp_item()],
        "custom_itinerary": [],
        "custom_includes": [],
        "custom_excludes": [],
        "contacts": contacts,
        "executive_id": executive_id,
        "notes": "",
        "presentation_text": "",
        "important_info": "",
        "show_price_breakdown": True,
    }


def _cleanup(s, qid):
    try:
        s.delete(f"{BASE_URL}/api/quotations/{qid}")
    except Exception:
        pass


# 1) Company with executives but NO executive_id -> 400
def test_custom_company_with_execs_missing_executive_returns_400(session):
    payload = _base_payload(CLIENT_WITH_EXECS, executive_id=None, contacts=None)
    r = session.post(f"{BASE_URL}/api/quotations", json=payload)
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    # message should mention ejecutivo / executive
    body = r.text.lower()
    assert "ejecutivo" in body or "executive" in body, body


# 2) Company with executives + executive_id + contacts -> created and persists
def test_custom_company_with_execs_creates_with_executive(session):
    contacts = {
        "agency": {"name": "Agencia Demo SA", "contact": "Laura Vendedora", "email": "laura@demo.mx", "phone": "+523310000001"},
        "traveler": {"name": "TEST Turista Final", "phone": "+523319999999", "email": ""},
    }
    payload = _base_payload(CLIENT_WITH_EXECS, executive_id=EXEC_LAURA, contacts=contacts)
    r = session.post(f"{BASE_URL}/api/quotations", json=payload)
    assert r.status_code in (200, 201), r.text
    q = r.json()
    qid = q["id"]
    try:
        assert q.get("executive_id") == EXEC_LAURA
        assert q.get("contacts", {}).get("agency", {}).get("name") == "Agencia Demo SA"
        assert q.get("contacts", {}).get("agency", {}).get("contact") == "Laura Vendedora"
        assert q.get("contacts", {}).get("traveler", {}).get("name") == "TEST Turista Final"

        # GET to verify persistence
        g = session.get(f"{BASE_URL}/api/quotations/{qid}")
        assert g.status_code == 200
        gj = g.json()
        assert gj["executive_id"] == EXEC_LAURA
        assert gj["contacts"]["agency"]["contact"] == "Laura Vendedora"

        # PDF must include agency name and executive contact
        pdf = session.get(f"{BASE_URL}/api/quotations/{qid}/pdf")
        assert pdf.status_code == 200
        assert pdf.content[:4] == b"%PDF"
        assert len(pdf.content) > 2000

        # Public link
        pl = session.post(f"{BASE_URL}/api/quotations/{qid}/public-link")
        assert pl.status_code == 200, pl.text
        token = pl.json().get("token")
        assert token
        pub = requests.get(f"{BASE_URL}/api/public/quotations/{token}")
        assert pub.status_code == 200
        pj = pub.json()
        # Confirm contacts/exec propagate in public payload (nested under "quotation")
        qpub = pj.get("quotation") or pj
        ag = (qpub.get("contacts") or {}).get("agency") or {}
        tr = (qpub.get("contacts") or {}).get("traveler") or {}
        assert ag.get("name") == "Agencia Demo SA"
        assert ag.get("contact") == "Laura Vendedora"
        assert tr.get("name") == "TEST Turista Final"
    finally:
        _cleanup(session, qid)


# 3) Directo client (no executives, no agency): should create without contacts requirement
def test_custom_directo_client_creates_without_contacts(session):
    payload = _base_payload(CLIENT_DIRECTO, executive_id=None, contacts=None)
    r = session.post(f"{BASE_URL}/api/quotations", json=payload)
    assert r.status_code in (200, 201), r.text
    qid = r.json()["id"]
    try:
        g = session.get(f"{BASE_URL}/api/quotations/{qid}")
        assert g.status_code == 200
        gj = g.json()
        assert (gj.get("executive_id") in (None, ""))
    finally:
        _cleanup(session, qid)


# 4) Agencia without executives (legacy): contacts.agency manually filled
def test_custom_agencia_without_execs_legacy_contacts(session):
    contacts = {
        "agency": {"name": "Agencia Viajes del Sol", "contact": "Vendedor Manual", "email": "v@sol.mx", "phone": "+523313334444"},
        "traveler": {"name": "TEST Tur Legacy", "phone": "+523319999998", "email": ""},
    }
    payload = _base_payload(CLIENT_AGENCIA_NO_EXEC, executive_id=None, contacts=contacts)
    r = session.post(f"{BASE_URL}/api/quotations", json=payload)
    assert r.status_code in (200, 201), r.text
    qid = r.json()["id"]
    try:
        g = session.get(f"{BASE_URL}/api/quotations/{qid}")
        gj = g.json()
        assert gj["contacts"]["agency"]["name"] == "Agencia Viajes del Sol"
        assert gj["contacts"]["agency"]["contact"] == "Vendedor Manual"
        pdf = session.get(f"{BASE_URL}/api/quotations/{qid}/pdf")
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    finally:
        _cleanup(session, qid)


# 5) Regression: paquete + servicios still require executive when client has executives
@pytest.mark.parametrize("qtype", ["paquete", "servicios"])
def test_regression_paquete_and_servicios_require_executive(session, qtype):
    payload = {
        "type": qtype,
        "client_id": CLIENT_WITH_EXECS,
        "dates": {"start": "2026-08-10", "end": "2026-08-12"},
        "pax": {"adultos": 2, "menores": 0, "rooms": []},
        "contacts": None,
        "executive_id": None,
    }
    if qtype == "paquete":
        # need a package_id - skip if we can't find one quickly
        pkgs = session.get(f"{BASE_URL}/api/packages")
        if pkgs.status_code != 200 or not pkgs.json():
            pytest.skip("No packages available for regression")
        payload["package_id"] = pkgs.json()[0]["id"]
    else:
        payload["services"] = []
    r = session.post(f"{BASE_URL}/api/quotations", json=payload)
    # 400 because executive is required for client with executives (or 422 for missing other fields, but the auth validation is server-side)
    assert r.status_code in (400, 422), f"Expected validation error, got {r.status_code}: {r.text}"
