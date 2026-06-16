"""Iteration 28: presentation_text + custom item service_date/start_time/end_time + AI/PDF/public."""
import os
import requests
import pytest

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def client_id(admin_session):
    payload = {"name": "TEST_iter28 Cliente", "phone": "5512345678", "email": "test_iter28@example.com", "channel": "directo"}
    # Try create
    r = admin_session.post(f"{BASE_URL}/api/clients", json=payload, timeout=15)
    if r.status_code in (200, 201):
        return r.json()["id"]
    # Maybe existing → fetch list
    r2 = admin_session.get(f"{BASE_URL}/api/clients", timeout=15)
    for c in r2.json().get("items", r2.json() if isinstance(r2.json(), list) else []):
        if c.get("email") == payload["email"]:
            return c["id"]
    pytest.skip("could not create client")


@pytest.fixture(scope="module")
def custom_quotation(admin_session, client_id):
    payload = {
        "client_id": client_id,
        "type": "personalizado",
        "custom_title": "TEST_iter28 Programa",
        "dates": {"start": "2026-03-01", "end": "2026-03-03"},
        "pax": {"adultos": 2, "menores": 0, "rooms": []},
        "custom_nights": 2,
        "custom_rooms": 1,
        "custom_items": [
            {"category": "hospedaje", "name": "Hotel Demo", "description": "Suite vista mar",
             "net_price": 1500, "unit": "per_night", "qty": 2,
             "service_date": "2026-03-01", "start_time": "15:00", "end_time": "12:00"},
            {"category": "tour", "name": "City Tour", "description": "Tour por el centro",
             "net_price": 800, "unit": "per_person", "qty": 2,
             "service_date": "2026-03-02", "start_time": "09:00", "end_time": "13:00"},
        ],
        "custom_itinerary": [
            {"day": 1, "title": "Llegada", "description": "Check-in y descanso"},
            {"day": 2, "title": "Tour", "description": "Día completo"},
        ],
        "custom_includes": ["Desayunos", "Traslado aeropuerto"],
        "custom_excludes": ["Vuelos", "Propinas"],
        "presentation_text": "Bienvenidos a esta experiencia única en Jalisco. Disfrutarán de hospedaje premium y tours guiados.",
        "notes": "Notas internas",
    }
    r = admin_session.post(f"{BASE_URL}/api/quotations", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create custom quotation failed: {r.status_code} {r.text}"
    data = r.json()
    assert "id" in data
    return data


# ---------------- Tests ----------------

class TestCustomQuotationPersistence:
    def test_presentation_text_persisted(self, admin_session, custom_quotation):
        qid = custom_quotation["id"]
        r = admin_session.get(f"{BASE_URL}/api/quotations/{qid}", timeout=15)
        assert r.status_code == 200
        q = r.json()
        assert q.get("presentation_text", "").startswith("Bienvenidos")
        assert q.get("type") == "personalizado"

    def test_custom_items_have_datetime_fields(self, admin_session, custom_quotation):
        qid = custom_quotation["id"]
        r = admin_session.get(f"{BASE_URL}/api/quotations/{qid}", timeout=15)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) >= 2
        # Find by name (because pricing recomputes items)
        hosp = next((i for i in items if "Hotel Demo" in (i.get("name") or "") or "Hotel Demo" in (i.get("description") or "")), None)
        tour = next((i for i in items if "City Tour" in (i.get("name") or "")), None)
        assert hosp is not None, f"hospedaje not found in items: {items}"
        assert tour is not None, f"tour not found in items: {items}"
        assert hosp.get("service_date") == "2026-03-01"
        assert hosp.get("start_time") == "15:00"
        assert hosp.get("end_time") == "12:00"
        assert tour.get("service_date") == "2026-03-02"
        assert tour.get("description") == "Tour por el centro"


class TestPackagePresentationText:
    def test_package_quotation_accepts_presentation_text(self, admin_session, client_id):
        # Use existing package — list and pick first
        rp = admin_session.get(f"{BASE_URL}/api/packages", timeout=15)
        assert rp.status_code == 200
        packages = rp.json() if isinstance(rp.json(), list) else rp.json().get("items", [])
        active = [p for p in packages if p.get("status") == "active"]
        if not active:
            pytest.skip("no active package available")
        pack = active[0]
        payload = {
            "client_id": client_id,
            "type": "paquete",
            "package_id": pack["id"],
            "hotel_name": pack.get("hotels", [{}])[0].get("name", "") if pack.get("hotels") else "",
            "dates": {"start": "2026-04-01", "end": "2026-04-04"},
            "pax": {"adultos": 2, "menores": 0, "rooms": [{"adultos": 2, "menores": 0}]},
            "services": [],
            "notes": "TEST_iter28 paquete",
            "presentation_text": "Texto de presentación para paquete demo.",
        }
        r = admin_session.post(f"{BASE_URL}/api/quotations", json=payload, timeout=30)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        qid = r.json()["id"]
        rg = admin_session.get(f"{BASE_URL}/api/quotations/{qid}", timeout=15)
        assert rg.status_code == 200
        assert rg.json().get("presentation_text", "").startswith("Texto de presentación")


class TestPDF:
    def test_pdf_returned_for_custom_with_presentation(self, admin_session, custom_quotation):
        qid = custom_quotation["id"]
        r = admin_session.get(f"{BASE_URL}/api/quotations/{qid}/pdf", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        # PDF magic bytes
        assert r.content[:4] == b"%PDF", f"not PDF content (first bytes: {r.content[:10]})"
        assert len(r.content) > 1000


class TestPublicLink:
    def test_public_link_exposes_presentation_and_custom_items(self, admin_session, custom_quotation):
        qid = custom_quotation["id"]
        # Generate public link
        r = admin_session.post(f"{BASE_URL}/api/quotations/{qid}/public-link", timeout=15)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        token = r.json().get("token") or r.json().get("public_link", {}).get("token")
        if not token:
            # Maybe nested
            pl = r.json().get("public_link") or r.json()
            token = pl.get("token") if isinstance(pl, dict) else None
        assert token, f"no token in response: {r.json()}"

        rp = requests.get(f"{BASE_URL}/api/public/quotations/{token}", timeout=15)
        assert rp.status_code == 200, f"{rp.status_code} {rp.text[:200]}"
        data = rp.json()
        # quotation could be at root or under 'quotation'
        q = data.get("quotation") or data
        assert q.get("presentation_text", "").startswith("Bienvenidos")
        items = q.get("items", [])
        hosp = next((i for i in items if "Hotel Demo" in (i.get("name") or "")), None)
        assert hosp is not None, f"items: {items}"
        assert hosp.get("service_date") == "2026-03-01"
        assert hosp.get("start_time") == "15:00"
        assert hosp.get("description") == "Suite vista mar"


class TestAIPresentation:
    def test_ai_presentation_returns_503_or_200(self, admin_session):
        # In preview, BYOK not configured → 503 expected. Either is valid.
        payload = {"client_name": "Cliente Demo", "title": "Programa Demo",
                   "date_start": "2026-03-01", "date_end": "2026-03-03",
                   "adultos": 2, "menores": 0}
        r = admin_session.post(f"{BASE_URL}/api/ai/presentation", json=payload, timeout=30)
        assert r.status_code in (200, 503), f"unexpected status: {r.status_code} {r.text}"
        if r.status_code == 200:
            assert "text" in r.json() and isinstance(r.json()["text"], str)
        else:
            # error in Spanish ideally
            assert "IA" in r.text or "no disponible" in r.text.lower() or "no" in r.text.lower()


# ---------------- Cleanup ----------------
@pytest.fixture(scope="module", autouse=True)
def _cleanup(admin_session, custom_quotation):
    yield
    try:
        admin_session.delete(f"{BASE_URL}/api/quotations/{custom_quotation['id']}", timeout=10)
    except Exception:
        pass
