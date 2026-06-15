"""
v1.5 Backend regression: Package CRUD + Season pricing engine + Image upload.
Already curl-verified by the dev agent; this is a programmatic regression layer.
"""
import os
import io
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://saas-quotes-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}
EXEC = {"email": "ejecutivo@aventurate.mx", "password": "Demo2026!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def exec_session():
    return _login(EXEC)


# ----- Package CRUD -----

def test_package_create_with_seasons_and_hotels(admin_session):
    season_payload_id = "ignored-client-id"  # backend should re-assign
    payload = {
        "code": "TEST-PKG-S1",
        "name": "TEST Paquete con Temporada",
        "nights": 3,
        "description": "TEST season pricing package",
        "status": "active",
        "allowed_start_days": [0, 3],
        "includes": ["Hospedaje", "Desayuno"],
        "excludes": ["Vuelos"],
        "itinerary": [{"day": 1, "title": "Llegada", "description": "Check-in"}],
        "seasons": [
            {"id": season_payload_id, "name": "Alta",
             "ranges": [{"start": "2026-12-15", "end": "2027-01-10"}]}
        ],
        "hotels": [
            {"name": "TEST Hotel A", "category": "4*",
             "prices_by_occupancy": {"sencilla": 10000, "doble": 8900, "triple": 7800, "cuadruple": 7000},
             "minor_price": 3500,
             "season_prices": {season_payload_id: {"sencilla": 15000, "doble": 13350, "triple": 11800, "cuadruple": 10500, "minor_price": 5000}}},
        ],
    }
    r = admin_session.post(f"{API}/packages", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    assert data["code"] == "TEST-PKG-S1"
    assert data["nights"] == 3
    assert len(data["seasons"]) == 1
    s = data["seasons"][0]
    assert s["name"] == "Alta"
    # backend should assign a real season id
    server_sid = s["id"]
    assert server_sid and isinstance(server_sid, str)
    # And carry the season prices keyed by the backend's id
    hotel = data["hotels"][0]
    assert "season_prices" in hotel
    assert server_sid in hotel["season_prices"], f"expected key {server_sid} in {list(hotel['season_prices'].keys())}"
    assert hotel["season_prices"][server_sid]["doble"] == 13350
    # store id for later tests
    pytest.pkg_id = data["id"]
    pytest.pkg_season_id = server_sid


def test_package_get_after_create(admin_session):
    pid = getattr(pytest, "pkg_id", None)
    assert pid, "previous create failed"
    r = admin_session.get(f"{API}/packages/{pid}", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == pid
    assert data["seasons"][0]["name"] == "Alta"


def test_package_patch_updates_base_price(admin_session):
    pid = getattr(pytest, "pkg_id", None)
    sid = getattr(pytest, "pkg_season_id", None)
    assert pid
    patch = {
        "hotels": [{
            "name": "TEST Hotel A", "category": "4*",
            "prices_by_occupancy": {"sencilla": 11000, "doble": 9500, "triple": 8000, "cuadruple": 7200},
            "minor_price": 3700,
            "season_prices": {sid: {"sencilla": 16000, "doble": 14000, "triple": 12500, "cuadruple": 11000, "minor_price": 5200}},
        }],
    }
    r = admin_session.patch(f"{API}/packages/{pid}", json=patch, timeout=30)
    assert r.status_code in (200, 204), r.text
    # verify persisted via GET
    r2 = admin_session.get(f"{API}/packages/{pid}", timeout=30)
    assert r2.status_code == 200
    hotel = r2.json()["hotels"][0]
    assert hotel["prices_by_occupancy"]["doble"] == 9500
    assert hotel["season_prices"][sid]["doble"] == 14000


def test_executive_cannot_create_package(exec_session):
    r = exec_session.post(f"{API}/packages", json={
        "code": "TEST-FORBID", "name": "x", "nights": 1, "hotels": [], "seasons": [],
    }, timeout=30)
    assert r.status_code == 403, f"expected 403 but got {r.status_code} {r.text}"


def test_executive_cannot_delete_package(exec_session):
    pid = getattr(pytest, "pkg_id", None)
    assert pid
    r = exec_session.delete(f"{API}/packages/{pid}", timeout=30)
    assert r.status_code == 403


# ----- Season pricing engine -----

def test_quotation_inside_alta_uses_season_price(admin_session):
    # Use the seeded Guadalajara package per agent note (Alta 2026-12-15..2027-01-10 doble=13350 vs base 8900)
    pkgs = admin_session.get(f"{API}/packages", timeout=30).json()
    gdl = next((p for p in pkgs if "guadalajara" in p["name"].lower() or p["code"].lower().startswith("gdl")), None)
    if not gdl:
        pytest.skip("seeded Guadalajara package not found")
    # find a hotel id and a season alta
    hotel = gdl["hotels"][0]
    clients = admin_session.get(f"{API}/clients", timeout=30).json()
    if not clients:
        pytest.skip("no clients seeded")
    client = clients[0]
    body = {
        "client_id": client["id"],
        "package_id": gdl["id"],
        "hotel_name": hotel["name"],
        "pax": {"rooms": [{"ocupacion": "doble", "count": 1}], "menores": 0},
        "dates": {"start": "2026-12-20", "end": "2026-12-23"},
        "services": [],
        "notes": "TEST_season_inside",
    }
    r = admin_session.post(f"{API}/quotations", json=body, timeout=30)
    assert r.status_code in (200, 201), r.text
    q = r.json()
    # season_applied should be present and equal to 'Alta'
    sa = q.get("season_applied") or q.get("payment", {}).get("season_applied")
    assert sa and "alta" in str(sa).lower(), f"expected season_applied=Alta, got {sa}; q keys={list(q.keys())}"


def test_quotation_outside_uses_base_price(admin_session):
    pkgs = admin_session.get(f"{API}/packages", timeout=30).json()
    gdl = next((p for p in pkgs if "guadalajara" in p["name"].lower() or p["code"].lower().startswith("gdl")), None)
    if not gdl:
        pytest.skip("seeded Guadalajara package not found")
    hotel = gdl["hotels"][0]
    client = admin_session.get(f"{API}/clients", timeout=30).json()[0]
    body = {
        "client_id": client["id"],
        "package_id": gdl["id"],
        "hotel_name": hotel["name"],
        "pax": {"rooms": [{"ocupacion": "doble", "count": 1}], "menores": 0},
        "dates": {"start": "2026-08-10", "end": "2026-08-13"},
        "services": [],
        "notes": "TEST_season_outside",
    }
    r = admin_session.post(f"{API}/quotations", json=body, timeout=30)
    assert r.status_code in (200, 201), r.text
    q = r.json()
    sa = q.get("season_applied") or q.get("payment", {}).get("season_applied")
    # outside: season_applied should be None / empty
    assert not sa, f"expected no season_applied outside, got {sa}"


# ----- Image upload -----

def test_image_upload_returns_fetchable_url(admin_session):
    # Minimal valid PNG
    png = (b"\x89PNG\r\n\x1a\n"
           b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
           b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x80&\x9b\x00\x00\x00\x00IEND\xaeB`\x82")
    files = {"file": ("test.png", io.BytesIO(png), "image/png")}
    r = admin_session.post(f"{API}/packages/upload-image", files=files, timeout=30)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    assert "url" in data
    url = data["url"]
    full = url if url.startswith("http") else f"{BASE_URL}{url}"
    r2 = requests.get(full, timeout=30)
    assert r2.status_code == 200, f"image not fetchable at {full}"


# ----- Cleanup -----

def test_zz_delete_test_package(admin_session):
    pid = getattr(pytest, "pkg_id", None)
    if not pid:
        pytest.skip("no test package to delete")
    r = admin_session.delete(f"{API}/packages/{pid}", timeout=30)
    assert r.status_code in (200, 204), r.text
    r2 = admin_session.get(f"{API}/packages/{pid}", timeout=30)
    assert r2.status_code == 404
