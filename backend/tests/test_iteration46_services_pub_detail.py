"""Iter 46 — Servicios: página detalle pública, formulario servicio con imagen/duración/días/incluye/excluye,
compartir servicios (QR) y lead con etiqueta 'Servicio'. NO tocamos precios/cotizador."""
import os
import io
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
SLUG = "aventurate"
ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def created(sess):
    """Crea un servicio TEST con nuevos campos y lo limpia al final."""
    payload = {
        "name": "TEST_iter46 Tour",
        "category": "tour",
        "description": "Tour de prueba iter 46",
        "net_price": 800,
        "public_price": 0,  # server autocalc
        "unit": "per_person",
        "image_url": "/api/uploads/packages/nope.jpg",
        "duration_value": 4,
        "duration_unit": "horas",
        "operating_days": [0, 2, 4],  # Lun/Mié/Vie
        "includes": ["Guía", "Snack"],
        "excludes": ["Propinas"],
    }
    r = sess.post(f"{API}/services", json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    svc = r.json()
    yield svc
    # Cleanup
    try:
        sess.delete(f"{API}/services/{svc['id']}", timeout=15)
    except Exception:
        pass


# ---------- CREATE / persistence ----------
def test_01_create_service_fields_persist(sess, created):
    sid = created["id"]
    r = sess.get(f"{API}/services", timeout=15)
    assert r.status_code == 200
    svc = next((s for s in r.json() if s["id"] == sid), None)
    assert svc, "servicio recién creado no aparece en /services"
    assert svc["duration_value"] == 4
    assert svc["duration_unit"] == "horas"
    assert svc["operating_days"] == [0, 2, 4]
    assert "Guía" in svc["includes"] and "Snack" in svc["includes"]
    assert svc["excludes"] == ["Propinas"]
    assert svc["image_url"] == "/api/uploads/packages/nope.jpg"
    # public_price autocalculado desde neto/margin (800/0.76 ≈ 1052.63)
    assert svc["public_price"] > 800


def test_02_update_all_days_clears_operating_days(sess, created):
    sid = created["id"]
    r = sess.patch(f"{API}/services/{sid}", json={"operating_days": []}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["operating_days"] == []


def test_03_update_specific_days(sess, created):
    sid = created["id"]
    r = sess.patch(f"{API}/services/{sid}", json={"operating_days": [5, 6]}, timeout=15)
    assert r.status_code == 200
    assert r.json()["operating_days"] == [5, 6]
    # reset for later tests
    sess.patch(f"{API}/services/{sid}", json={"operating_days": [0, 2, 4]}, timeout=15)


# ---------- PUBLIC catalog with id ----------
def test_04_public_services_includes_id(created):
    r = requests.get(f"{API}/public/company/{SLUG}/services", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    all_items = [it for g in data.get("groups", []) for it in g["items"]]
    ids = [it["id"] for it in all_items]
    assert created["id"] in ids, "el servicio creado no aparece en el catálogo público"
    # cada item tiene id no vacío
    assert all(it.get("id") for it in all_items)


# ---------- PUBLIC service detail ----------
def test_05_public_service_detail_ok(created):
    r = requests.get(f"{API}/public/company/{SLUG}/service/{created['id']}", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    s = data["service"]
    assert s["id"] == created["id"]
    assert s["name"] == "TEST_iter46 Tour"
    assert s["duration_value"] == 4
    assert s["duration_unit"] == "horas"
    assert s["operating_days"] == [0, 2, 4]
    assert "Guía" in s["includes"]
    assert s["excludes"] == ["Propinas"]
    assert s["public_price"] > 0
    assert data["company"]["slug"] == SLUG


def test_06_public_service_detail_404(sess):
    r = requests.get(f"{API}/public/company/{SLUG}/service/does-not-exist", timeout=15)
    assert r.status_code == 404


# ---------- LEAD from service detail ----------
def test_07_public_service_request_creates_lead(sess, created):
    payload = {"name": "TEST_iter46 Lead", "email": "test_iter46@example.com",
               "phone": "555-1111", "travel_date": "2026-05-01", "pax": "2 adultos",
               "message": "Quiero este servicio"}
    r = requests.post(f"{API}/public/company/{SLUG}/service/{created['id']}/request",
                      json=payload, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True

    # Verify lead exists with service_id + service_name
    leads = sess.get(f"{API}/quote-requests", timeout=15).json()
    lead = next((l for l in leads if l.get("email") == "test_iter46@example.com"), None)
    assert lead, "El lead de servicio no aparece en /quote-requests"
    assert lead.get("service_id") == created["id"]
    assert lead.get("service_name") == "TEST_iter46 Tour"
    assert lead.get("package_id") in (None, ""), "no debería tener package_id"
    # Cleanup: archivar
    sess.patch(f"{API}/quote-requests/{lead['id']}", json={"status": "archived"}, timeout=15)


def test_08_public_service_request_honeypot(sess, created):
    # bot -> devuelve ok:true SIN crear lead
    payload = {"name": "BOT", "email": "bot@evil.com", "company_website": "http://spam"}
    r = requests.post(f"{API}/public/company/{SLUG}/service/{created['id']}/request",
                      json=payload, timeout=15)
    assert r.status_code == 200
    leads = sess.get(f"{API}/quote-requests", timeout=15).json()
    assert not any(l.get("email") == "bot@evil.com" for l in leads)


def test_09_public_service_request_bad_email(created):
    payload = {"name": "TEST", "email": "not-an-email"}
    r = requests.post(f"{API}/public/company/{SLUG}/service/{created['id']}/request",
                      json=payload, timeout=15)
    assert r.status_code == 422  # pydantic EmailStr


# ---------- REGRESSION: existing endpoints still work ----------
def test_10_public_package_still_works():
    r = requests.get(f"{API}/public/company/{SLUG}", timeout=15)
    assert r.status_code == 200
    assert "packages" in r.json()


def test_11_catalog_export_still_works(sess):
    r = sess.get(f"{API}/catalog/export", timeout=30)
    assert r.status_code == 200
    assert len(r.content) > 200


def test_12_upload_image_endpoint(sess):
    # Ensure /packages/upload-image still accessible for admin (used by Services form)
    # Send a minimal PNG (1x1 pixel).
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    files = {"file": ("tiny.png", io.BytesIO(png), "image/png")}
    r = sess.post(f"{API}/packages/upload-image", files=files, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("url", "").startswith("/api/uploads/")
