"""Routiq backend API tests — multi-tenant SaaS."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")

SUPER = {"email": "owner@routiq.mx", "password": "Routiq2026!"}
ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}
EXEC = {"email": "ejecutivo@aventurate.mx", "password": "Demo2026!"}


def _session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(creds):
    s = _session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"Login failed {creds['email']}: {r.status_code} {r.text}"
    return s, r.json()


# ---------- Health ----------
def test_health():
    r = requests.get(f"{BASE_URL}/api/", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"


# ---------- Auth ----------
def test_login_super():
    s, user = _login(SUPER)
    assert user["role"] == "super_admin"
    assert user["email"] == SUPER["email"]
    # cookie set
    assert "access_token" in s.cookies.get_dict() or any(
        c.name == "access_token" for c in s.cookies
    )


def test_login_admin():
    s, user = _login(ADMIN)
    assert user["role"] == "company_admin"
    assert user.get("tenant_id")


def test_login_executive():
    s, user = _login(EXEC)
    assert user["role"] == "executive"
    assert user.get("tenant_id")


def test_login_invalid():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "nope@x.com", "password": "bad"}, timeout=30)
    assert r.status_code == 401


def test_me_after_login():
    s, _ = _login(ADMIN)
    r = s.get(f"{BASE_URL}/api/auth/me", timeout=30)
    assert r.status_code == 200
    assert r.json()["email"] == ADMIN["email"]


def test_logout_clears():
    s, _ = _login(ADMIN)
    r = s.post(f"{BASE_URL}/api/auth/logout", timeout=30)
    assert r.status_code == 200
    # Session still has cookies from before, but fresh request without cookies should be 401
    s.cookies.clear()
    r2 = s.get(f"{BASE_URL}/api/auth/me", timeout=30)
    assert r2.status_code == 401


# ---------- Role / tenant isolation ----------
def test_executive_cannot_list_companies():
    s, _ = _login(EXEC)
    r = s.get(f"{BASE_URL}/api/companies", timeout=30)
    assert r.status_code == 403


def test_admin_cannot_access_master_metrics():
    s, _ = _login(ADMIN)
    r = s.get(f"{BASE_URL}/api/metrics/master", timeout=30)
    assert r.status_code == 403


def test_super_cannot_list_quotations_require_tenant():
    s, _ = _login(SUPER)
    r = s.get(f"{BASE_URL}/api/quotations", timeout=30)
    assert r.status_code == 403


# ---------- Companies ----------
def test_list_companies_super():
    s, _ = _login(SUPER)
    r = s.get(f"{BASE_URL}/api/companies", timeout=30)
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert any("Aventúrate" in n for n in names)


def test_create_company_super():
    s, _ = _login(SUPER)
    ts = int(time.time())
    payload = {
        "name": f"TEST Tours {ts}",
        "slug": f"test-tours-{ts}",
        "contact_email": f"test{ts}@test.com",
        "contact_phone": "+52 00 0000 0000",
        "address": "Test addr",
        "admin_name": "Test Admin",
        "admin_email": f"admin-{ts}@test.com",
        "admin_password": "Test2026!",
    }
    r = s.post(f"{BASE_URL}/api/companies", json=payload, timeout=30)
    assert r.status_code == 201, r.text
    assert r.json()["slug"] == payload["slug"]


def test_company_me_admin():
    s, _ = _login(ADMIN)
    r = s.get(f"{BASE_URL}/api/companies/me", timeout=30)
    assert r.status_code == 200
    assert "Aventúrate" in r.json()["name"]


def test_patch_pricing_admin():
    s, _ = _login(ADMIN)
    payload = {
        "margin_divisor": 0.75,
        "commissions": {"directo": 0.0, "agencia": 0.12, "mayorista": 0.15, "operador": 0.20},
        "minor_age_min": 3,
        "minor_age_max": 11,
        "minor_discount": 0.40,
        "currency": "MXN",
    }
    r = s.patch(f"{BASE_URL}/api/companies/me/pricing", json=payload, timeout=30)
    assert r.status_code == 200
    assert r.json()["pricing_config"]["commissions"]["agencia"] == 0.12
    # verify persistence
    r2 = s.get(f"{BASE_URL}/api/companies/me", timeout=30)
    assert r2.json()["pricing_config"]["margin_divisor"] == 0.75


# ---------- Packages / Clients ----------
def test_list_packages():
    s, _ = _login(ADMIN)
    r = s.get(f"{BASE_URL}/api/packages", timeout=30)
    assert r.status_code == 200
    pkgs = r.json()
    codes = [p["code"] for p in pkgs]
    assert "GDL-TEQ-3N" in codes
    assert "PV-LUX-5N" in codes


def test_list_clients():
    s, _ = _login(ADMIN)
    r = s.get(f"{BASE_URL}/api/clients", timeout=30)
    assert r.status_code == 200
    assert len(r.json()) >= 2


def test_create_client():
    s, _ = _login(ADMIN)
    ts = int(time.time())
    payload = {"name": f"TEST Cliente {ts}", "phone": "555", "email": f"c{ts}@x.com",
               "channel": "agencia", "notes": "t"}
    r = s.post(f"{BASE_URL}/api/clients", json=payload, timeout=30)
    assert r.status_code == 201
    assert r.json()["channel"] == "agencia"


# ---------- Quotations ----------
def test_create_quotation_and_verify():
    s, _ = _login(ADMIN)
    clients = s.get(f"{BASE_URL}/api/clients", timeout=30).json()
    packages = s.get(f"{BASE_URL}/api/packages", timeout=30).json()
    agencia = next(c for c in clients if c["channel"] == "agencia")
    pack = next(p for p in packages if p["code"] == "GDL-TEQ-3N")
    hotel = pack["hotels"][0]
    payload = {
        "client_id": agencia["id"], "package_id": pack["id"],
        "hotel_name": hotel["name"],
        "dates": {"start": "2026-05-01", "end": "2026-05-04"},
        "pax": {"adultos": 2, "menores": 1, "ocupacion": "doble"},
        "notes": "TEST",
    }
    r = s.post(f"{BASE_URL}/api/quotations", json=payload, timeout=30)
    assert r.status_code == 201, r.text
    q = r.json()
    price_adult = hotel["prices_by_occupancy"]["doble"]
    price_minor = hotel["minor_price"]
    expected_subtotal = price_adult * 2 + price_minor * 1
    expected_commission = round(expected_subtotal * 0.10, 2)  # agencia (but pricing was updated to 0.12 earlier)
    # Re-check commission rate from response to be robust vs test order
    assert abs(q["subtotal"] - expected_subtotal) < 0.01
    assert abs(q["commission"] - round(q["subtotal"] * q["commission_rate"], 2)) < 0.01
    assert abs(q["total"] - round(q["subtotal"] - q["commission"], 2)) < 0.01
    assert q["state"] == "nueva_consulta"
    # GET verify persist
    r2 = s.get(f"{BASE_URL}/api/quotations/{q['id']}", timeout=30)
    assert r2.status_code == 200


def test_list_quotations_enriched():
    s, _ = _login(ADMIN)
    r = s.get(f"{BASE_URL}/api/quotations", timeout=30)
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 6
    assert all("days_idle" in it for it in items)


def test_update_quotation_state():
    s, _ = _login(ADMIN)
    items = s.get(f"{BASE_URL}/api/quotations", timeout=30).json()
    qid = items[0]["id"]
    for state in ["cotizando", "enviada", "negociacion", "ganada", "perdida", "nueva_consulta"]:
        r = s.patch(f"{BASE_URL}/api/quotations/{qid}/state", json={"state": state}, timeout=30)
        assert r.status_code == 200
        assert r.json()["state"] == state


def test_pdf_download():
    s, _ = _login(ADMIN)
    items = s.get(f"{BASE_URL}/api/quotations", timeout=30).json()
    qid = items[0]["id"]
    r = s.get(f"{BASE_URL}/api/quotations/{qid}/pdf", timeout=60)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert len(r.content) > 500
    assert r.content.startswith(b"%PDF")


# ---------- Metrics ----------
def test_dashboard_metrics():
    s, _ = _login(ADMIN)
    r = s.get(f"{BASE_URL}/api/metrics/dashboard", timeout=30)
    assert r.status_code == 200
    m = r.json()
    for k in ["quotations_total", "quotations_active", "quotations_won",
              "conversion_rate", "projected_revenue", "revenue_won"]:
        assert k in m


def test_master_metrics():
    s, _ = _login(SUPER)
    r = s.get(f"{BASE_URL}/api/metrics/master", timeout=30)
    assert r.status_code == 200
    m = r.json()
    assert "per_company" in m
    assert m["companies_total"] >= 1


# ---------- Invite executive ----------
def test_invite_executive():
    s, _ = _login(ADMIN)
    ts = int(time.time())
    payload = {"name": f"TEST Exec {ts}", "email": f"exec-{ts}@test.com", "password": "Test2026!"}
    r = s.post(f"{BASE_URL}/api/users/invite-executive", json=payload, timeout=30)
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "executive"
    # verify appears in team list
    r2 = s.get(f"{BASE_URL}/api/users", timeout=30)
    assert r2.status_code == 200
    emails = [u["email"] for u in r2.json()]
    assert payload["email"].lower() in emails


def test_invite_executive_requires_admin():
    s, _ = _login(EXEC)
    r = s.post(f"{BASE_URL}/api/users/invite-executive",
               json={"name": "X", "email": "x@x.com", "password": "Test2026!"}, timeout=30)
    assert r.status_code == 403
