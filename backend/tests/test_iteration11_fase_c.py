"""Iteration 11 — Fase C regression: bank config + public payment options +
manual mark-paid + send-to-charge + audit mini-dashboard."""
import os
import requests
import pytest
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}


# ---------- session fixtures ----------
@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def seed(admin):
    """Find a client + a package to build a quotation against."""
    clients = admin.get(f"{API}/clients", timeout=10).json()
    pkgs = admin.get(f"{API}/packages", timeout=10).json()
    assert clients and pkgs, "Need at least one client and one package"
    return {"client": clients[0], "package": pkgs[0]}


# ---------- 1. Bank settings persistence ----------
def test_bank_integration_save_and_persist(admin):
    payload = {
        "bank_enabled": True,
        "bank_name": "BBVA México",
        "bank_holder": "Aventúrate por Jalisco SA de CV",
        "bank_clabe": "012345678901234567",
        "bank_account": "0123456789",
        "bank_usd_account": "9876543210",
        "bank_swift": "BCMRMXMM",
        "bank_aba": "026009593",
        "bank_address": "Av. Vallarta 1000, Guadalajara, Jalisco",
    }
    r = admin.patch(f"{API}/companies/me/integrations", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    for k, v in payload.items():
        assert body.get(k) == v, f"{k} not persisted: got {body.get(k)!r}"

    # reload via GET
    r2 = admin.get(f"{API}/companies/me/integrations", timeout=10)
    assert r2.status_code == 200
    g = r2.json()
    assert g["bank_enabled"] is True
    assert g["bank_clabe"] == payload["bank_clabe"]
    assert g["bank_usd_account"] == payload["bank_usd_account"]


# ---------- 2. Public quotation exposes transfer + bank ----------
@pytest.fixture(scope="module")
def package_quotation(admin, seed):
    client = seed["client"]
    pkg = seed["package"]
    body = {
        "client_id": client["id"], "type": "paquete", "package_id": pkg["id"],
        "hotel_name": (pkg.get("hotels") or [{}])[0].get("name", ""),
        "dates": {"start": "2026-04-01", "end": "2026-04-04"},
        "pax": {"adults": 2, "children": 0},
        "services": [],
    }
    r = admin.post(f"{API}/quotations", json=body, timeout=15)
    assert r.status_code == 201, r.text
    q = r.json()
    # ensure public link
    r2 = admin.post(f"{API}/quotations/{q['id']}/public-link", timeout=10)
    assert r2.status_code == 200, r2.text
    q["token"] = r2.json()["token"]
    yield q
    # cleanup
    admin.delete(f"{API}/quotations/{q['id']}", timeout=10)


def test_public_quotation_exposes_bank_and_transfer(package_quotation):
    token = package_quotation["token"]
    r = requests.get(f"{API}/public/quotations/{token}", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    pay = data["payment"]
    assert pay["enabled"] is True, "Stripe should be enabled (demo key)"
    assert pay["transfer_enabled"] is True, "bank.enabled True after save"
    assert pay["bank"] is not None
    assert pay["bank"]["clabe"] == "012345678901234567"
    assert pay["bank"]["name"] == "BBVA México"
    # servicios guard sanity: package quotation has package_snapshot
    assert data["quotation"]["package_snapshot"] is not None


def test_request_transfer_endpoint(package_quotation):
    token = package_quotation["token"]
    r = requests.post(f"{API}/public/quotations/{token}/request-transfer", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert "email_sent" in body  # may be False (Resend not configured) — that's fine
    assert body["bank"]["clabe"] == "012345678901234567"


# ---------- 3. Manual mark-paid (partial then full) ----------
def test_mark_paid_partial_then_full(admin, seed):
    client = seed["client"]
    pkg = seed["package"]
    # include a service to guarantee non-zero total
    services = admin.get(f"{API}/services", timeout=10).json()
    svc_payload = [{"service_id": services[0]["id"], "qty_per_person": 1}] if services else []
    body = {
        "client_id": client["id"], "type": "paquete", "package_id": pkg["id"],
        "hotel_name": (pkg.get("hotels") or [{}])[0].get("name", ""),
        "dates": {"start": "2026-05-01", "end": "2026-05-03"},
        "pax": {"adults": 2, "children": 0}, "services": svc_payload,
    }
    r = admin.post(f"{API}/quotations", json=body, timeout=15)
    assert r.status_code == 201, r.text
    q = r.json()
    qid = q["id"]
    final_total = q.get("final_total") or q.get("total")
    assert final_total and final_total > 0

    try:
        # partial
        half = round(final_total / 2, 2)
        r1 = admin.patch(f"{API}/quotations/{qid}/mark-paid",
                         json={"amount": half, "method": "transfer", "note": "anticipo TEST"},
                         timeout=15)
        assert r1.status_code == 200, r1.text
        upd = r1.json()
        assert upd["payment_status"] == "partial"
        assert upd["state"] == "ganada", "partial payment moves state to ganada"
        assert abs(upd["amount_paid"] - half) < 0.05

        # history entry
        det = admin.get(f"{API}/quotations/{qid}", timeout=10).json()
        history_kinds = [h.get("action") for h in det.get("history", [])]
        assert "payment" in history_kinds

        # full remaining
        remaining = round(final_total - half, 2)
        r2 = admin.patch(f"{API}/quotations/{qid}/mark-paid",
                         json={"amount": remaining, "method": "transfer"}, timeout=15)
        assert r2.status_code == 200, r2.text
        upd2 = r2.json()
        assert upd2["payment_status"] == "paid"
        assert upd2["state"] == "ganada"

        # audit 'won' present
        audit = admin.get(f"{API}/audit-log", params={"action": "won"}, timeout=10).json()
        assert any(a.get("quotation_id") == qid for a in audit), "won audit entry missing"
    finally:
        admin.delete(f"{API}/quotations/{qid}", timeout=10)


# ---------- 4. Send payment link ----------
def test_send_payment_link(admin, seed):
    client = seed["client"]
    pkg = seed["package"]
    body = {
        "client_id": client["id"], "type": "paquete", "package_id": pkg["id"],
        "hotel_name": (pkg.get("hotels") or [{}])[0].get("name", ""),
        "dates": {"start": "2026-06-01", "end": "2026-06-03"},
        "pax": {"adults": 2, "children": 0}, "services": [],
        "contacts": {"traveler_name": "Test Cliente", "traveler_email": "cliente.test@example.com",
                     "traveler_phone": "5512345678"},
    }
    r = admin.post(f"{API}/quotations", json=body, timeout=15)
    assert r.status_code == 201, r.text
    q = r.json()
    qid = q["id"]
    try:
        r1 = admin.post(f"{API}/quotations/{qid}/send-payment",
                        json={"channel": "email", "to_email": "cliente.test@example.com",
                              "public_url": "https://neto-a-publico.preview.emergentagent.com"},
                        timeout=15)
        assert r1.status_code == 200, r1.text
        body = r1.json()
        assert body["ok"] is True
        assert body["link"].startswith("https://neto-a-publico.preview.emergentagent.com/q/")
        # email_sent may be False (Resend not configured) — link must still be returned
        assert "email_sent" in body
    finally:
        admin.delete(f"{API}/quotations/{qid}", timeout=10)


# ---------- 5. Post-acceptance flow (public accept) ----------
def test_public_accept_records_won_audit(admin, seed):
    client = seed["client"]
    pkg = seed["package"]
    body = {
        "client_id": client["id"], "type": "paquete", "package_id": pkg["id"],
        "hotel_name": (pkg.get("hotels") or [{}])[0].get("name", ""),
        "dates": {"start": "2026-07-01", "end": "2026-07-03"},
        "pax": {"adults": 2, "children": 0}, "services": [],
    }
    r = admin.post(f"{API}/quotations", json=body, timeout=15)
    q = r.json(); qid = q["id"]
    try:
        tok = admin.post(f"{API}/quotations/{qid}/public-link", timeout=10).json()["token"]
        r2 = requests.post(f"{API}/public/quotations/{tok}/accept", timeout=15)
        assert r2.status_code == 200, r2.text
        # state ganada
        det = admin.get(f"{API}/quotations/{qid}", timeout=10).json()
        assert det["state"] == "ganada"
        # won audit
        audit = admin.get(f"{API}/audit-log", params={"action": "won"}, timeout=10).json()
        assert any(a.get("quotation_id") == qid for a in audit)
    finally:
        admin.delete(f"{API}/quotations/{qid}", timeout=10)


# ---------- 6. Audit mini-dashboard ----------
def test_metrics_audit(admin):
    r = admin.get(f"{API}/metrics/audit", timeout=10)
    assert r.status_code == 200, r.text
    m = r.json()
    for k in ("won_this_month", "won_total", "amount_recovered", "currency"):
        assert k in m, f"missing {k}"
    assert isinstance(m["won_this_month"], int)
    assert isinstance(m["amount_recovered"], (int, float))
    # top_executive may be None if no won quotations; structurally we accept either
    assert "top_executive" in m


def test_metrics_audit_forbidden_for_executive():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": "ejecutivo@aventurate.mx", "password": "Demo2026!"}, timeout=10)
    assert r.status_code == 200
    r2 = s.get(f"{API}/metrics/audit", timeout=10)
    assert r2.status_code == 403


# ---------- 7. Servicios public link still renders (Fase B regression) ----------
def test_servicios_quotation_public_link_renders(admin, seed):
    # find any agencia client + first available service
    clients = admin.get(f"{API}/clients", timeout=10).json()
    agency = next((c for c in clients if c.get("channel") == "agencia"), None) or seed["client"]
    services = admin.get(f"{API}/services", timeout=10).json()
    if not services:
        pytest.skip("no services catalog")
    svc = services[0]
    body = {
        "client_id": agency["id"], "type": "servicios",
        "dates": {"start": "2026-08-01", "end": "2026-08-02"},
        "pax": {"adults": 4, "children": 0},
        "services": [{"service_id": svc["id"], "qty_per_person": 1}],
    }
    r = admin.post(f"{API}/quotations", json=body, timeout=15)
    assert r.status_code == 201, r.text
    q = r.json(); qid = q["id"]
    try:
        tok = admin.post(f"{API}/quotations/{qid}/public-link", timeout=10).json()["token"]
        r2 = requests.get(f"{API}/public/quotations/{tok}", timeout=15)
        assert r2.status_code == 200, r2.text
        data = r2.json()
        # guard against package_snapshot None for servicios
        assert data["quotation"]["package_snapshot"] is None
        assert data["payment"]["transfer_enabled"] is True
    finally:
        admin.delete(f"{API}/quotations/{qid}", timeout=10)
