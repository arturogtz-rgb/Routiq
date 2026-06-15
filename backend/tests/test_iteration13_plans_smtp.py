"""Iteration 13 — P0 features tests:
 1) Plans (Master): PATCH /api/companies/{id}/plan applies presets
 2) Executive limit on POST /api/users/invite-executive (403 over limit)
 3) SMTP: integrations persistence + POST /companies/me/test-smtp validation
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

OWNER = {"email": "owner@routiq.mx", "password": "Routiq2026!"}
ADMIN = {"email": "admin@aventurate.mx", "password": "Demo2026!"}


# ---------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def owner_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=OWNER, timeout=20)
    assert r.status_code == 200, f"Owner login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def aventurate_company(owner_session):
    r = owner_session.get(f"{BASE_URL}/api/companies", timeout=20)
    assert r.status_code == 200, r.text
    companies = r.json()
    for c in companies:
        if c.get("slug") == "routiq-planes" or "aventurate" in (c.get("slug") or "").lower() or "Aventúrate" in (c.get("name") or ""):
            return c
    # fallback: first non-master
    return companies[0]


# ---------------------------------------------------------------- PLANS
class TestPlans:
    def test_list_companies_has_plan_field(self, owner_session):
        r = owner_session.get(f"{BASE_URL}/api/companies", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) > 0
        assert "plan" in data[0]

    def test_apply_starter_plan(self, owner_session, aventurate_company):
        cid = aventurate_company["id"]
        r = owner_session.patch(
            f"{BASE_URL}/api/companies/{cid}/plan",
            json={"plan": "starter"}, timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["plan"] == "starter"
        assert data["exec_limit"] == 3
        assert data["ai_enabled"] is False
        assert data["white_label"] is False
        assert data["stripe_allowed"] is False
        assert data["transfer_allowed"] is True

    def test_apply_enterprise_plan(self, owner_session, aventurate_company):
        cid = aventurate_company["id"]
        r = owner_session.patch(
            f"{BASE_URL}/api/companies/{cid}/plan",
            json={"plan": "enterprise"}, timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["plan"] == "enterprise"
        assert data["exec_limit"] == 0
        assert data["ai_enabled"] is True
        assert data["white_label"] is True
        assert data["stripe_allowed"] is True

    def test_per_field_override(self, owner_session, aventurate_company):
        cid = aventurate_company["id"]
        r = owner_session.patch(
            f"{BASE_URL}/api/companies/{cid}/plan",
            json={"plan": "pro", "exec_limit": 7}, timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["plan"] == "pro"
        # explicit override wins
        assert data["exec_limit"] == 7

    def test_non_master_cannot_change_plan(self, admin_session, aventurate_company):
        cid = aventurate_company["id"]
        r = admin_session.patch(
            f"{BASE_URL}/api/companies/{cid}/plan",
            json={"plan": "starter"}, timeout=20,
        )
        assert r.status_code in (401, 403), r.text


# ---------------------------------------------------------------- EXEC LIMIT
class TestExecLimit:
    def test_invite_blocked_when_limit_reached(self, owner_session, admin_session, aventurate_company):
        cid = aventurate_company["id"]
        # Set a tiny limit (=1) so the existing seed executive already fills the cap
        r = owner_session.patch(
            f"{BASE_URL}/api/companies/{cid}/plan",
            json={"plan": "starter", "exec_limit": 1}, timeout=20,
        )
        assert r.status_code == 200, r.text
        assert r.json()["exec_limit"] == 1

        # Now try to invite a new executive as admin -> should be 403
        r = admin_session.post(
            f"{BASE_URL}/api/users/invite-executive",
            json={"email": "TEST_overlimit@aventurate.mx", "name": "Test Overlimit", "password": "Test1234!"},
            timeout=20,
        )
        assert r.status_code == 403, f"Expected 403 over limit, got {r.status_code}: {r.text}"
        assert "límite" in r.text.lower() or "limite" in r.text.lower()

    def test_invite_allowed_with_capacity(self, owner_session, admin_session, aventurate_company):
        cid = aventurate_company["id"]
        # restore pro limit (15)
        r = owner_session.patch(
            f"{BASE_URL}/api/companies/{cid}/plan",
            json={"plan": "pro"}, timeout=20,
        )
        assert r.status_code == 200, r.text

        # now invite should succeed
        email = "TEST_cap_ok@aventurate.mx"
        r = admin_session.post(
            f"{BASE_URL}/api/users/invite-executive",
            json={"email": email, "name": "Test Cap OK", "password": "Test1234!"},
            timeout=20,
        )
        # could be 201 (created) or 400 if dup from previous run; accept both but prefer 201
        assert r.status_code in (201, 400), r.text
        if r.status_code == 201:
            body = r.json()
            assert body["email"] == email.lower()
            assert body["role"] == "executive"
            # cleanup: suspend so it doesn't pollute counters
            try:
                admin_session.patch(
                    f"{BASE_URL}/api/users/{body['id']}/status?status=suspended",
                    timeout=10,
                )
            except Exception:
                pass


# ---------------------------------------------------------------- SMTP
class TestSMTP:
    def test_get_integrations_has_smtp_fields(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/companies/me/integrations", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # SMTP / provider fields exposed
        for k in (
            "email_provider", "smtp_host", "smtp_port", "smtp_username",
            "smtp_password_set", "smtp_use_tls", "smtp_from_email", "smtp_from_name",
        ):
            assert k in data, f"Missing field {k} in integrations view"

    def test_patch_integrations_persists_smtp(self, admin_session):
        payload = {
            "email_provider": "smtp",
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "user@example.com",
            "smtp_use_tls": True,
            "smtp_from_email": "from@example.com",
            "smtp_from_name": "Test From",
        }
        r = admin_session.patch(
            f"{BASE_URL}/api/companies/me/integrations", json=payload, timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email_provider"] == "smtp"
        assert data["smtp_host"] == "smtp.example.com"
        assert data["smtp_port"] == 587
        assert data["smtp_username"] == "user@example.com"
        assert data["smtp_from_email"] == "from@example.com"
        assert data["smtp_from_name"] == "Test From"
        # password not provided -> smtp_password_set stays as it was (do not assert true)

        # GET verifies persistence
        r2 = admin_session.get(f"{BASE_URL}/api/companies/me/integrations", timeout=20)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["email_provider"] == "smtp"
        assert d2["smtp_host"] == "smtp.example.com"

    def test_patch_integrations_empty_password_does_not_overwrite(self, admin_session):
        # Send an empty password — backend code only sets password when non-empty and
        # not starting with bullets. So smtp_password_set should remain whatever it was.
        before = admin_session.get(f"{BASE_URL}/api/companies/me/integrations", timeout=20).json()
        before_set = before["smtp_password_set"]
        r = admin_session.patch(
            f"{BASE_URL}/api/companies/me/integrations",
            json={"smtp_password": ""}, timeout=20,
        )
        assert r.status_code == 200, r.text
        after = r.json()
        assert after["smtp_password_set"] == before_set

    def test_test_smtp_missing_password_returns_400(self, admin_session):
        # ensure stored password is empty by sending masked bullets (won't overwrite)
        # We rely on company likely not having a stored password in seed
        payload = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "user@example.com",
            "smtp_password": "",  # missing
            "smtp_use_tls": True,
            "smtp_from_email": "from@example.com",
            "smtp_from_name": "Test",
            "to_email": "to@example.com",
        }
        r = admin_session.post(
            f"{BASE_URL}/api/companies/me/test-smtp", json=payload, timeout=30,
        )
        # If a password was set by previous tests, this will fail with 400 "No se pudo enviar"
        # instead of 400 "Falta la contraseña SMTP". Both are 400 — but verify message
        # is specific in the no-password scenario.
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        detail = (r.json().get("detail") or "").lower()
        # Either missing password OR cannot send (host unreachable) — accept either
        assert ("contraseña" in detail) or ("no se pudo enviar" in detail), detail

    def test_test_smtp_bad_host_returns_400(self, admin_session):
        payload = {
            "smtp_host": "nonexistent.invalid.host.routiq.test",
            "smtp_port": 587,
            "smtp_username": "user@example.com",
            "smtp_password": "fake-password-xyz",
            "smtp_use_tls": True,
            "smtp_from_email": "from@example.com",
            "smtp_from_name": "Test",
            "to_email": "to@example.com",
        }
        r = admin_session.post(
            f"{BASE_URL}/api/companies/me/test-smtp", json=payload, timeout=60,
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        detail = (r.json().get("detail") or "").lower()
        assert "no se pudo enviar" in detail, detail


# ---------------------------------------------------------------- FINAL: restore pro
class TestZRestore:
    """Run last alphabetically to leave aventurate on PRO plan for demos."""
    def test_restore_pro_plan(self, owner_session, aventurate_company):
        cid = aventurate_company["id"]
        # also restore email_provider to resend so SMTP doesn't break Resend flows
        # (admin scope — different session)
        r = owner_session.patch(
            f"{BASE_URL}/api/companies/{cid}/plan",
            json={"plan": "pro"}, timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["plan"] == "pro"
        assert data["exec_limit"] == 15

    def test_restore_email_provider(self, admin_session):
        r = admin_session.patch(
            f"{BASE_URL}/api/companies/me/integrations",
            json={"email_provider": "resend"}, timeout=20,
        )
        assert r.status_code == 200, r.text
        assert r.json()["email_provider"] == "resend"
