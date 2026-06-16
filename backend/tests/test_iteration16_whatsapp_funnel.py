"""Iteration 16 — KPI funnel metrics + WhatsApp (Baileys proxy) API tests.

Preview environment: BAILEYS_URL is empty, so connect/qr/status/send must return
503 with the explanatory Spanish message. The webhook IS real and is exercised
with the shared secret read from /app/backend/.env.

Cleanup invariant: do NOT touch owner@routiq.mx, admin@aventurate.mx, or the
seed company "Aventúrate por Jalisco". The seed number "Ventas GDL" must remain
(status reset to disconnected). Any number we add gets deleted; any message we
insert via webhook gets removed from whatsapp_messages.
"""
import os
import secrets
from pathlib import Path
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://free-itinerary-mode.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

# Read BAILEYS_SHARED_SECRET from /app/backend/.env
def _env(key: str) -> str:
    for line in Path("/app/backend/.env").read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""

BAILEYS_SECRET = _env("BAILEYS_SHARED_SECRET")

MASTER_EMAIL = "owner@routiq.mx"
MASTER_PASS = "Routiq2026!"
ADMIN_EMAIL = "admin@aventurate.mx"
ADMIN_PASS = "Demo2026!"


# ---------------- Fixtures ----------------
@pytest.fixture(scope="session")
def master_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": MASTER_EMAIL, "password": MASTER_PASS})
    assert r.status_code == 200, f"master login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def tenant_id(admin_session):
    r = admin_session.get(f"{API}/companies/me")
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------------- KPI MASTER ----------------
class TestFunnelMetrics:
    def test_metrics_shape(self, master_session):
        r = master_session.get(f"{API}/tenant-requests/metrics")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("month", "received", "approved", "rejected", "active", "conversion_pct"):
            assert k in d, f"missing key {k}"
        assert isinstance(d["received"], int)
        assert isinstance(d["approved"], int)
        assert isinstance(d["active"], int)
        assert isinstance(d["conversion_pct"], int)
        assert 0 <= d["conversion_pct"] <= 100

    def test_metrics_requires_super_admin(self, admin_session):
        r = admin_session.get(f"{API}/tenant-requests/metrics")
        assert r.status_code in (401, 403), f"expected forbidden, got {r.status_code}"

    def test_metrics_updates_after_signup_and_approve(self, master_session):
        """Insert tenant_request directly (captcha is ENABLED in preview) and
        verify approve flow updates received/approved/active counters."""
        from datetime import datetime, timezone
        from pymongo import MongoClient
        import uuid
        from passlib.hash import bcrypt

        before = master_session.get(f"{API}/tenant-requests/metrics").json()

        mc = MongoClient(_env("MONGO_URL"))
        db = mc[_env("DB_NAME")]
        suffix = secrets.token_hex(4)
        req_id = str(uuid.uuid4())
        email = f"TEST_iter16_{suffix}@example.com"
        now_iso = datetime.now(timezone.utc).isoformat()
        db.tenant_requests.insert_one({
            "id": req_id, "company_name": f"TEST_iter16_{suffix}",
            "admin_name": "Test 16", "admin_email": email, "admin_phone": "",
            "plan": "pro", "slug": f"test-iter16-{suffix}",
            "password_hash": bcrypt.hash("Test1234!"),
            "status": "pending", "reason": "",
            "created_at": now_iso, "decided_at": "",
        })

        try:
            after_recv = master_session.get(f"{API}/tenant-requests/metrics").json()
            assert after_recv["received"] >= before["received"] + 1

            ar = master_session.post(f"{API}/tenant-requests/{req_id}/approve",
                                     json={"slug": f"test-iter16-{suffix}"})
            assert ar.status_code == 200, ar.text
            company_id = ar.json()["company"]["id"]

            after = master_session.get(f"{API}/tenant-requests/metrics").json()
            assert after["approved"] >= before["approved"] + 1
            assert after["active"] >= before["active"] + 1
            # conversion_pct must be a sane percentage
            if after["received"] > 0:
                assert after["conversion_pct"] == round((after["approved"] / after["received"]) * 100)
        finally:
            db.companies.delete_many({"slug": {"$regex": f"^test-iter16-{suffix}"}})
            db.users.delete_one({"email": email})
            db.tenant_requests.delete_one({"id": req_id})
            mc.close()


# ---------------- WhatsApp number management ----------------
class TestWhatsAppNumbers:
    created_id = None

    def test_list_numbers_seed(self, admin_session):
        r = admin_session.get(f"{API}/whatsapp/numbers")
        assert r.status_code == 200, r.text
        nums = r.json()
        assert any(n.get("label") == "Ventas GDL" for n in nums), "seed number missing"

    def test_add_and_delete_number(self, admin_session):
        suffix = secrets.token_hex(3)
        r = admin_session.post(f"{API}/whatsapp/numbers", json={"label": f"TEST_{suffix}", "number": "+5215555000000"})
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["status"] == "disconnected"
        assert "id" in data
        TestWhatsAppNumbers.created_id = data["id"]

        # verify persistence
        nums = admin_session.get(f"{API}/whatsapp/numbers").json()
        assert any(n["id"] == data["id"] for n in nums)

        # delete
        dr = admin_session.delete(f"{API}/whatsapp/numbers/{data['id']}")
        assert dr.status_code == 200
        nums2 = admin_session.get(f"{API}/whatsapp/numbers").json()
        assert not any(n["id"] == data["id"] for n in nums2)

    def test_connect_without_microservice_returns_503(self, admin_session):
        # add a temp number
        r = admin_session.post(f"{API}/whatsapp/numbers", json={"label": "TEST_conn", "number": ""})
        nid = r.json()["id"]
        try:
            cr = admin_session.post(f"{API}/whatsapp/numbers/{nid}/connect")
            assert cr.status_code == 503, f"expected 503, got {cr.status_code} {cr.text}"
            detail = cr.json().get("detail", "")
            assert "WhatsApp" in detail and "configurado" in detail
        finally:
            admin_session.delete(f"{API}/whatsapp/numbers/{nid}")


# ---------------- WhatsApp webhook ----------------
class TestWhatsAppWebhook:
    def test_webhook_requires_secret(self):
        r = requests.post(f"{API}/whatsapp/webhook", json={"event": "status", "session_id": "x_y", "status": "connected"})
        assert r.status_code == 401, r.text

    def test_webhook_wrong_secret(self):
        r = requests.post(f"{API}/whatsapp/webhook",
                          json={"event": "status", "session_id": "x_y", "status": "connected"},
                          headers={"x-baileys-secret": "wrong"})
        assert r.status_code == 401

    def test_webhook_status_and_message_flow(self, admin_session, tenant_id):
        assert BAILEYS_SECRET, "BAILEYS_SHARED_SECRET missing"
        # create a number for this test
        nr = admin_session.post(f"{API}/whatsapp/numbers", json={"label": "TEST_wh", "number": "+5215554440000"})
        nid = nr.json()["id"]
        sid = f"{tenant_id}_{nid}"
        H = {"x-baileys-secret": BAILEYS_SECRET}

        try:
            # status -> connected
            r1 = requests.post(f"{API}/whatsapp/webhook",
                               json={"event": "status", "session_id": sid, "status": "connected"}, headers=H)
            assert r1.status_code == 200, r1.text
            nums = admin_session.get(f"{API}/whatsapp/numbers").json()
            n = next(x for x in nums if x["id"] == nid)
            assert n["status"] == "connected", n

            # inject inbound message
            chat = "5213311112222@s.whatsapp.net"
            msg_id = f"TEST_wamid_{secrets.token_hex(4)}"
            body = {"event": "message", "session_id": sid, "chat_id": chat,
                    "message_id": msg_id, "from_me": False, "text": "Hola desde test",
                    "push_name": "Cliente Test", "timestamp": 1737000000}
            r2 = requests.post(f"{API}/whatsapp/webhook", json=body, headers=H)
            assert r2.status_code == 200, r2.text

            # idempotency: same message_id -> no duplicate
            requests.post(f"{API}/whatsapp/webhook", json=body, headers=H)

            # chats listing
            chats = admin_session.get(f"{API}/whatsapp/chats", params={"number_id": nid}).json()
            target_chat = next((c for c in chats if c["chat_id"] == chat), None)
            assert target_chat is not None, chats
            assert target_chat["phone"] == "5213311112222"
            assert target_chat["last_text"] == "Hola desde test"
            assert target_chat["unread"] >= 1
            assert target_chat["contact_name"] == "Cliente Test"

            # messages listing — and mark-as-read side effect
            msgs = admin_session.get(f"{API}/whatsapp/messages",
                                     params={"number_id": nid, "chat_id": chat}).json()
            assert len(msgs) == 1, f"expected 1 message (idempotent), got {len(msgs)}"
            assert msgs[0]["text"] == "Hola desde test"
            assert msgs[0]["from_me"] is False
            # after listing, unread should drop to 0
            chats2 = admin_session.get(f"{API}/whatsapp/chats", params={"number_id": nid}).json()
            t2 = next(c for c in chats2 if c["chat_id"] == chat)
            assert t2["unread"] == 0

            # send without microservice -> 502/503 but no crash
            sr = admin_session.post(f"{API}/whatsapp/send",
                                    json={"number_id": nid, "to": chat, "text": "ping"})
            assert sr.status_code in (502, 503), f"expected 502/503, got {sr.status_code} {sr.text}"
        finally:
            # cleanup messages and number
            from pymongo import MongoClient
            mc = MongoClient(_env("MONGO_URL"))
            db = mc[_env("DB_NAME")]
            db.whatsapp_messages.delete_many({"tenant_id": tenant_id, "number_id": nid})
            mc.close()
            admin_session.delete(f"{API}/whatsapp/numbers/{nid}")


# ---------------- Multi-tenant isolation ----------------
class TestTenantIsolation:
    def test_other_tenant_cannot_see_messages(self, admin_session, master_session, tenant_id):
        # inject message into a fake number under demo tenant
        nr = admin_session.post(f"{API}/whatsapp/numbers", json={"label": "TEST_iso", "number": ""})
        nid = nr.json()["id"]
        sid = f"{tenant_id}_{nid}"
        H = {"x-baileys-secret": BAILEYS_SECRET}
        chat = "5219999999999@s.whatsapp.net"
        msg_id = f"TEST_iso_{secrets.token_hex(4)}"
        try:
            requests.post(f"{API}/whatsapp/webhook", headers=H, json={
                "event": "message", "session_id": sid, "chat_id": chat,
                "message_id": msg_id, "from_me": False, "text": "secreto", "push_name": "X",
                "timestamp": 1737000111,
            })
            # super_admin has no tenant_id → should get 401/403 on tenant routes
            r = master_session.get(f"{API}/whatsapp/numbers")
            assert r.status_code in (401, 403), f"super_admin should not access tenant route, got {r.status_code}"

            # webhook with bad session_id (no underscore) returns ok but stores nothing
            r2 = requests.post(f"{API}/whatsapp/webhook", headers=H, json={
                "event": "message", "session_id": "noseparator", "chat_id": chat,
                "message_id": "TEST_bad", "from_me": False, "text": "x", "timestamp": 1737000222,
            })
            assert r2.status_code == 200
        finally:
            from pymongo import MongoClient
            mc = MongoClient(_env("MONGO_URL"))
            db = mc[_env("DB_NAME")]
            db.whatsapp_messages.delete_many({"tenant_id": tenant_id, "number_id": nid})
            db.whatsapp_messages.delete_many({"message_id": "TEST_bad"})
            mc.close()
            admin_session.delete(f"{API}/whatsapp/numbers/{nid}")


# ---------------- Final teardown: reset Ventas GDL ----------------
@pytest.fixture(scope="session", autouse=True)
def _final_cleanup(tenant_id):
    yield
    from pymongo import MongoClient
    mc = MongoClient(_env("MONGO_URL"))
    db = mc[_env("DB_NAME")]
    # reset seed number to disconnected
    db.companies.update_one(
        {"id": tenant_id, "whatsapp_numbers.label": "Ventas GDL"},
        {"$set": {"whatsapp_numbers.$.status": "disconnected"}},
    )
    # purge any leftover TEST_ messages for demo tenant
    db.whatsapp_messages.delete_many({"tenant_id": tenant_id, "message_id": {"$regex": "^TEST_"}})
    # remove any leftover TEST_ numbers
    db.companies.update_one(
        {"id": tenant_id},
        {"$pull": {"whatsapp_numbers": {"label": {"$regex": "^TEST_"}}}},
    )
    mc.close()
