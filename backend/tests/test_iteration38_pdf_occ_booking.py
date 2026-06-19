"""
Iteration 38 tests:
- GET /api/public/quotations/{token}/pdf -> 200 application/pdf binary (token E4cWS)
- GET /api/public/quotations/{token} payload includes occupancy_prices with 'occ' key
- GET /api/public/booking-confirmation/{token} returns confirmation+company with trip_start/trip_end
- GET /api/public/booking-confirmation/{token}/pdf -> 200 application/pdf
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://quotation-layout-v2.preview.emergentagent.com").rstrip("/")
QUOT_TOKEN = "E4cWS--ucnOiioZotwHcD8OM"
BOOK_TOKEN = "NVhfGoFku3Mh2CN6B967tA"


# --- Public quotation PDF ---
class TestPublicQuotationPdf:
    def test_pdf_200_and_content_type(self):
        r = requests.get(f"{BASE_URL}/api/public/quotations/{QUOT_TOKEN}/pdf", timeout=60)
        assert r.status_code == 200, r.text[:300]
        ct = r.headers.get("content-type", "")
        assert "application/pdf" in ct, ct
        assert r.content[:5] == b"%PDF-", r.content[:20]
        # sanity: PDF size > 1KB
        assert len(r.content) > 1024


# --- Public quotation JSON with occupancy_prices ---
class TestPublicQuotationOcc:
    def test_payload_has_occupancy_prices_with_occ_keys(self):
        r = requests.get(f"{BASE_URL}/api/public/quotations/{QUOT_TOKEN}", timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        q = data.get("quotation") or {}
        rows = q.get("occupancy_prices") or []
        # show_all_occupancies effective via populated rows
        assert isinstance(rows, list) and len(rows) > 0, "occupancy_prices must be populated"
        occ_keys = {r.get("occ") for r in rows}
        expected = {"sencilla", "doble", "triple", "cuadruple", "menor"}
        assert expected.issubset(occ_keys), f"expected {expected} subset of {occ_keys}"
        # doble = 8900 per spec
        doble = next((r for r in rows if r.get("occ") == "doble"), None)
        assert doble and doble.get("price") == 8900, doble
        for row in rows:
            assert "label" in row and "price" in row and "occ" in row


# --- Public booking confirmation JSON ---
class TestPublicBookingConfirmation:
    def test_payload_200_with_trip_dates_and_company(self):
        r = requests.get(f"{BASE_URL}/api/public/booking-confirmation/{BOOK_TOKEN}", timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        conf = data.get("confirmation") or {}
        company = data.get("company") or {}
        assert conf.get("code"), "confirmation.code missing"
        assert conf.get("trip_start"), "trip_start missing"
        assert conf.get("trip_end"), "trip_end missing"
        # Expected dates per request
        assert conf["trip_start"] == "2026-08-10", conf["trip_start"]
        assert conf["trip_end"] == "2026-08-13", conf["trip_end"]
        assert company.get("name"), "company.name missing"


# --- Public booking confirmation PDF ---
class TestPublicBookingPdf:
    def test_pdf_200_and_content_type(self):
        r = requests.get(f"{BASE_URL}/api/public/booking-confirmation/{BOOK_TOKEN}/pdf", timeout=60)
        assert r.status_code == 200, r.text[:300]
        ct = r.headers.get("content-type", "")
        assert "application/pdf" in ct, ct
        assert r.content[:5] == b"%PDF-"
        assert len(r.content) > 1024


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
