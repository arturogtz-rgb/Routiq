"""Iter 62 — Test resolución de destinatario del correo AL CLIENTE.
Cubre send-message, send-payment, y unit tests de _resolve_client_email.
"""
import os
import sys
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or pytest.skip("no backend url", allow_module_level=True)
API = f"{BASE}/api"

ADMIN_EMAIL = "admin@aventurate.mx"
ADMIN_PASS = "Demo2026!"

# --- Unit tests on _resolve_client_email (import in-process) ---
sys.path.insert(0, "/app/backend")
from deps import _resolve_client_email  # noqa: E402


class TestResolveClientEmailUnit:
    def test_directo_with_email(self):
        c = {"channel": "directo", "email": "d@x.com"}
        email, err = _resolve_client_email(c, {})
        assert email == "d@x.com" and err == ""

    def test_agency_executive_with_email(self):
        c = {"channel": "agencia", "email": "ceo@a.com",
             "executives": [{"id": "e1", "email": "exec@a.com"}]}
        q = {"executive_id": "e1"}
        email, err = _resolve_client_email(c, q)
        assert email == "exec@a.com" and err == ""
        assert email != "ceo@a.com"

    def test_agency_executive_no_email(self):
        c = {"channel": "agencia", "email": "ceo@a.com",
             "executives": [{"id": "e1", "email": ""}]}
        q = {"executive_id": "e1"}
        email, err = _resolve_client_email(c, q)
        assert email == "" and "ejecutivo asignado no tiene correo" in err.lower()

    def test_agency_no_executive_id(self):
        c = {"channel": "agencia", "email": "ceo@a.com",
             "executives": [{"id": "e1", "email": "exec@a.com"}]}
        email, err = _resolve_client_email(c, {})
        assert email == "" and "no hay un ejecutivo asignado" in err.lower()

    def test_directo_no_email(self):
        c = {"channel": "directo", "email": ""}
        email, err = _resolve_client_email(c, {})
        assert email == "" and "cliente no tiene correo" in err.lower()


# --- E2E fixtures ---
@pytest.fixture(scope="module")
def auth_headers():
    """Return a requests.Session-like object; app uses HttpOnly cookie auth."""
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def test_data(auth_headers):
    """Create direct client, agency client (with two executives), and quotations for each."""
    created = {"clients": [], "quotations": []}

    # Direct client
    r = auth_headers.post(f"{API}/clients", json={
        "name": "TEST_ClienteDirecto",
        "email": "TEST_directo@example.com",
        "phone": "5551234567",
        "channel": "directo",
    })
    assert r.status_code in (200, 201), f"create directo failed: {r.text}"
    direct_client = r.json()
    created["clients"].append(direct_client["id"])

    # Agency client with 2 executives (one with email, one without)
    r = auth_headers.post(f"{API}/clients", json={
        "name": "TEST_AgenciaXYZ",
        "email": "TEST_ceo@agencia.com",  # general/CEO email - should NEVER be used
        "phone": "5559999999",
        "channel": "agencia",
        "executives": [
            {"name": "Exec Con Email", "email": "TEST_exec@agencia.com", "phone": "5551111111"},
            {"name": "Exec Sin Email", "email": "", "phone": "5552222222"},
        ],
    })
    assert r.status_code in (200, 201), f"create agencia failed: {r.text}"
    agency_client = r.json()
    created["clients"].append(agency_client["id"])
    execs = agency_client.get("executives", [])
    assert len(execs) == 2
    exec_with_email = next(e for e in execs if e["email"])
    exec_no_email = next(e for e in execs if not e["email"])

    # Helper: create a minimal 'servicios' quotation
    # Fetch a service id to satisfy validation
    svc_r = auth_headers.get(f"{API}/services")
    assert svc_r.status_code == 200
    services_list = svc_r.json()
    assert services_list, "no services available for tenant"
    svc_id = services_list[0]["id"]

    def _create_quot(client_id, executive_id=None):
        payload = {
            "client_id": client_id,
            "type": "servicios",
            "services": [{"service_id": svc_id, "qty": 1}],
        }
        if executive_id is not None:
            payload["executive_id"] = executive_id
        r = auth_headers.post(f"{API}/quotations", json=payload)
        assert r.status_code in (200, 201), f"create quotation failed: {r.text}"
        return r.json()

    q_direct = _create_quot(direct_client["id"])
    q_agency_with = _create_quot(agency_client["id"], executive_id=exec_with_email["id"])
    q_agency_without = _create_quot(agency_client["id"], executive_id=exec_no_email["id"])

    # For "no executive_id" case: create a separate agency client with EMPTY executives so
    # the create-quotation validation is skipped and we can produce a quotation without executive_id.
    r = auth_headers.post(f"{API}/clients", json={
        "name": "TEST_AgenciaSinEjec",
        "email": "TEST_ceo2@agencia.com",
        "phone": "5558888888",
        "channel": "agencia",
        "executives": [],
    })
    assert r.status_code in (200, 201), r.text
    agency_no_execs = r.json()
    created["clients"].append(agency_no_execs["id"])
    q_agency_none = _create_quot(agency_no_execs["id"], executive_id=None)

    created["quotations"].extend([q_direct["id"], q_agency_with["id"], q_agency_without["id"], q_agency_none["id"]])

    yield {
        "direct_client": direct_client,
        "agency_client": agency_client,
        "exec_with_email": exec_with_email,
        "exec_no_email": exec_no_email,
        "q_direct": q_direct,
        "q_agency_with": q_agency_with,
        "q_agency_without": q_agency_without,
        "q_agency_none": q_agency_none,
    }

    # Cleanup
    for qid in created["quotations"]:
        auth_headers.delete(f"{API}/quotations/{qid}")
    for cid in created["clients"]:
        auth_headers.delete(f"{API}/clients/{cid}")


class TestSendMessage:
    """POST /api/quotations/{id}/send-message — validates resolved `to` and errors."""

    def test_directo_uses_client_email(self, auth_headers, test_data):
        qid = test_data["q_direct"]["id"]
        r = auth_headers.post(f"{API}/quotations/{qid}/send-message",
                          json={"text": "Hola cliente", "kind": "followup"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("to") == "TEST_directo@example.com"

    def test_agencia_uses_executive_email_not_general(self, auth_headers, test_data):
        qid = test_data["q_agency_with"]["id"]
        r = auth_headers.post(f"{API}/quotations/{qid}/send-message",
                          json={"text": "Hola ejecutivo", "kind": "followup"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("to") == "TEST_exec@agencia.com"
        # CRITICAL: never the general/CEO email
        assert data.get("to") != "TEST_ceo@agencia.com"

    def test_agencia_executive_no_email_returns_400(self, auth_headers, test_data):
        qid = test_data["q_agency_without"]["id"]
        r = auth_headers.post(f"{API}/quotations/{qid}/send-message",
                          json={"text": "Hola", "kind": "followup"})
        assert r.status_code == 400, r.text
        detail = (r.json().get("detail") or "").lower()
        assert "ejecutivo asignado no tiene correo" in detail
        # NEVER falls back to CEO email
        assert "TEST_ceo@agencia.com" not in r.text

    def test_agencia_no_executive_id_returns_400(self, auth_headers, test_data):
        qid = test_data["q_agency_none"]["id"]
        r = auth_headers.post(f"{API}/quotations/{qid}/send-message",
                          json={"text": "Hola", "kind": "followup"})
        assert r.status_code == 400, r.text
        detail = (r.json().get("detail") or "").lower()
        assert "ejecutivo asignado" in detail


class TestSendPayment:
    """POST /api/quotations/{id}/send-payment — mismo comportamiento de resolución."""

    def test_directo_resolves_client_email(self, auth_headers, test_data):
        qid = test_data["q_direct"]["id"]
        r = auth_headers.post(f"{API}/quotations/{qid}/send-payment",
                          json={"public_url": "https://example.com"})
        assert r.status_code == 200, r.text
        assert r.json().get("to") == "TEST_directo@example.com"

    def test_agencia_resolves_executive_email(self, auth_headers, test_data):
        qid = test_data["q_agency_with"]["id"]
        r = auth_headers.post(f"{API}/quotations/{qid}/send-payment",
                          json={"public_url": "https://example.com"})
        assert r.status_code == 200, r.text
        assert r.json().get("to") == "TEST_exec@agencia.com"
        assert r.json().get("to") != "TEST_ceo@agencia.com"

    def test_agencia_no_exec_email_returns_400(self, auth_headers, test_data):
        qid = test_data["q_agency_without"]["id"]
        r = auth_headers.post(f"{API}/quotations/{qid}/send-payment",
                          json={"public_url": "https://example.com"})
        assert r.status_code == 400, r.text
        detail = (r.json().get("detail") or "").lower()
        assert "ejecutivo asignado no tiene correo" in detail

    def test_explicit_to_email_is_respected(self, auth_headers, test_data):
        qid = test_data["q_agency_without"]["id"]  # would 400 otherwise
        r = auth_headers.post(f"{API}/quotations/{qid}/send-payment",
                          json={"public_url": "https://example.com", "to_email": "explicit@x.com"})
        assert r.status_code == 200, r.text
        assert r.json().get("to") == "explicit@x.com"
