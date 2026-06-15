"""Iteration 14 - Self-service signup funnel.

Covers:
- Public POST /api/signup (201, validation, duplicate, dup pending)
- Master endpoints: list pending, count, approve, reject
- Approval creates company + admin user with correct plan defaults
- After approval the new admin can login with chosen password
- Slug auto-suffixing (-2) when duplicated
- Re-processing a decided request returns 400

Cleanup: deletes the tenant_requests / users / companies it created.
"""
import os
import time
import uuid
import pytest
import requests
from pathlib import Path

# Load frontend .env to obtain REACT_APP_BACKEND_URL
_env = Path("/app/frontend/.env")
if _env.exists():
    for line in _env.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL"):
            os.environ.setdefault("REACT_APP_BACKEND_URL", line.split("=", 1)[1].strip())
# Load backend .env for MONGO_URL/DB_NAME
_benv = Path("/app/backend/.env")
if _benv.exists():
    for line in _benv.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

MASTER_EMAIL = "owner@routiq.mx"
MASTER_PASSWORD = "Routiq2026!"
EXISTING_ADMIN_EMAIL = "admin@aventurate.mx"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def master_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD})
    assert r.status_code == 200, f"master login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def public_session():
    """A session that injects a unique X-Forwarded-For per /signup call so the
    iter15 rate-limit (5/IP/hour) doesn't make this suite flaky."""
    import random
    s = requests.Session()
    _orig = s.request

    def _req(method, url, **kw):
        if str(url).endswith("/signup"):
            headers = dict(kw.get("headers") or {})
            headers["X-Forwarded-For"] = f"198.51.{random.randint(1, 254)}.{random.randint(1, 254)}"
            kw["headers"] = headers
        return _orig(method, url, **kw)

    s.request = _req
    return s


@pytest.fixture(scope="module")
def created():
    """Track created ids for teardown."""
    state = {"request_ids": [], "company_ids": [], "user_emails": []}
    yield state
    # Teardown: delete via direct mongo so we don't rely on admin DELETE endpoints
    try:
        from pymongo import MongoClient
        cli = MongoClient(os.environ["MONGO_URL"])
        db = cli[os.environ.get("DB_NAME", "test_database")]
        if state["request_ids"]:
            db.tenant_requests.delete_many({"id": {"$in": state["request_ids"]}})
        if state["company_ids"]:
            db.companies.delete_many({"id": {"$in": state["company_ids"]}})
        if state["user_emails"]:
            db.users.delete_many({"email": {"$in": state["user_emails"]}})
    except Exception as e:  # noqa
        print(f"cleanup failed: {e}")


def _unique_suffix():
    return f"{int(time.time())}{uuid.uuid4().hex[:4]}"


# ---------- 1. Public POST /signup ----------
class TestPublicSignup:
    def test_signup_success_201(self, public_session, created):
        suf = _unique_suffix()
        email = f"test_signup_{suf}@example.com"
        payload = {
            "company_name": f"TEST Empresa {suf}",
            "admin_name": "Admin Prueba",
            "admin_email": email,
            "admin_phone": "+52 33 1111 2222",
            "plan": "pro",
            "admin_password": "TestPass123!",
        }
        r = public_session.post(f"{API}/signup", json=payload)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["ok"] is True
        assert "id" in data and isinstance(data["id"], str)
        created["request_ids"].append(data["id"])

    def test_signup_duplicate_existing_user(self, public_session):
        payload = {
            "company_name": "TEST Dup",
            "admin_name": "Otra Persona",
            "admin_email": EXISTING_ADMIN_EMAIL,
            "admin_phone": "",
            "plan": "starter",
            "admin_password": "TestPass123!",
        }
        r = public_session.post(f"{API}/signup", json=payload)
        assert r.status_code == 400, r.text
        detail = r.json().get("detail", "")
        assert "Ya existe una cuenta" in detail

    def test_signup_short_password_422(self, public_session):
        suf = _unique_suffix()
        payload = {
            "company_name": f"TEST shortpw {suf}",
            "admin_name": "ABC",
            "admin_email": f"shortpw_{suf}@example.com",
            "admin_phone": "",
            "plan": "starter",
            "admin_password": "abc",
        }
        r = public_session.post(f"{API}/signup", json=payload)
        assert r.status_code == 422

    def test_signup_short_name_422(self, public_session):
        suf = _unique_suffix()
        payload = {
            "company_name": "X",
            "admin_name": "Y",
            "admin_email": f"shortname_{suf}@example.com",
            "admin_phone": "",
            "plan": "pro",
            "admin_password": "TestPass123!",
        }
        r = public_session.post(f"{API}/signup", json=payload)
        assert r.status_code == 422

    def test_signup_duplicate_pending(self, public_session, created):
        suf = _unique_suffix()
        email = f"pending_dup_{suf}@example.com"
        payload = {
            "company_name": f"TEST Pending {suf}",
            "admin_name": "Pendiente",
            "admin_email": email,
            "admin_phone": "",
            "plan": "pro",
            "admin_password": "TestPass123!",
        }
        r1 = public_session.post(f"{API}/signup", json=payload)
        assert r1.status_code == 201, r1.text
        created["request_ids"].append(r1.json()["id"])
        r2 = public_session.post(f"{API}/signup", json=payload)
        assert r2.status_code == 400
        assert "pendiente" in r2.json().get("detail", "").lower()


# ---------- 2. Master endpoints ----------
class TestMasterListAndCount:
    def test_list_requires_super_admin(self, public_session):
        r = public_session.get(f"{API}/tenant-requests?status=pending")
        assert r.status_code in (401, 403)

    def test_list_and_count(self, master_session):
        r = master_session.get(f"{API}/tenant-requests", params={"status": "pending"})
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        rc = master_session.get(f"{API}/tenant-requests/count")
        assert rc.status_code == 200
        assert isinstance(rc.json().get("pending"), int)


# ---------- 3. Approve flow ----------
class TestApproveFlow:
    def test_approve_creates_company_user_and_login_works(self, public_session, master_session, created):
        suf = _unique_suffix()
        email = f"approve_{suf}@example.com"
        password = "ApprovedPass1!"
        company_name = f"TEST Approve {suf}"
        payload = {
            "company_name": company_name,
            "admin_name": "Aprobador Prueba",
            "admin_email": email,
            "admin_phone": "+52 33 9999 8888",
            "plan": "starter",
            "admin_password": password,
        }
        r = public_session.post(f"{API}/signup", json=payload)
        assert r.status_code == 201
        req_id = r.json()["id"]
        created["request_ids"].append(req_id)
        created["user_emails"].append(email)

        custom_slug = f"test-approve-{suf}"
        ra = master_session.post(f"{API}/tenant-requests/{req_id}/approve", json={"slug": custom_slug})
        assert ra.status_code == 200, ra.text
        body = ra.json()
        assert body["ok"] is True
        assert body["company"]["plan"] == "starter"
        assert body["company"]["slug"] == custom_slug
        assert body["credentials"]["email"] == email
        assert "login_url" in body["credentials"]
        assert "email_sent" in body
        created["company_ids"].append(body["company"]["id"])

        # Login with chosen password
        ls = requests.Session()
        rl = ls.post(f"{API}/auth/login", json={"email": email, "password": password})
        assert rl.status_code == 200, rl.text
        me = ls.get(f"{API}/auth/me")
        assert me.status_code == 200
        u = me.json()
        assert u["email"] == email
        assert u["role"] == "company_admin"
        assert u["tenant_id"] == body["company"]["id"]

        # Verify plan defaults applied: starter -> exec_limit=3, ai_enabled False, stripe_allowed False
        rc = master_session.get(f"{API}/companies")
        assert rc.status_code == 200, rc.text
        comp = next((c for c in rc.json() if c["id"] == body["company"]["id"]), None)
        assert comp is not None, "approved company not found in /api/companies list"
        assert comp["plan"] == "starter"
        assert comp["exec_limit"] == 3
        assert comp["ai_enabled"] is False
        assert comp["stripe_allowed"] is False
        assert comp["transfer_allowed"] is True

    def test_approve_slug_dedupes_with_suffix(self, public_session, master_session, created):
        suf = _unique_suffix()
        # First signup + approve with explicit slug
        slug_base = f"test-dup-slug-{suf}"
        e1 = f"slugdup1_{suf}@example.com"
        e2 = f"slugdup2_{suf}@example.com"
        for em in (e1, e2):
            r = public_session.post(f"{API}/signup", json={
                "company_name": f"TEST Slug {suf} {em}",
                "admin_name": "Slug Dup",
                "admin_email": em,
                "admin_phone": "",
                "plan": "pro",
                "admin_password": "SlugPass123!",
            })
            assert r.status_code == 201
            created["request_ids"].append(r.json()["id"])
            created["user_emails"].append(em)

        # find both ids in pending list (most recent first)
        rl = master_session.get(f"{API}/tenant-requests", params={"status": "pending"})
        ids_for_emails = {row["admin_email"]: row["id"] for row in rl.json()}
        id1, id2 = ids_for_emails[e1], ids_for_emails[e2]

        ra1 = master_session.post(f"{API}/tenant-requests/{id1}/approve", json={"slug": slug_base})
        assert ra1.status_code == 200
        comp1 = ra1.json()["company"]
        created["company_ids"].append(comp1["id"])
        assert comp1["slug"] == slug_base

        ra2 = master_session.post(f"{API}/tenant-requests/{id2}/approve", json={"slug": slug_base})
        assert ra2.status_code == 200
        comp2 = ra2.json()["company"]
        created["company_ids"].append(comp2["id"])
        assert comp2["slug"] == f"{slug_base}-2"

    def test_approve_already_processed_returns_400(self, master_session, created):
        # reuse first approved request id from prior test if available
        # easier: get any approved request and try to approve again
        rl = master_session.get(f"{API}/tenant-requests")
        approved = [row for row in rl.json() if row.get("status") == "approved"]
        if not approved:
            pytest.skip("no approved request to retry")
        rid = approved[0]["id"]
        r = master_session.post(f"{API}/tenant-requests/{rid}/approve", json={})
        assert r.status_code == 400


# ---------- 4. Reject flow ----------
class TestRejectFlow:
    def test_reject_with_reason(self, public_session, master_session, created):
        suf = _unique_suffix()
        email = f"reject_{suf}@example.com"
        r = public_session.post(f"{API}/signup", json={
            "company_name": f"TEST Reject {suf}",
            "admin_name": "Rechazo Prueba",
            "admin_email": email,
            "admin_phone": "",
            "plan": "pro",
            "admin_password": "RejectPass1!",
        })
        assert r.status_code == 201
        rid = r.json()["id"]
        created["request_ids"].append(rid)

        rr = master_session.post(f"{API}/tenant-requests/{rid}/reject", json={"reason": "Datos insuficientes"})
        assert rr.status_code == 200
        assert rr.json()["ok"] is True

        # Re-reject -> 400
        rr2 = master_session.post(f"{API}/tenant-requests/{rid}/reject", json={"reason": ""})
        assert rr2.status_code == 400

        # No longer in pending list
        lp = master_session.get(f"{API}/tenant-requests", params={"status": "pending"})
        ids = {row["id"] for row in lp.json()}
        assert rid not in ids
