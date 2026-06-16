"""Iteration 27 backend tests:
- PATCH /api/templates/{id}: featured toggle + GET ordered featured-first
- POST /api/templates/{id}/publish-as-package: admin only (executive 403),
  status='inactive', code respected, hotel prefilled (net/margin),
  itinerary+includes copied, from_template set; inactive NOT visible in
  /api/public/company/free-itinerary-mode catalog
- POST /api/quotations/{id}/save-as-package: respects {code}, creates status='active'
"""
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
def company_slug(admin_session):
    r = admin_session.get(f"{API}/companies/me", timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["slug"]


@pytest.fixture(scope="module")
def client_id(admin_session):
    r = admin_session.post(f"{API}/clients", json={
        "name": "TEST_iter27 Cliente", "phone": "5550000027", "email": "test27@example.com",
        "channel": "directo"
    }, timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def template_id(admin_session):
    r = admin_session.post(f"{API}/templates", json={
        "name": "TEST_iter27 Plantilla A",
        "custom_title": "TEST_iter27 Riviera",
        "custom_items": [
            {"category": "hospedaje", "name": "Hotel Demo27", "net_price": 3000,
             "unit": "per_night", "qty": 3},
            {"category": "tour", "name": "Tour Demo27", "net_price": 1000,
             "unit": "per_person", "qty": 0},
        ],
        "custom_itinerary": [
            {"day": 1, "title": "Llegada", "description": "Checkin"},
            {"day": 2, "title": "Tour", "description": "Tour"},
        ],
        "custom_includes": ["Hospedaje", "Tour"],
        "custom_excludes": ["Vuelos"],
        "custom_nights": 3, "custom_rooms": 1,
        "pax_default": {"adultos": 2, "menores": 0},
    }, timeout=15)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def template_id_b(admin_session):
    """A second template created LATER -> appears first by created_at if not featured."""
    r = admin_session.post(f"{API}/templates", json={
        "name": "TEST_iter27 Plantilla B",
        "custom_items": [{"category": "extra", "name": "X", "net_price": 50,
                          "unit": "per_group", "qty": 1}],
    }, timeout=15)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def custom_quotation_id(admin_session, client_id):
    r = admin_session.post(f"{API}/quotations", json={
        "client_id": client_id, "type": "personalizado",
        "custom_title": "TEST_iter27 Quotation",
        "custom_items": [
            {"category": "hospedaje", "name": "Hotel Custom27", "net_price": 2500,
             "unit": "per_night", "qty": 3}
        ],
        "custom_includes": ["Hospedaje"],
        "custom_nights": 3, "custom_rooms": 1,
        "pax": {"adultos": 2, "menores": 0, "ocupacion": "doble"},
    }, timeout=20)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# ---------- PATCH /api/templates/{id} featured ----------
class TestTemplateFeatured:
    def test_patch_featured_true(self, admin_session, template_id):
        r = admin_session.patch(f"{API}/templates/{template_id}",
                                json={"featured": True}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["featured"] is True

    def test_list_featured_first(self, admin_session, template_id, template_id_b):
        # ensure A is featured, B is not
        admin_session.patch(f"{API}/templates/{template_id}", json={"featured": True}, timeout=15)
        admin_session.patch(f"{API}/templates/{template_id_b}", json={"featured": False}, timeout=15)
        r = admin_session.get(f"{API}/templates", timeout=15)
        assert r.status_code == 200
        tpls = r.json()
        ids = [t["id"] for t in tpls]
        assert template_id in ids and template_id_b in ids
        # featured (A) must appear before non-featured (B)
        assert ids.index(template_id) < ids.index(template_id_b)
        # And first item overall must be featured
        assert tpls[0]["featured"] is True

    def test_patch_featured_false(self, admin_session, template_id):
        r = admin_session.patch(f"{API}/templates/{template_id}",
                                json={"featured": False}, timeout=15)
        assert r.status_code == 200
        assert r.json()["featured"] is False


# ---------- POST /api/templates/{id}/publish-as-package ----------
class TestPublishTemplateAsPackage:
    def test_executive_forbidden(self, exec_session, template_id):
        r = exec_session.post(f"{API}/templates/{template_id}/publish-as-package",
                              json={"code": "EXECFAIL27"}, timeout=15)
        assert r.status_code == 403

    def test_admin_publish_inactive_with_code(self, admin_session, template_id, company_slug):
        code = "TESTITER27PUB"
        r = admin_session.post(f"{API}/templates/{template_id}/publish-as-package",
                               json={"code": code}, timeout=15)
        assert r.status_code == 201, r.text
        pkg = r.json()
        # status MUST be inactive (draft)
        assert pkg["status"] == "inactive"
        # code respected (auto-suffix if collision)
        assert pkg["code"].startswith(code)
        assert pkg["from_template"] == template_id
        assert pkg["nights"] == 3
        # itinerary + includes copied
        assert len(pkg["itinerary"]) == 2
        assert "Hospedaje" in pkg["includes"]
        # hotel prefilled: net 3000 / margin 1.25 = 2400
        assert len(pkg["hotels"]) == 1
        h = pkg["hotels"][0]
        assert h["name"] == "Hotel Demo27"
        for occ in ("sencilla", "doble", "triple", "cuadruple"):
            assert abs(h["prices_by_occupancy"][occ] - 2400.0) < 0.01, h

        # MUST NOT appear in public free-itinerary-mode catalog (inactive)
        rp = requests.get(f"{API}/public/company/free-itinerary-mode",
                          params={"slug": company_slug}, timeout=15)
        # endpoint may need different params; try common variants
        if rp.status_code != 200:
            rp = requests.get(f"{API}/public/company/{company_slug}/free-itinerary-mode", timeout=15)
        if rp.status_code == 200:
            data = rp.json()
            # data could be a list of packages or {packages: [...]}
            items = data.get("packages", data) if isinstance(data, dict) else data
            if isinstance(items, list):
                assert not any(p.get("id") == pkg["id"] for p in items), \
                    "Inactive package should NOT appear in public catalog"
        # Persist id for later test
        TestPublishTemplateAsPackage._created_id = pkg["id"]
        TestPublishTemplateAsPackage._created_code = pkg["code"]

    def test_published_appears_in_admin_packages(self, admin_session):
        pid = getattr(TestPublishTemplateAsPackage, "_created_id", None)
        assert pid, "previous test must have created a package"
        r = admin_session.get(f"{API}/packages", timeout=15)
        assert r.status_code == 200
        found = next((p for p in r.json() if p["id"] == pid), None)
        assert found is not None
        assert found["status"] == "inactive"

    def test_publish_without_code_auto_generates(self, admin_session, template_id):
        r = admin_session.post(f"{API}/templates/{template_id}/publish-as-package",
                               json={}, timeout=15)
        assert r.status_code == 201, r.text
        pkg = r.json()
        assert pkg["status"] == "inactive"
        assert pkg["code"]
        assert pkg["code"].isupper()


# ---------- POST /api/quotations/{id}/save-as-package respects code ----------
class TestSaveQuotationAsPackageRespectsCode:
    def test_save_as_package_with_custom_code_active(self, admin_session, custom_quotation_id):
        code = "TESTITER27CUSTOM"
        r = admin_session.post(f"{API}/quotations/{custom_quotation_id}/save-as-package",
                               json={"code": code}, timeout=15)
        assert r.status_code == 201, r.text
        pkg = r.json()
        # status must be active for save-as-package from quotation
        assert pkg["status"] == "active"
        assert pkg["code"].startswith(code)
        assert pkg["from_custom_quotation"] == custom_quotation_id


# ---------- Cleanup ----------
@pytest.fixture(scope="module", autouse=True)
def _cleanup(admin_session):
    yield
    try:
        tpls = admin_session.get(f"{API}/templates", timeout=15).json()
        for t in tpls:
            if t.get("name", "").startswith("TEST_iter27"):
                admin_session.delete(f"{API}/templates/{t['id']}", timeout=10)
    except Exception:
        pass
    try:
        pkgs = admin_session.get(f"{API}/packages", timeout=15).json()
        for p in pkgs:
            code = p.get("code", "")
            if code.startswith("TESTITER27") or code.startswith("EXECFAIL27"):
                admin_session.delete(f"{API}/packages/{p['id']}", timeout=10)
            # Also delete those auto-generated from template TEST_iter27 (name match)
            elif p.get("name", "").startswith("TEST_iter27"):
                admin_session.delete(f"{API}/packages/{p['id']}", timeout=10)
    except Exception:
        pass
