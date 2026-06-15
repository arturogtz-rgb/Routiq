"""Iteration 15 - Signup funnel hardening.

Covers:
- Rate-limit per IP (X-Forwarded-For): 5 ok, 6th -> 429. Different IP still ok.
- Honeypot: 'website' non-empty -> {ok:true,id:'ok'} but NO insert in tenant_requests.
- Captcha bypass (TURNSTILE_SECRET_KEY empty): signup works without token.
- History via GET /api/tenant-requests with ?status=approved / rejected / no filter.

Cleanup: Mongo direct delete of any TEST_ data created and signup_attempts touched
by this run.
"""
import os
import random
import time
import uuid
from pathlib import Path

import pytest
import requests

# Load envs (frontend BASE URL + backend MONGO_URL/DB_NAME)
_env = Path("/app/frontend/.env")
if _env.exists():
    for line in _env.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL"):
            os.environ.setdefault("REACT_APP_BACKEND_URL", line.split("=", 1)[1].strip())
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


def _suf():
    return f"{int(time.time())}{uuid.uuid4().hex[:6]}"


def _mongo():
    from pymongo import MongoClient
    cli = MongoClient(os.environ["MONGO_URL"])
    return cli[os.environ.get("DB_NAME", "routiq")]


@pytest.fixture(scope="module")
def master_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def created():
    state = {"request_ids": [], "company_ids": [], "user_emails": [], "ips": []}
    yield state
    try:
        db = _mongo()
        if state["request_ids"]:
            db.tenant_requests.delete_many({"id": {"$in": state["request_ids"]}})
        if state["company_ids"]:
            db.companies.delete_many({"id": {"$in": state["company_ids"]}})
        if state["user_emails"]:
            db.users.delete_many({"email": {"$in": state["user_emails"]}})
        if state["ips"]:
            db.signup_attempts.delete_many({"ip": {"$in": state["ips"]}})
    except Exception as e:
        print(f"cleanup failed: {e}")


# ---------------- 1. Honeypot ----------------
class TestHoneypot:
    def test_honeypot_returns_ok_but_does_not_insert(self, created):
        suf = _suf()
        email = f"hp_{suf}@example.com"
        ip = f"10.99.{random.randint(30,229)}.{random.randint(5,244)}"
        created["ips"].append(ip)
        payload = {
            "company_name": f"TEST HP {suf}",
            "admin_name": "Honeypot Bot",
            "admin_email": email,
            "admin_phone": "",
            "plan": "pro",
            "admin_password": "BotPass1234",
            "website": "https://spam.example.com",
        }
        r = requests.post(f"{API}/signup", json=payload, headers={"X-Forwarded-For": ip})
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body == {"ok": True, "id": "ok"}, body

        db = _mongo()
        assert db.tenant_requests.find_one({"admin_email": email}) is None
        # Honeypot must NOT consume a rate-limit slot
        assert db.signup_attempts.count_documents({"ip": ip}) == 0

    def test_empty_website_works_normally(self, created):
        suf = _suf()
        email = f"normal_{suf}@example.com"
        ip = f"10.98.{random.randint(30,229)}.{random.randint(5,244)}"
        created["ips"].append(ip)
        r = requests.post(f"{API}/signup", json={
            "company_name": f"TEST Normal {suf}",
            "admin_name": "Normal Persona",
            "admin_email": email,
            "admin_phone": "",
            "plan": "pro",
            "admin_password": "NormalPass1!",
            "website": "",
        }, headers={"X-Forwarded-For": ip})
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
        assert rid != "ok"
        created["request_ids"].append(rid)


# ---------------- 2. Captcha bypass ----------------
class TestCaptchaBypass:
    def test_signup_works_without_turnstile_token(self, created):
        suf = _suf()
        email = f"nocap_{suf}@example.com"
        ip = f"10.97.{random.randint(30,229)}.{random.randint(5,244)}"
        created["ips"].append(ip)
        # No turnstile_token field at all
        r = requests.post(f"{API}/signup", json={
            "company_name": f"TEST NoCap {suf}",
            "admin_name": "Sin Captcha",
            "admin_email": email,
            "admin_phone": "",
            "plan": "starter",
            "admin_password": "NoCapPass1!",
        }, headers={"X-Forwarded-For": ip})
        assert r.status_code == 201, r.text
        created["request_ids"].append(r.json()["id"])


# ---------------- 3. Rate-limit ----------------
class TestRateLimit:
    def test_5_ok_6th_429_other_ip_ok(self, created):
        suf = _suf()
        ip_a = f"10.96.{random.randint(30,229)}.{random.randint(5,244)}"
        ip_b = f"10.95.{random.randint(30,229)}.{random.randint(5,244)}"
        created["ips"].extend([ip_a, ip_b])

        # 5 valid requests with same IP -> 201 each
        for i in range(5):
            email = f"rl_{suf}_{i}@example.com"
            r = requests.post(f"{API}/signup", json={
                "company_name": f"TEST RL {suf} {i}",
                "admin_name": f"User {i}",
                "admin_email": email,
                "admin_phone": "",
                "plan": "pro",
                "admin_password": "RatePass1234",
            }, headers={"X-Forwarded-For": ip_a})
            assert r.status_code == 201, f"req {i}: {r.status_code} {r.text}"
            created["request_ids"].append(r.json()["id"])

        # 6th request from same IP -> 429
        r6 = requests.post(f"{API}/signup", json={
            "company_name": f"TEST RL {suf} 6",
            "admin_name": "User 6",
            "admin_email": f"rl_{suf}_6@example.com",
            "admin_phone": "",
            "plan": "pro",
            "admin_password": "RatePass1234",
        }, headers={"X-Forwarded-For": ip_a})
        assert r6.status_code == 429, r6.text
        assert "Demasiadas" in r6.json().get("detail", "")

        # A different IP still works
        r_other = requests.post(f"{API}/signup", json={
            "company_name": f"TEST RL OTHER {suf}",
            "admin_name": "Other IP",
            "admin_email": f"rl_other_{suf}@example.com",
            "admin_phone": "",
            "plan": "pro",
            "admin_password": "RatePass1234",
        }, headers={"X-Forwarded-For": ip_b})
        assert r_other.status_code == 201, r_other.text
        created["request_ids"].append(r_other.json()["id"])


# ---------------- 4. History endpoint ----------------
class TestHistory:
    def test_approve_reject_and_history_filters(self, master_session, created):
        suf = _suf()
        # Use a fresh IP to avoid hitting the rate-limit from earlier tests
        ip = f"10.94.{random.randint(30,229)}.{random.randint(5,244)}"
        created["ips"].append(ip)

        # Create 2 fresh requests
        e_app = f"hist_app_{suf}@example.com"
        e_rej = f"hist_rej_{suf}@example.com"
        created["user_emails"].extend([e_app, e_rej])
        ids = {}
        for label, em in (("approve", e_app), ("reject", e_rej)):
            r = requests.post(f"{API}/signup", json={
                "company_name": f"TEST Hist {label} {suf}",
                "admin_name": f"Hist {label}",
                "admin_email": em,
                "admin_phone": "",
                "plan": "pro",
                "admin_password": "HistPass1234",
            }, headers={"X-Forwarded-For": ip})
            assert r.status_code == 201, r.text
            ids[label] = r.json()["id"]
            created["request_ids"].append(ids[label])

        # Approve one
        ra = master_session.post(
            f"{API}/tenant-requests/{ids['approve']}/approve",
            json={"slug": f"test-hist-{suf}"},
        )
        assert ra.status_code == 200, ra.text
        created["company_ids"].append(ra.json()["company"]["id"])

        # Reject other
        rj = master_session.post(
            f"{API}/tenant-requests/{ids['reject']}/reject",
            json={"reason": "Motivo de prueba iter15"},
        )
        assert rj.status_code == 200, rj.text

        # GET all
        all_resp = master_session.get(f"{API}/tenant-requests")
        assert all_resp.status_code == 200
        all_rows = {row["id"]: row for row in all_resp.json()}
        assert ids["approve"] in all_rows and all_rows[ids["approve"]]["status"] == "approved"
        assert all_rows[ids["approve"]].get("decided_at"), "approved request missing decided_at"
        assert ids["reject"] in all_rows and all_rows[ids["reject"]]["status"] == "rejected"
        assert all_rows[ids["reject"]].get("reason") == "Motivo de prueba iter15"
        assert all_rows[ids["reject"]].get("decided_at"), "rejected request missing decided_at"

        # Approved filter
        appr_resp = master_session.get(f"{API}/tenant-requests", params={"status": "approved"})
        assert appr_resp.status_code == 200
        appr_ids = {row["id"] for row in appr_resp.json()}
        assert ids["approve"] in appr_ids
        assert ids["reject"] not in appr_ids
        assert all(r["status"] == "approved" for r in appr_resp.json())

        # Rejected filter
        rej_resp = master_session.get(f"{API}/tenant-requests", params={"status": "rejected"})
        assert rej_resp.status_code == 200
        rej_ids = {row["id"] for row in rej_resp.json()}
        assert ids["reject"] in rej_ids
        assert ids["approve"] not in rej_ids
        assert all(r["status"] == "rejected" for r in rej_resp.json())

        # Password hash should be scrubbed from approved + rejected docs
        db = _mongo()
        for rid in (ids["approve"], ids["reject"]):
            doc = db.tenant_requests.find_one({"id": rid})
            assert doc is not None
            assert "password_hash" not in doc, f"password_hash still present in {doc}"
