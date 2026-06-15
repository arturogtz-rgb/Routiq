"""
Iteration 6 — Tests for v1.3 features:
- Site settings (Landing/Login editor) — super_admin only, draft/publish/reset
- Image upload
- Web Push VAPID + subscribe/unsubscribe
"""
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://routiq-master-editor.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

SUPER = {"email": "owner@routiq.mx", "password": "Routiq2026!"}
ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}
EXEC = {"email": "ejecutivo@aventurate.mx", "password": "Demo2026!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def super_session():
    return _login(SUPER)


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def exec_session():
    return _login(EXEC)


# ------------------- Site Settings (public) -------------------
class TestSiteSettingsPublic:
    def test_public_no_auth_required(self):
        r = requests.get(f"{API}/site-settings/public", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "landing" in data and "login" in data
        # Defaults must merge — fields present
        assert isinstance(data["landing"], dict)
        assert isinstance(data["login"], dict)


# ------------------- Site Settings (admin draft/publish) -------------------
class TestSiteSettingsAdmin:
    def test_super_admin_get_returns_draft_and_published(self, super_session):
        r = super_session.get(f"{API}/site-settings", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "draft" in data and "published" in data

    def test_exec_forbidden(self, exec_session):
        r = exec_session.get(f"{API}/site-settings", timeout=15)
        assert r.status_code == 403

    def test_admin_forbidden(self, admin_session):
        r = admin_session.get(f"{API}/site-settings", timeout=15)
        assert r.status_code == 403

    def test_patch_updates_draft_only(self, super_session):
        # Capture published before
        before = requests.get(f"{API}/site-settings/public", timeout=15).json()
        before_hero = before["landing"].get("hero_title")

        # Snapshot current published so we can restore at the end
        cur = super_session.get(f"{API}/site-settings", timeout=15).json()
        original_published_landing = cur["published"]["landing"]
        original_published_login = cur["published"]["login"]

        token = "TEST_HERO_DRAFT_X"
        r = super_session.patch(f"{API}/site-settings", json={"landing": {"hero_title": token}}, timeout=15)
        assert r.status_code == 200
        assert r.json()["landing"]["hero_title"] == token

        # Public should NOT reflect draft
        pub = requests.get(f"{API}/site-settings/public", timeout=15).json()
        assert pub["landing"].get("hero_title") == before_hero, "Public changed before publish!"

        # GET site-settings — draft should reflect the new title
        cur2 = super_session.get(f"{API}/site-settings", timeout=15).json()
        assert cur2["draft"]["landing"]["hero_title"] == token

        # Now publish — public should reflect token
        rp = super_session.post(f"{API}/site-settings/publish", timeout=15)
        assert rp.status_code == 200
        pub2 = requests.get(f"{API}/site-settings/public", timeout=15).json()
        assert pub2["landing"]["hero_title"] == token

        # Restore: patch the draft back to original published, then publish
        restore_payload = {"landing": original_published_landing or {}, "login": original_published_login or {}}
        rrest = super_session.patch(f"{API}/site-settings", json=restore_payload, timeout=15)
        assert rrest.status_code == 200
        super_session.post(f"{API}/site-settings/publish", timeout=15)
        pub3 = requests.get(f"{API}/site-settings/public", timeout=15).json()
        # No assertion on exact value (defaults vs original), but ensure it's not our test token
        assert pub3["landing"].get("hero_title") != token

    def test_reset_draft(self, super_session):
        # Set a junk draft
        super_session.patch(f"{API}/site-settings", json={"landing": {"hero_title": "TEST_JUNK_DRAFT"}}, timeout=15)
        cur = super_session.get(f"{API}/site-settings", timeout=15).json()
        assert cur["draft"]["landing"]["hero_title"] == "TEST_JUNK_DRAFT"

        rr = super_session.post(f"{API}/site-settings/reset-draft", timeout=15)
        assert rr.status_code == 200
        cur2 = super_session.get(f"{API}/site-settings", timeout=15).json()
        # After reset, draft.hero_title should match published.hero_title
        assert cur2["draft"]["landing"].get("hero_title") == cur2["published"]["landing"].get("hero_title")


# ------------------- Image Upload -------------------
class TestSiteImageUpload:
    def test_upload_and_fetch(self, super_session):
        # Minimal 1x1 PNG (no real header verification on backend beyond content_type)
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0"
            b"\x00\x00\x00\x03\x00\x01]\xc9\x9c\xb6\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        files = {"file": ("test.png", io.BytesIO(png_bytes), "image/png")}
        r = super_session.post(f"{API}/site-settings/upload-image", files=files, timeout=20)
        assert r.status_code == 200, r.text
        url = r.json()["url"]
        assert url.startswith("/api/uploads/site/")

        # Fetchable
        full = f"{BASE_URL}{url}"
        rf = requests.get(full, timeout=15)
        assert rf.status_code == 200
        assert len(rf.content) > 0

    def test_upload_rejects_non_image(self, super_session):
        files = {"file": ("hack.txt", io.BytesIO(b"not an image"), "text/plain")}
        r = super_session.post(f"{API}/site-settings/upload-image", files=files, timeout=15)
        assert r.status_code == 400

    def test_upload_requires_super_admin(self, exec_session):
        files = {"file": ("test.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")}
        r = exec_session.post(f"{API}/site-settings/upload-image", files=files, timeout=15)
        assert r.status_code == 403


# ------------------- Web Push VAPID -------------------
class TestPushVapid:
    def test_vapid_public_key(self):
        r = requests.get(f"{API}/push/vapid-public-key", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "public_key" in data
        assert isinstance(data["public_key"], str)
        assert len(data["public_key"]) > 0, "VAPID public_key is empty"


class TestPushSubscription:
    def test_subscribe_requires_auth(self):
        r = requests.post(
            f"{API}/push/subscribe",
            json={"subscription": {"endpoint": "https://example.com/x", "keys": {"p256dh": "k", "auth": "a"}}},
            timeout=15,
        )
        assert r.status_code == 401

    def test_subscribe_and_unsubscribe(self, admin_session):
        endpoint = "https://example.com/test-push-endpoint-TEST"
        payload = {"subscription": {"endpoint": endpoint, "keys": {"p256dh": "k", "auth": "a"}}}

        r1 = admin_session.post(f"{API}/push/subscribe", json=payload, timeout=15)
        assert r1.status_code == 200
        assert r1.json().get("ok") is True

        # Idempotent (upsert)
        r2 = admin_session.post(f"{API}/push/subscribe", json=payload, timeout=15)
        assert r2.status_code == 200

        r3 = admin_session.post(f"{API}/push/unsubscribe", json=payload, timeout=15)
        assert r3.status_code == 200

    def test_subscribe_invalid_payload(self, admin_session):
        r = admin_session.post(f"{API}/push/subscribe", json={"subscription": {}}, timeout=15)
        assert r.status_code == 400


# ------------------- Regression: login + quotation list still works -------------------
class TestRegression:
    def test_admin_dashboard_endpoint(self, admin_session):
        r = admin_session.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200
        assert r.json().get("email") == ADMIN["email"]

    def test_quotation_list(self, admin_session):
        r = admin_session.get(f"{API}/quotations", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
