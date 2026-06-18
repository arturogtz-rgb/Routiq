"""Iteration 9 — Advanced Master Site Editor.

Tests the new GET/PATCH/PUBLISH cycle for landing.sections + pricing_*.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://neto-a-publico.preview.emergentagent.com").rstrip("/")

SUPER = {"email": "owner@routiq.mx", "password": "Routiq2026!"}


@pytest.fixture(scope="module")
def super_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=SUPER, timeout=15)
    assert r.status_code == 200, f"super login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def anon_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- public endpoint (no auth) ---------------------------------------------
class TestPublic:
    def test_public_returns_sections_and_pricing(self, anon_client):
        r = anon_client.get(f"{BASE_URL}/api/site-settings/public", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "landing" in data and "login" in data
        landing = data["landing"]
        # sections list
        secs = landing.get("sections")
        assert isinstance(secs, list) and len(secs) >= 4
        keys = [s["key"] for s in secs]
        for k in ("features", "how", "pricing", "final_cta"):
            assert k in keys, f"missing section {k}"
        for s in secs:
            assert "visible" in s and isinstance(s["visible"], bool)
            assert "label" in s
        # pricing
        assert "pricing_title" in landing
        assert "pricing_subtitle" in landing
        tiers = landing.get("pricing_tiers")
        assert isinstance(tiers, list) and len(tiers) >= 1
        for t in tiers:
            assert "name" in t and "price" in t and "cta" in t
            assert "perks" in t and isinstance(t["perks"], list)


# --- auth -------------------------------------------------------------------
class TestAuth:
    def test_get_settings_requires_super_admin(self, anon_client):
        r = anon_client.get(f"{BASE_URL}/api/site-settings", timeout=15)
        assert r.status_code in (401, 403)

    def test_patch_requires_super_admin(self, anon_client):
        r = anon_client.patch(f"{BASE_URL}/api/site-settings", json={"landing": {}}, timeout=15)
        assert r.status_code in (401, 403)

    def test_publish_requires_super_admin(self, anon_client):
        r = anon_client.post(f"{BASE_URL}/api/site-settings/publish", timeout=15)
        assert r.status_code in (401, 403)


# --- editor flow ------------------------------------------------------------
class TestEditorFlow:
    """End-to-end: GET draft → PATCH (reorder + hide + edit pricing) → PUBLISH
    → GET /public verifies the changes flowed through."""

    @pytest.fixture(scope="class")
    def baseline(self, super_client):
        r = super_client.get(f"{BASE_URL}/api/site-settings", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "draft" in body and "published" in body
        return body

    def test_get_super_returns_draft_and_published(self, baseline):
        for k in ("draft", "published"):
            landing = baseline[k]["landing"]
            assert isinstance(landing.get("sections"), list)
            assert isinstance(landing.get("pricing_tiers"), list)

    def test_patch_reorder_hide_and_edit_pricing(self, super_client, baseline):
        landing = dict(baseline["draft"]["landing"])
        # 1. reorder: swap features and how
        secs = [dict(s) for s in landing["sections"]]
        # Find indices
        idx_f = next(i for i, s in enumerate(secs) if s["key"] == "features")
        idx_h = next(i for i, s in enumerate(secs) if s["key"] == "how")
        secs[idx_f], secs[idx_h] = secs[idx_h], secs[idx_f]
        # 2. hide pricing
        for s in secs:
            if s["key"] == "pricing":
                s["visible"] = False
        # 3. edit pricing title + tiers
        new_title = "TEST_ITER9 — Precios de prueba"
        new_tiers = [
            {"name": "TEST_Basico", "price": "$1", "period": "/mes", "highlight": False,
             "cta": "Empezar", "perks": ["uno", "dos"]},
            {"name": "TEST_Pro", "price": "$2", "period": "/mes", "highlight": True,
             "cta": "Probar", "perks": ["alfa", "beta", "gamma"]},
        ]
        payload = {"landing": {
            "sections": secs,
            "pricing_title": new_title,
            "pricing_tiers": new_tiers,
        }}
        r = super_client.patch(f"{BASE_URL}/api/site-settings", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        merged = r.json()
        ml = merged["landing"]
        # verify response reflects changes
        assert ml["pricing_title"] == new_title
        assert [t["name"] for t in ml["pricing_tiers"]] == ["TEST_Basico", "TEST_Pro"]
        order = [s["key"] for s in ml["sections"]]
        assert order.index("how") < order.index("features")
        assert any(s["key"] == "pricing" and s["visible"] is False for s in ml["sections"])

    def test_get_draft_persists(self, super_client):
        r = super_client.get(f"{BASE_URL}/api/site-settings", timeout=15)
        assert r.status_code == 200
        d = r.json()["draft"]["landing"]
        assert d["pricing_title"] == "TEST_ITER9 — Precios de prueba"
        order = [s["key"] for s in d["sections"]]
        assert order.index("how") < order.index("features")

    def test_publish_propagates_to_public(self, super_client, anon_client):
        r = super_client.post(f"{BASE_URL}/api/site-settings/publish", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        # Public endpoint should now show new title + hidden pricing + reordered
        r2 = anon_client.get(f"{BASE_URL}/api/site-settings/public", timeout=15)
        assert r2.status_code == 200
        landing = r2.json()["landing"]
        assert landing["pricing_title"] == "TEST_ITER9 — Precios de prueba"
        assert [t["name"] for t in landing["pricing_tiers"]] == ["TEST_Basico", "TEST_Pro"]
        order = [s["key"] for s in landing["sections"]]
        assert order.index("how") < order.index("features")
        pricing_sec = next(s for s in landing["sections"] if s["key"] == "pricing")
        assert pricing_sec["visible"] is False


# --- cleanup: restore defaults so other tests / UI are not left broken ------
class TestCleanup:
    def test_restore_defaults(self, super_client, anon_client):
        # Restore a clean order/visibility and original pricing data
        default_sections = [
            {"key": "features", "label": "Características", "visible": True},
            {"key": "how", "label": "Cómo funciona", "visible": True},
            {"key": "pricing", "label": "Planes / Precios", "visible": True},
            {"key": "final_cta", "label": "Llamado final (CTA)", "visible": True},
        ]
        default_tiers = [
            {"name": "Starter", "price": "$890", "period": "/mes", "highlight": False, "cta": "Comenzar",
             "perks": ["1 número WhatsApp", "Hasta 3 ejecutivos", "Cotizaciones ilimitadas", "PDF con branding"]},
            {"name": "Pro", "price": "$1,890", "period": "/mes", "highlight": True, "cta": "Comenzar",
             "perks": ["Hasta 5 números", "Hasta 15 ejecutivos", "IA operativa", "Kanban + alertas", "Motor de precios avanzado"]},
            {"name": "Enterprise", "price": "A medida", "period": "/mes", "highlight": False, "cta": "Comenzar",
             "perks": ["Números ilimitados", "Meta API oficial", "SLA dedicado", "Onboarding + capacitación"]},
        ]
        payload = {"landing": {
            "sections": default_sections,
            "pricing_pill": "Planes",
            "pricing_title": "Precios simples que crecen con tu operación.",
            "pricing_subtitle": "MXN al mes por empresa. Sin costo por mensaje. Sin costo por usuario extra hasta el límite del plan.",
            "pricing_tiers": default_tiers,
        }}
        r = super_client.patch(f"{BASE_URL}/api/site-settings", json=payload, timeout=15)
        assert r.status_code == 200
        r = super_client.post(f"{BASE_URL}/api/site-settings/publish", timeout=15)
        assert r.status_code == 200
        # confirm
        r = anon_client.get(f"{BASE_URL}/api/site-settings/public", timeout=15)
        landing = r.json()["landing"]
        assert landing["pricing_title"].startswith("Precios simples")
        assert all(s["visible"] for s in landing["sections"])
