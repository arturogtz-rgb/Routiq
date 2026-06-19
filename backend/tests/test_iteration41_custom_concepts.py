"""Iteration 41 — Validaciones server-side de executive_id + GET /api/clients/{id} + custom items con fechas/horas por categoría."""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
EXEC_EMAIL = "ejecutivo@aventurate.mx"
EXEC_PASSWORD = "Demo2026!"
DEMO_CLIENT_WITH_EXECS = "c76a1ac7-1eaa-40b2-83bb-63d7cd52f218"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EXEC_EMAIL, "password": EXEC_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Login fallo: {r.status_code} {r.text}"
    return s


# --- GET /api/clients/{id} ---
class TestClientById:
    def test_get_client_by_id_includes_counts(self, session):
        r = session.get(f"{BASE_URL}/api/clients/{DEMO_CLIENT_WITH_EXECS}", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["id"] == DEMO_CLIENT_WITH_EXECS
        assert "executives_count" in data and data["executives_count"] >= 1
        assert "quotations_count" in data and isinstance(data["quotations_count"], int)
        assert isinstance(data.get("executives"), list) and len(data["executives"]) >= 1
        # ids reales para ejecutivos
        for ex in data["executives"]:
            assert ex.get("id") and ex.get("name")

    def test_get_client_404(self, session):
        r = session.get(f"{BASE_URL}/api/clients/nonexistent-id-zzz", timeout=10)
        assert r.status_code == 404


# --- Validación executive_id en POST /api/quotations ---
class TestExecutiveValidation:
    def _base_payload(self, client_id, executive_id=None):
        p = {
            "client_id": client_id,
            "type": "personalizado",
            "show_price_breakdown": True,
            "currency": "MXN",
            "dates": {"start": "2026-10-01", "end": "2026-10-04"},
            "pax": {"adults": 2, "children": 0},
            "custom_items": [
                {"category": "hospedaje", "name": "Hospedaje TEST", "net_price": 1000.0,
                 "price_type": "neto", "unit": "per_night", "qty": 3,
                 "checkin": "2026-10-01", "checkout": "2026-10-04", "nights": 3},
                {"category": "tour", "name": "City tour TEST", "net_price": 500.0,
                 "price_type": "neto", "unit": "per_person", "qty": 2,
                 "service_date": "2026-10-02", "start_time": "09:00"},
                {"category": "acceso", "name": "Acceso recinto TEST", "net_price": 200.0,
                 "price_type": "neto", "unit": "per_person", "qty": 2,
                 "service_date": "2026-10-03"},
            ],
            "custom_nights": 3,
        }
        if executive_id:
            p["executive_id"] = executive_id
        return p

    def test_post_quotation_missing_executive_returns_400(self, session):
        payload = self._base_payload(DEMO_CLIENT_WITH_EXECS)
        r = session.post(f"{BASE_URL}/api/quotations", json=payload, timeout=15)
        assert r.status_code == 400, r.text
        assert "ejecutivo" in r.json().get("detail", "").lower()

    def test_post_quotation_invalid_executive_returns_400(self, session):
        payload = self._base_payload(DEMO_CLIENT_WITH_EXECS, executive_id="fake-exec-id-zzz")
        r = session.post(f"{BASE_URL}/api/quotations", json=payload, timeout=15)
        assert r.status_code == 400, r.text
        assert "no pertenece" in r.json().get("detail", "").lower()

    def test_post_quotation_valid_executive_creates(self, session):
        # Obtener ejecutivo real
        client = session.get(f"{BASE_URL}/api/clients/{DEMO_CLIENT_WITH_EXECS}", timeout=10).json()
        execs = client.get("executives") or []
        assert len(execs) >= 1
        exec_id = execs[0]["id"]

        payload = self._base_payload(DEMO_CLIENT_WITH_EXECS, executive_id=exec_id)
        r = session.post(f"{BASE_URL}/api/quotations", json=payload, timeout=20)
        assert r.status_code == 201, r.text
        q = r.json()
        qid = q["id"]
        assert q.get("executive_id") == exec_id

        # GET /api/quotations/{id} para verificar custom_items propagan fechas/horas
        r2 = session.get(f"{BASE_URL}/api/quotations/{qid}", timeout=10)
        assert r2.status_code == 200
        det = r2.json()
        ci = det.get("custom_items") or []
        assert len(ci) == 3
        hosp = next((x for x in ci if x["category"] == "hospedaje"), None)
        tour = next((x for x in ci if x["category"] == "tour"), None)
        acc = next((x for x in ci if x["category"] == "acceso"), None)
        assert hosp and hosp.get("checkin") == "2026-10-01" and hosp.get("checkout") == "2026-10-04" and (hosp.get("nights") or 0) == 3
        assert tour and tour.get("service_date") == "2026-10-02" and tour.get("start_time") == "09:00"
        assert acc and acc.get("service_date") == "2026-10-03"

        # Public link
        pl = session.post(f"{BASE_URL}/api/quotations/{qid}/public-link", timeout=10)
        assert pl.status_code == 200
        token = pl.json().get("token")
        assert token

        # GET público
        rp = requests.get(f"{BASE_URL}/api/public/quotations/{token}", timeout=10)
        assert rp.status_code == 200
        pub = rp.json()
        pub_items = (pub.get("quotation") or pub).get("custom_items") or pub.get("custom_items") or []
        # Tambien puede venir en items (kind=custom) con campos category/checkin/checkout/service_date/start_time
        items = (pub.get("quotation") or pub).get("items") or pub.get("items") or []
        # Asegurar al menos 1 lookup OK
        # buscar por category en custom_items o items
        def find_cat(arr, cat):
            return next((x for x in arr if x.get("category") == cat), None)
        h2 = find_cat(pub_items, "hospedaje") or find_cat(items, "hospedaje")
        t2 = find_cat(pub_items, "tour") or find_cat(items, "tour")
        a2 = find_cat(pub_items, "acceso") or find_cat(items, "acceso")
        assert h2 and (h2.get("checkin") or "") == "2026-10-01" and (h2.get("checkout") or "") == "2026-10-04"
        assert t2 and (t2.get("service_date") or "") == "2026-10-02" and (t2.get("start_time") or "") == "09:00"
        assert a2 and (a2.get("service_date") or "") == "2026-10-03"

        # PDF auth
        rpdf = session.get(f"{BASE_URL}/api/quotations/{qid}/pdf", timeout=20)
        assert rpdf.status_code == 200
        assert rpdf.content[:4] == b"%PDF"
        body = rpdf.content
        # Buscar fechas: el PDF puede formatear "10 oct 2026" etc.; verificar al menos presencia de horas y "noches"
        # No podemos asegurar formato exacto sin parsear PDF, así que comprobamos al menos %PDF y tamaño razonable
        assert len(body) > 2000

        # Cleanup
        session.delete(f"{BASE_URL}/api/quotations/{qid}", timeout=10)
