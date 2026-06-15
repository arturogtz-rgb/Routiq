"""Iteration 3 — A la carte Services tests (CRUD, role guards, quotation wiring, PDF, public link)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")

ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}
EXEC = {"email": "ejecutivo@aventurate.mx", "password": "Demo2026!"}


def _login(creds):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


# ---------- Services: seed list ----------
def test_services_list_seeded():
    s = _login(ADMIN)
    r = s.get(f"{BASE_URL}/api/services", timeout=30)
    assert r.status_code == 200
    services = r.json()
    assert isinstance(services, list)
    assert len(services) >= 4, f"Expected >=4 seeded services, got {len(services)}"
    for svc in services:
        assert "id" in svc and "name" in svc
        assert "net_price" in svc and "public_price" in svc
        assert svc["public_price"] > 0, f"Service {svc['name']} has 0 public_price (should be auto-computed)"
        assert svc["category"] in ("tour", "traslado", "acceso", "extra")


# ---------- Services CRUD ----------
def test_create_service_auto_public_price():
    s = _login(ADMIN)
    # Get current margin_divisor
    company = s.get(f"{BASE_URL}/api/companies/me", timeout=30).json()
    divisor = company["pricing_config"]["margin_divisor"]
    ts = int(time.time())
    payload = {
        "name": f"TEST Tour {ts}",
        "category": "tour",
        "description": "test service",
        "net_price": 380.0,
        "public_price": 0,
        "per_person": True,
    }
    r = s.post(f"{BASE_URL}/api/services", json=payload, timeout=30)
    assert r.status_code == 201, r.text
    svc = r.json()
    expected_public = round(380.0 / divisor, 2)
    assert abs(svc["public_price"] - expected_public) < 0.01, \
        f"Expected public_price={expected_public}, got {svc['public_price']} (divisor={divisor})"
    assert "id" in svc
    # GET to verify persistence
    listing = s.get(f"{BASE_URL}/api/services", timeout=30).json()
    assert any(x["id"] == svc["id"] for x in listing)
    return svc["id"]


def test_create_service_explicit_public_price():
    s = _login(ADMIN)
    ts = int(time.time())
    payload = {"name": f"TEST Acceso {ts}", "category": "acceso",
               "net_price": 100.0, "public_price": 250.0}
    r = s.post(f"{BASE_URL}/api/services", json=payload, timeout=30)
    assert r.status_code == 201
    assert r.json()["public_price"] == 250.0


def test_patch_service_recomputes_public_on_net_change():
    s = _login(ADMIN)
    company = s.get(f"{BASE_URL}/api/companies/me", timeout=30).json()
    divisor = company["pricing_config"]["margin_divisor"]
    ts = int(time.time())
    # Create
    r = s.post(f"{BASE_URL}/api/services", json={
        "name": f"TEST Patch {ts}", "category": "extra", "net_price": 100.0
    }, timeout=30)
    sid = r.json()["id"]
    # Patch only net_price -> public should recompute
    r2 = s.patch(f"{BASE_URL}/api/services/{sid}", json={"net_price": 500.0}, timeout=30)
    assert r2.status_code == 200, r2.text
    expected = round(500.0 / divisor, 2)
    assert abs(r2.json()["public_price"] - expected) < 0.01


def test_delete_service():
    s = _login(ADMIN)
    ts = int(time.time())
    r = s.post(f"{BASE_URL}/api/services", json={
        "name": f"TEST Del {ts}", "category": "extra", "net_price": 50.0
    }, timeout=30)
    sid = r.json()["id"]
    rd = s.delete(f"{BASE_URL}/api/services/{sid}", timeout=30)
    assert rd.status_code == 200
    # Verify gone
    listing = s.get(f"{BASE_URL}/api/services", timeout=30).json()
    assert not any(x["id"] == sid for x in listing)


# ---------- Role guards ----------
def test_executive_can_list_services():
    s = _login(EXEC)
    r = s.get(f"{BASE_URL}/api/services", timeout=30)
    assert r.status_code == 200


def test_executive_cannot_create_service():
    s = _login(EXEC)
    r = s.post(f"{BASE_URL}/api/services",
               json={"name": "X", "category": "tour", "net_price": 10.0}, timeout=30)
    assert r.status_code == 403


def test_executive_cannot_patch_service():
    s_admin = _login(ADMIN)
    services = s_admin.get(f"{BASE_URL}/api/services", timeout=30).json()
    sid = services[0]["id"]
    s = _login(EXEC)
    r = s.patch(f"{BASE_URL}/api/services/{sid}", json={"name": "Hack"}, timeout=30)
    assert r.status_code == 403


def test_executive_cannot_delete_service():
    s_admin = _login(ADMIN)
    services = s_admin.get(f"{BASE_URL}/api/services", timeout=30).json()
    sid = services[0]["id"]
    s = _login(EXEC)
    r = s.delete(f"{BASE_URL}/api/services/{sid}", timeout=30)
    assert r.status_code == 403


# ---------- Quotation wiring ----------
def _make_quotation_with_services(s, services_payload):
    clients = s.get(f"{BASE_URL}/api/clients", timeout=30).json()
    packages = s.get(f"{BASE_URL}/api/packages", timeout=30).json()
    cli = next(c for c in clients if c["channel"] == "directo")
    pack = next(p for p in packages if p["code"] == "GDL-TEQ-3N")
    hotel = pack["hotels"][0]
    payload = {
        "client_id": cli["id"], "package_id": pack["id"],
        "hotel_name": hotel["name"],
        "dates": {"start": "2026-06-01", "end": "2026-06-04"},
        "pax": {"adultos": 2, "menores": 0, "ocupacion": "doble"},
        "services": services_payload,
        "notes": "TEST services",
    }
    r = s.post(f"{BASE_URL}/api/quotations", json=payload, timeout=30)
    assert r.status_code == 201, r.text
    return r.json(), pack, hotel


def test_quotation_with_services_items_and_total():
    s = _login(ADMIN)
    services = s.get(f"{BASE_URL}/api/services", timeout=30).json()
    svc = services[0]  # use first seeded
    q, pack, hotel = _make_quotation_with_services(s, [{"service_id": svc["id"], "qty": 2}])
    # Verify item kind=servicio exists
    servicio_items = [it for it in q["items"] if it.get("kind") == "servicio"]
    assert len(servicio_items) >= 1, f"No servicio items found in {q['items']}"
    it = servicio_items[0]
    assert it["service_id"] == svc["id"]
    assert abs(it["unit_price"] - svc["public_price"]) < 0.01
    # qty may be auto-bumped to total_pax if per_person; but at minimum should be >= requested
    assert it["qty"] >= 2 if not svc.get("per_person") else it["qty"] >= 2
    assert abs(it["subtotal"] - round(it["unit_price"] * it["qty"], 2)) < 0.01
    # Subtotal should include service contribution
    hospedaje_sub = sum(x["subtotal"] for x in q["items"] if x.get("kind") == "hospedaje")
    service_sub = sum(x["subtotal"] for x in q["items"] if x.get("kind") == "servicio")
    assert abs(q["subtotal"] - (hospedaje_sub + service_sub)) < 0.01
    return q["id"], svc


def test_patch_quotation_services_recomputes():
    s = _login(ADMIN)
    services = s.get(f"{BASE_URL}/api/services", timeout=30).json()
    svc1, svc2 = services[0], services[1]
    q, _, _ = _make_quotation_with_services(s, [{"service_id": svc1["id"], "qty": 1}])
    original_total = q["total"]
    # PATCH with new services array (both)
    r = s.patch(f"{BASE_URL}/api/quotations/{q['id']}", json={
        "services": [{"service_id": svc1["id"], "qty": 1}, {"service_id": svc2["id"], "qty": 1}]
    }, timeout=30)
    assert r.status_code == 200, r.text
    q2 = r.json()
    servicio_ids = {it["service_id"] for it in q2["items"] if it.get("kind") == "servicio"}
    assert svc1["id"] in servicio_ids and svc2["id"] in servicio_ids
    assert q2["total"] != original_total
    # Remove services
    r3 = s.patch(f"{BASE_URL}/api/quotations/{q['id']}", json={"services": []}, timeout=30)
    assert r3.status_code == 200
    q3 = r3.json()
    assert not any(it.get("kind") == "servicio" for it in q3["items"])


def test_pdf_with_services():
    s = _login(ADMIN)
    services = s.get(f"{BASE_URL}/api/services", timeout=30).json()
    q, _, _ = _make_quotation_with_services(s, [{"service_id": services[0]["id"], "qty": 1}])
    r = s.get(f"{BASE_URL}/api/quotations/{q['id']}/pdf", timeout=60)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content.startswith(b"%PDF")
    assert len(r.content) > 1000


def test_public_link_with_services():
    s = _login(ADMIN)
    services = s.get(f"{BASE_URL}/api/services", timeout=30).json()
    q, _, _ = _make_quotation_with_services(s, [{"service_id": services[0]["id"], "qty": 1}])
    rl = s.post(f"{BASE_URL}/api/quotations/{q['id']}/public-link", timeout=30)
    assert rl.status_code == 200, rl.text
    token = rl.json()["token"]
    # Public fetch (no auth)
    rp = requests.get(f"{BASE_URL}/api/public/quotations/{token}", timeout=30)
    assert rp.status_code == 200
    data = rp.json()
    assert "quotation" in data
    items = data["quotation"]["items"]
    assert any(it.get("kind") == "servicio" for it in items), \
        f"No servicio items exposed in public link: {items}"
