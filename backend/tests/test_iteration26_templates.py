"""Iteration 26 backend tests: quotation templates + save-as-template + save-as-package.
Covers RBAC (executive cannot save as package), validation (non-personalizado quotation),
copy semantics (descriptive content + hotel pre-filled at public price)."""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}
EXEC = {"email": "ejecutivo@aventurate.mx", "password": "Demo2026!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def exec_session():
    return _login(EXEC)


@pytest.fixture(scope="module")
def client_id(admin_session):
    r = admin_session.post(f"{API}/clients", json={
        "name": "TEST_iter26 Cliente", "phone": "5550000026", "email": "test26@example.com",
        "channel": "directo"
    }, timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def custom_quotation_id(admin_session, client_id):
    payload = {
        "client_id": client_id, "type": "personalizado",
        "custom_title": "TEST_iter26 Riviera Maya",
        "custom_items": [
            {"category": "hospedaje", "name": "Hotel Xcaret",
             "description": "All inclusive", "net_price": 4000, "unit": "per_night", "qty": 3},
            {"category": "tour", "name": "Tour Tulum",
             "description": "Day tour", "net_price": 1500, "unit": "per_person", "qty": 0},
        ],
        "custom_itinerary": [
            {"day": 1, "title": "Llegada", "description": "Checkin y descanso"},
            {"day": 2, "title": "Tulum", "description": "Tour Tulum"},
        ],
        "custom_includes": ["Hospedaje", "Tour"],
        "custom_excludes": ["Vuelos"],
        "custom_nights": 3, "custom_rooms": 1,
        "pax": {"adultos": 2, "menores": 0, "ocupacion": "doble"},
    }
    r = admin_session.post(f"{API}/quotations", json=payload, timeout=20)
    assert r.status_code in (200, 201), r.text
    q = r.json()
    assert q["type"] == "personalizado"
    return q["id"]


# ---------- POST /api/templates ----------
class TestTemplatesCRUD:
    def test_create_template_requires_items(self, admin_session):
        r = admin_session.post(f"{API}/templates", json={
            "name": "TEST_iter26 empty", "custom_items": []
        }, timeout=15)
        assert r.status_code == 400
        assert "concepto" in r.text.lower() or "least" in r.text.lower()

    def test_create_template_direct(self, admin_session):
        r = admin_session.post(f"{API}/templates", json={
            "name": "TEST_iter26 plantilla directa",
            "custom_title": "Riviera",
            "custom_items": [
                {"category": "hospedaje", "name": "Hotel X", "net_price": 4000,
                 "unit": "per_night", "qty": 3}
            ],
            "custom_includes": ["A", "B"],
            "custom_nights": 3, "custom_rooms": 1,
            "pax_default": {"adultos": 2, "menores": 0},
        }, timeout=15)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["name"] == "TEST_iter26 plantilla directa"
        assert len(data["custom_items"]) == 1
        assert data["custom_nights"] == 3
        assert data["pax_default"]["adultos"] == 2
        # GET it back
        gid = data["id"]
        r2 = admin_session.get(f"{API}/templates/{gid}", timeout=15)
        assert r2.status_code == 200
        assert r2.json()["id"] == gid

    def test_list_templates(self, admin_session):
        r = admin_session.get(f"{API}/templates", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert any(t.get("name", "").startswith("TEST_iter26") for t in data)

    def test_delete_template(self, admin_session):
        # create then delete
        r = admin_session.post(f"{API}/templates", json={
            "name": "TEST_iter26 to-delete",
            "custom_items": [{"category": "extra", "name": "X", "net_price": 100,
                              "unit": "per_group", "qty": 1}],
        }, timeout=15)
        assert r.status_code == 201
        tid = r.json()["id"]
        rd = admin_session.delete(f"{API}/templates/{tid}", timeout=15)
        assert rd.status_code == 200
        # confirm gone
        rg = admin_session.get(f"{API}/templates/{tid}", timeout=15)
        assert rg.status_code == 404


# ---------- POST /api/quotations/{id}/save-as-template ----------
class TestSaveAsTemplate:
    def test_save_quotation_as_template(self, admin_session, custom_quotation_id):
        r = admin_session.post(
            f"{API}/quotations/{custom_quotation_id}/save-as-template",
            json={"name": "TEST_iter26 from-quotation"}, timeout=15)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["name"] == "TEST_iter26 from-quotation"
        # 2 items copied
        assert len(data["custom_items"]) == 2
        assert data["custom_nights"] == 3
        assert "Hospedaje" in data["custom_includes"]
        # pax_default carried over from quotation
        assert data["pax_default"]["adultos"] == 2

    def test_save_paquete_quotation_as_template_rejected(self, admin_session, client_id):
        # Need a non-personalizado quotation. Get any paquete from catalog.
        rp = admin_session.get(f"{API}/packages", timeout=15)
        pkgs = rp.json()
        if not pkgs:
            pytest.skip("No packages in catalog")
        pkg = pkgs[0]
        rq = admin_session.post(f"{API}/quotations", json={
            "client_id": client_id, "type": "paquete", "package_id": pkg["id"],
            "hotel_name": (pkg.get("hotels") or [{}])[0].get("name", ""),
            "pax": {"adultos": 2, "menores": 0, "ocupacion": "doble"},
            "dates": {"start": "2026-03-01", "end": "2026-03-04"},
        }, timeout=20)
        assert rq.status_code in (200, 201), rq.text
        qid = rq.json()["id"]
        r = admin_session.post(f"{API}/quotations/{qid}/save-as-template",
                               json={"name": "TEST_iter26 should-fail"}, timeout=15)
        assert r.status_code == 400
        assert "personalizado" in r.text.lower() or "medida" in r.text.lower()


# ---------- POST /api/quotations/{id}/save-as-package (RBAC + math) ----------
class TestSaveAsPackage:
    def test_executive_cannot_save_as_package(self, exec_session, custom_quotation_id):
        r = exec_session.post(
            f"{API}/quotations/{custom_quotation_id}/save-as-package",
            json={}, timeout=15)
        assert r.status_code == 403

    def test_admin_saves_as_package_with_prefilled_hotel(self, admin_session, custom_quotation_id):
        r = admin_session.post(
            f"{API}/quotations/{custom_quotation_id}/save-as-package",
            json={}, timeout=15)
        assert r.status_code == 201, r.text
        pkg = r.json()
        assert pkg["name"] == "TEST_iter26 Riviera Maya"
        assert pkg["nights"] == 3
        assert pkg["from_custom_quotation"] == custom_quotation_id
        # itinerary + includes copied
        assert len(pkg["itinerary"]) == 2
        assert "Hospedaje" in pkg["includes"]
        # Hotel prefilled at public price: net 4000 / margin 1.25 = 3200
        assert len(pkg["hotels"]) == 1
        h = pkg["hotels"][0]
        assert h["name"] == "Hotel Xcaret"
        for occ in ("sencilla", "doble", "triple", "cuadruple"):
            assert abs(h["prices_by_occupancy"][occ] - 3200.0) < 0.01, h
        # unique code generated
        assert pkg["code"] and pkg["code"].isupper()
        # appears in catalog
        rl = admin_session.get(f"{API}/packages", timeout=15)
        assert any(p["id"] == pkg["id"] for p in rl.json())

    def test_save_as_package_unique_code(self, admin_session, custom_quotation_id):
        """Calling again must auto-generate a new unique code (suffix)."""
        r1 = admin_session.post(
            f"{API}/quotations/{custom_quotation_id}/save-as-package",
            json={}, timeout=15)
        r2 = admin_session.post(
            f"{API}/quotations/{custom_quotation_id}/save-as-package",
            json={}, timeout=15)
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["code"] != r2.json()["code"]


# ---------- Cleanup ----------
@pytest.fixture(scope="module", autouse=True)
def _cleanup(admin_session):
    yield
    # Delete TEST_ templates
    try:
        tpls = admin_session.get(f"{API}/templates", timeout=15).json()
        for t in tpls:
            if t.get("name", "").startswith("TEST_iter26"):
                admin_session.delete(f"{API}/templates/{t['id']}", timeout=10)
    except Exception:
        pass
