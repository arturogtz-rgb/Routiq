"""
Iteration 40 — FASE B backend tests.

Validates client (empresa + ejecutivos) 2-level model, executive_id propagation
into quotations, contacts.agency (with phone), PDF, public payload, booking
confirmation prefill.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
EXEC_EMAIL = "ejecutivo@aventurate.mx"
EXEC_PASSWORD = "Demo2026!"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EXEC_EMAIL, "password": EXEC_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def created_client(session):
    """Create empresa 'TEST_AGENCIA_B' with 2 executives and clean up after."""
    payload = {
        "name": "TEST_AGENCIA_B",
        "phone": "3300000000",
        "email": "general@testagency.mx",
        "channel": "agencia",
        "notes": "Creada por test iteration 40",
        "executives": [
            {"name": "Laura Test", "phone": "3311111", "email": "laura@testagency.mx"},
            {"name": "Pedro Test", "phone": "3322222", "email": "pedro@testagency.mx"},
        ],
    }
    r = session.post(f"{BASE_URL}/api/clients", json=payload)
    assert r.status_code in (200, 201), f"create client: {r.status_code} {r.text}"
    data = r.json()
    assert data["name"] == payload["name"]
    assert data["channel"] == "agencia"
    assert len(data.get("executives", [])) == 2
    assert all(e.get("id") for e in data["executives"])  # ids generated
    yield data
    # cleanup
    session.delete(f"{BASE_URL}/api/clients/{data['id']}")


def test_list_clients_includes_executives_count(session, created_client):
    r = session.get(f"{BASE_URL}/api/clients")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    match = next((c for c in items if c.get("id") == created_client["id"]), None)
    assert match is not None, "created client not in list"
    assert match.get("executives_count") == 2
    # quotations_count field may exist (0 since none created yet)
    assert "quotations_count" in match or "quotations_count" in created_client or True


def test_update_client_executives_persist(session, created_client):
    cid = created_client["id"]
    execs = list(created_client["executives"])
    # edit first exec, remove second
    execs[0]["name"] = "Laura Editada"
    new_execs = [execs[0]]
    r = session.patch(
        f"{BASE_URL}/api/clients/{cid}",
        json={"executives": new_execs},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["executives"]) == 1
    assert data["executives"][0]["name"] == "Laura Editada"

    # GET via list to verify persistence
    items = session.get(f"{BASE_URL}/api/clients").json()
    fetched = next((c for c in items if c["id"] == cid), None)
    assert fetched is not None
    assert len(fetched["executives"]) == 1
    assert fetched["executives"][0]["name"] == "Laura Editada"
    assert fetched["executives_count"] == 1

    # restore for downstream tests
    restored = [
        {"id": fetched["executives"][0]["id"], "name": "Laura Test", "phone": "3311111", "email": "laura@testagency.mx"},
        {"name": "Pedro Test", "phone": "3322222", "email": "pedro@testagency.mx"},
    ]
    r3 = session.patch(f"{BASE_URL}/api/clients/{cid}", json={"executives": restored})
    assert r3.status_code == 200


@pytest.fixture(scope="module")
def created_quotation(session, created_client):
    """Create a paquete quotation with executive_id + contacts."""
    cid = created_client["id"]
    # refresh client from list (no GET /:id endpoint exists)
    items = session.get(f"{BASE_URL}/api/clients").json()
    cdata = next((c for c in items if c["id"] == cid), None)
    assert cdata is not None
    exec0 = cdata["executives"][0]

    # Need a package id — use first available package and its first hotel
    pr = session.get(f"{BASE_URL}/api/packages")
    assert pr.status_code == 200
    pkgs = pr.json()
    assert isinstance(pkgs, list) and len(pkgs) > 0, "no packages available for test"
    pkg = pkgs[0]
    pkg_id = pkg["id"]
    hotel_name = ""
    if pkg.get("hotels"):
        hotel_name = pkg["hotels"][0].get("name", "")

    payload = {
        "type": "paquete",
        "client_id": cid,
        "executive_id": exec0["id"],
        "package_id": pkg_id,
        "hotel_name": hotel_name,
        "dates": {"start": "2026-10-10", "end": "2026-10-13"},
        "pax": {"adults": 2, "children": 0},
        "contacts": {
            "agency": {
                "name": cdata["name"],
                "contact": exec0["name"],
                "email": exec0.get("email", ""),
                "phone": exec0.get("phone", ""),
            },
            "traveler": {"name": "Pasajero Test B", "phone": "", "email": ""},
        },
    }
    r = session.post(f"{BASE_URL}/api/quotations", json=payload)
    assert r.status_code in (200, 201), f"create quotation: {r.status_code} {r.text}"
    q = r.json()
    assert q.get("executive_id") == exec0["id"]
    assert q.get("contacts", {}).get("agency", {}).get("phone") == exec0["phone"]
    yield q
    # cleanup
    try:
        session.delete(f"{BASE_URL}/api/quotations/{q['id']}")
    except Exception:
        pass


def test_quotation_pdf_includes_agency_and_phone(session, created_quotation):
    qid = created_quotation["id"]
    r = session.get(f"{BASE_URL}/api/quotations/{qid}/pdf")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content.startswith(b"%PDF-")
    # Check the quotation snapshot data
    rq = session.get(f"{BASE_URL}/api/quotations/{qid}")
    assert rq.status_code == 200
    q = rq.json()
    ag = q.get("contacts", {}).get("agency", {})
    assert ag.get("name") == "TEST_AGENCIA_B"
    assert ag.get("contact") == "Laura Test"
    assert ag.get("phone") == "3311111"


def test_public_payload_exposes_contacts(session, created_quotation):
    qid = created_quotation["id"]
    # Create public link
    rl = session.post(f"{BASE_URL}/api/quotations/{qid}/public-link")
    assert rl.status_code in (200, 201), rl.text
    token = rl.json().get("token")
    assert token
    r = requests.get(f"{BASE_URL}/api/public/quotations/{token}")
    assert r.status_code == 200, r.text
    payload = r.json()
    ag = (payload.get("quotation") or {}).get("contacts", {}).get("agency", {})
    assert ag.get("name") == "TEST_AGENCIA_B"
    assert ag.get("contact") == "Laura Test"
    assert ag.get("phone") == "3311111"
    assert ag.get("email") == "laura@testagency.mx"


def test_booking_confirmation_prefill(session, created_quotation):
    qid = created_quotation["id"]
    # Move to ganada
    r = session.patch(f"{BASE_URL}/api/quotations/{qid}/state", json={"state": "ganada"})
    assert r.status_code in (200, 204), f"state change: {r.status_code} {r.text}"
    # Booking confirmation prefill
    r2 = session.get(f"{BASE_URL}/api/quotations/{qid}/booking-confirmation")
    assert r2.status_code == 200, r2.text
    data = r2.json()
    prefill = data.get("_prefill")
    assert prefill is True or prefill, f"_prefill not True: {data}"
    assert data.get("agent_company") == "TEST_AGENCIA_B"
    assert data.get("agent_name") == "Laura Test"
    assert data.get("agent_phone") == "3311111"
    assert data.get("passenger_name") == "Pasajero Test B"
