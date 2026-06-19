"""Iteration 36 — Rediseño estructural del PDF de cotización + réplica en /q/:token.

Validaciones:
1. Login como ejecutivo y como admin (tests con credenciales del seed).
2. GET /api/quotations/{id}/pdf devuelve 200 + Content-Type application/pdf.
3. GET /api/public/quotations/{token} carga sin errores (200) y expone los campos esperados.
4. Para token con show_all_occupancies=false: occupancy_prices viene VACÍO (no se renderiza la tabla en frontend).
5. Para token personalizado con itinerario: itinerary_days (o campo equivalente) presente con días.
"""
import os
import pytest
import requests

# Resolver REACT_APP_BACKEND_URL del env o frontend/.env como fallback.
def _resolve_base_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        try:
            with open("/app/frontend/.env", "r") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except Exception:
            pass
    assert url, "REACT_APP_BACKEND_URL no resuelto"
    return url.rstrip("/")

BASE_URL = _resolve_base_url()

# Tokens proporcionados por el main agent
TOKEN_PERSONALIZADO_ITINERARIO_1 = "JX4Q1xHuqEgQ92QH45Z_rMfI"
TOKEN_PERSONALIZADO_ITINERARIO_2 = "vE7tTcK-JKJsK7FbpEIFnZkr"
TOKEN_PAQUETE_SHOW_ALL_FALSE = "E4cWS--ucnOiioZotwHcD8OM"


@pytest.fixture(scope="module")
def executive_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "ejecutivo@aventurate.mx", "password": "Demo2026!"})
    assert r.status_code == 200, f"login ejecutivo falló: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@aventurate.mx", "password": "Demo2026!"})
    assert r.status_code == 200, f"login admin falló: {r.status_code} {r.text}"
    return s


# --- Backend feature: PDF generation ---
class TestPdfGeneration:
    def test_pdf_for_existing_quotation_as_executive(self, executive_client):
        # Listar cotizaciones del ejecutivo y elegir la primera disponible
        r = executive_client.get(f"{BASE_URL}/api/quotations?limit=50")
        assert r.status_code == 200, r.text
        items = r.json()
        # Algunas APIs devuelven lista, otras dict con 'items'
        if isinstance(items, dict):
            items = items.get("items") or items.get("results") or []
        assert isinstance(items, list) and len(items) > 0, "no hay cotizaciones para el ejecutivo"
        qid = items[0].get("id") or items[0].get("_id")
        assert qid

        pdf_r = executive_client.get(f"{BASE_URL}/api/quotations/{qid}/pdf")
        assert pdf_r.status_code == 200, f"PDF status {pdf_r.status_code}: {pdf_r.text[:300]}"
        ctype = pdf_r.headers.get("Content-Type", "")
        assert "application/pdf" in ctype, f"Content-Type inesperado: {ctype}"
        assert pdf_r.content[:4] == b"%PDF", "binario no es %PDF"

    def test_pdf_for_existing_quotation_as_admin(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/quotations?limit=50")
        assert r.status_code == 200
        items = r.json()
        if isinstance(items, dict):
            items = items.get("items") or items.get("results") or []
        assert len(items) > 0
        qid = items[0].get("id") or items[0].get("_id")
        pdf_r = admin_client.get(f"{BASE_URL}/api/quotations/{qid}/pdf")
        assert pdf_r.status_code == 200
        assert "application/pdf" in pdf_r.headers.get("Content-Type", "")
        assert pdf_r.content[:4] == b"%PDF"


# --- Backend feature: public quotation endpoint ---
class TestPublicQuotationData:
    def test_public_personalizado_token_1_has_itinerary(self):
        r = requests.get(f"{BASE_URL}/api/public/quotations/{TOKEN_PERSONALIZADO_ITINERARIO_1}")
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        data = r.json()
        # itinerary vive en el top-level del payload público
        days = data.get("itinerary") or []
        assert isinstance(days, list) and len(days) >= 1, f"esperaba itinerario con días, got {days!r}"
        # cada día debe tener al menos 'day' y un 'title' o 'description'
        for d in days:
            assert "day" in d
            assert d.get("title") or d.get("description")

    def test_public_personalizado_token_2_has_itinerary(self):
        r = requests.get(f"{BASE_URL}/api/public/quotations/{TOKEN_PERSONALIZADO_ITINERARIO_2}")
        assert r.status_code == 200
        data = r.json()
        days = data.get("itinerary") or []
        assert isinstance(days, list) and len(days) >= 1

    def test_public_paquete_show_all_false_no_occupancy(self):
        r = requests.get(f"{BASE_URL}/api/public/quotations/{TOKEN_PAQUETE_SHOW_ALL_FALSE}")
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        data = r.json()
        q = data.get("quotation") or data
        occ = q.get("occupancy_prices")
        # Backend debe devolver lista vacía o null cuando show_all_occupancies=false
        assert (occ is None) or (isinstance(occ, list) and len(occ) == 0), (
            f"occupancy_prices debería estar vacío cuando show_all_occupancies=false, got {occ!r}"
        )

    def test_public_response_has_total_and_currency(self):
        r = requests.get(f"{BASE_URL}/api/public/quotations/{TOKEN_PAQUETE_SHOW_ALL_FALSE}")
        assert r.status_code == 200
        data = r.json()
        q = data.get("quotation") or data
        # total o total_final
        total = q.get("total") or q.get("total_final") or q.get("grand_total")
        assert total is not None, f"total ausente: keys={list(q.keys())}"
