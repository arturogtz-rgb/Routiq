"""Fase C tests:
- Catalog analytics (auth, period filter, totals/packages shape)
- Public view tracking increments analytics views
- Open Graph share endpoint (HTML, og:title, refresh meta)
- Lead -> quotation funnel via from_request field
- Multi-hotel template -> package conversion (2 hospedaje items -> 2 hotels)
- Resend test endpoint returns 400 when not configured
"""
import os
import re
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@aventurate.mx"
ADMIN_PASS = "Demo2026!"
SLUG = "aventurate"
CODE = "GDL-TEQ-3N"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


# --- Analytics auth + shape ---
class TestCatalogAnalytics:
    def test_requires_auth(self):
        r = requests.get(f"{API}/catalog/analytics", params={"period": "month"}, timeout=30)
        assert r.status_code == 401, f"expected 401 without auth, got {r.status_code}"

    def test_analytics_month_shape(self, admin_session):
        r = admin_session.get(f"{API}/catalog/analytics", params={"period": "month"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["period"] == "month"
        assert data["days"] == 30
        assert "totals" in data and "packages" in data
        for k in ("views", "leads", "quotations", "view_to_lead", "lead_to_quote"):
            assert k in data["totals"], f"missing totals.{k}"
        if data["packages"]:
            p = data["packages"][0]
            for k in ("package_id", "code", "name", "views", "leads", "quotations",
                     "view_to_lead", "lead_to_quote", "view_to_quote"):
                assert k in p

    def test_analytics_week_shape(self, admin_session):
        r = admin_session.get(f"{API}/catalog/analytics", params={"period": "week"}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["period"] == "week" and data["days"] == 7


# --- View tracking integration ---
class TestViewTracking:
    def test_views_increase_after_public_hits(self, admin_session):
        before = admin_session.get(f"{API}/catalog/analytics", params={"period": "week"}, timeout=30).json()
        before_views = next((p["views"] for p in before["packages"] if p["code"] == CODE), 0)

        for _ in range(2):
            rp = requests.get(f"{API}/public/package/{SLUG}/{CODE}", timeout=30)
            assert rp.status_code == 200, rp.text
        time.sleep(0.5)

        after = admin_session.get(f"{API}/catalog/analytics", params={"period": "week"}, timeout=30).json()
        after_views = next((p["views"] for p in after["packages"] if p["code"] == CODE), 0)
        assert after_views >= before_views + 2, f"expected views to grow by 2; before={before_views} after={after_views}"


# --- Open Graph share endpoint ---
class TestOGShare:
    def _valid_token(self, admin_session):
        r = admin_session.get(f"{API}/quotations", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        if not rows:
            pytest.skip("no quotations to test share endpoint")
        qid = rows[0]["id"]
        rl = admin_session.post(f"{API}/quotations/{qid}/public-link", timeout=30)
        assert rl.status_code in (200, 201), rl.text
        return rl.json()["token"]

    def test_invalid_token_returns_html_200(self):
        r = requests.get(f"{API}/share/q/invalid-token-xyz", timeout=30, allow_redirects=False)
        assert r.status_code == 200, r.status_code
        assert "text/html" in r.headers.get("content-type", "")
        assert "<html" in r.text.lower()
        # generic title
        assert "og:title" in r.text

    def test_valid_token_has_tenant_og_and_refresh(self, admin_session):
        token = self._valid_token(admin_session)
        r = requests.get(f"{API}/share/q/{token}", timeout=30, allow_redirects=False)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        html = r.text
        # og:title contains company name (Aventúrate)
        m = re.search(r'og:title"\s+content="([^"]+)"', html)
        assert m, "no og:title meta"
        og_title = m.group(1)
        assert "Cotización" in og_title, f"og:title missing 'Cotización': {og_title}"
        # Should include the company name or its prefix (handle html escaping)
        assert ("Aventúrate" in og_title) or ("Aventu" in og_title) or ("Aventrate" in og_title), og_title
        # refresh meta and SPA redirect
        assert 'http-equiv="refresh"' in html
        assert f"/q/{token}" in html


# --- Funnel from_request ---
class TestFunnelLink:
    def test_quotation_persists_from_request_and_analytics_includes(self, admin_session):
        # find a client and a package
        clients = admin_session.get(f"{API}/clients", timeout=30).json()
        if not clients:
            pytest.skip("no clients")
        client_id = clients[0]["id"]
        packs = admin_session.get(f"{API}/packages", timeout=30).json()
        pack = next((p for p in packs if p.get("code") == CODE), packs[0] if packs else None)
        if not pack:
            pytest.skip("no packages")

        lead_id = f"TEST_LEAD_{uuid.uuid4().hex[:8]}"
        # baseline quotation count for this package within week
        before = admin_session.get(f"{API}/catalog/analytics", params={"period": "week"}, timeout=30).json()
        before_q = next((p["quotations"] for p in before["packages"] if p["package_id"] == pack["id"]), 0)

        hotel_name = (pack.get("hotels") or [{}])[0].get("name", "")
        payload = {
            "type": "paquete",
            "client_id": client_id,
            "package_id": pack["id"],
            "hotel_name": hotel_name,
            "from_request": lead_id,
            "dates": {"check_in": "2026-03-01", "check_out": "2026-03-04"},
            "pax": {"adults": 2, "children": 0},
            "items": [],
        }
        r = admin_session.post(f"{API}/quotations", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        q = r.json()
        qid = q.get("id")
        # verify persistence via GET
        rget = admin_session.get(f"{API}/quotations/{qid}", timeout=30)
        assert rget.status_code == 200
        got = rget.json()
        assert got.get("from_request") == lead_id, f"from_request not persisted: {got.get('from_request')}"

        # analytics quotations count for this package should now be greater
        after = admin_session.get(f"{API}/catalog/analytics", params={"period": "week"}, timeout=30).json()
        after_q = next((p["quotations"] for p in after["packages"] if p["package_id"] == pack["id"]), 0)
        assert after_q >= before_q + 1, f"analytics quotations did not increase: before={before_q} after={after_q}"


# --- Multi-hotel template -> package ---
class TestMultiHotelPublish:
    def test_two_hospedaje_become_two_hotels(self, admin_session):
        unique = uuid.uuid4().hex[:6]
        tpl_payload = {
            "name": f"TEST_TPL_MULTIHOTEL_{unique}",
            "nights": 3,
            "custom_items": [
                {"category": "hospedaje", "concept": f"Hotel A {unique}",
                 "net_price": 1000, "qty": 1, "unit": "per_night"},
                {"category": "hospedaje", "concept": f"Hotel B {unique}",
                 "net_price": 1500, "qty": 1, "unit": "per_night"},
                {"category": "traslado", "concept": "Translado AP", "net_price": 200, "qty": 1, "unit": "per_group"},
            ],
        }
        r = admin_session.post(f"{API}/templates", json=tpl_payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        tpl = r.json()
        tpl_id = tpl["id"]

        rp = admin_session.post(f"{API}/templates/{tpl_id}/publish-as-package", json={}, timeout=60)
        assert rp.status_code in (200, 201), rp.text
        pack = rp.json()
        hotels = pack.get("hotels") or []
        assert len(hotels) == 2, f"expected 2 hotels from 2 hospedaje items, got {len(hotels)}: {[h.get('name') for h in hotels]}"
        for h in hotels:
            pbo = h.get("prices_by_occupancy") or {}
            assert any(v and v > 0 for v in pbo.values()), f"hotel {h.get('name')} has no public prices: {pbo}"

        # cleanup: try deleting created package & template (best-effort)
        try:
            if pack.get("id"):
                admin_session.delete(f"{API}/packages/{pack['id']}", timeout=15)
            admin_session.delete(f"{API}/templates/{tpl_id}", timeout=15)
        except Exception:
            pass


# --- Resend test endpoint ---
class TestResendTest:
    def test_returns_400_when_not_configured(self, admin_session):
        r = admin_session.post(f"{API}/companies/me/test-resend",
                               json={"to": "qa@example.com"}, timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
        # Spanish message hint
        msg = r.text.lower()
        assert any(w in msg for w in ("resend", "configurad", "clave", "api")), r.text
