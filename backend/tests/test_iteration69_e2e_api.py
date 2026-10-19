"""Iter 69 E2E API checks against public URL with a REAL invalid Stripe key (rk_test_invalid000).
Requires `python it69_e2e_setup.py setup` beforehand (writes /tmp/it69_state.json)."""
import json
import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
S = json.load(open("/tmp/it69_state.json")) if os.path.exists("/tmp/it69_state.json") else None
SID = "cs_test_fake_it69"

pytestmark = pytest.mark.skipif(S is None, reason="run it69_e2e_setup.py setup first")


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": "admin@aventurate.mx", "password": "Demo2026!"})
    assert r.status_code == 200
    return s


@pytest.fixture(scope="module")
def owner():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": "owner@routiq.mx", "password": "Routiq2026!"})
    return s if r.status_code == 200 else None


# Payment config + txn insertion
def test_01_payment_config(admin):
    r = admin.patch(f"{BASE}/api/quotations/{S['qid']}/payment-config",
                    json={"payment_enabled": True, "allowed_pay_type": "full", "card_fee_enabled": True, "card_fee_percent": 5.5})
    assert r.status_code == 200 and r.json()["payment_enabled"] is True
    db.payment_transactions.delete_many({"session_id": SID})
    db.payment_transactions.insert_one({
        "id": str(uuid.uuid4()), "session_id": SID, "quotation_id": S["qid"], "tenant_id": S["tid"],
        "amount": 1055.0, "base_amount": 1000.0, "card_fee_amount": 55.0, "currency": "MXN",
        "status": "initiated", "payment_status": "pending", "applied": False,
        "created_at": datetime.now(timezone.utc).isoformat()})


# Public link -> verification_error (real Stripe rejects key)
def test_02_public_unresolved_verification_error():
    r = requests.get(f"{BASE}/api/public/quotations/{S['token']}")
    assert r.status_code == 200
    p = r.json()["payment"]
    assert p["enabled"] is True
    assert p["unresolved"] == {"state": "verification_error", "session_id": SID}
    assert p["last_session_id"] == SID


def test_03_payment_status_verification_error():
    r = requests.get(f"{BASE}/api/public/quotations/{S['token']}/payment-status/{SID}")
    assert r.status_code == 200
    d = r.json()
    assert d["state"] == "verification_error" and d["payment_status"] == "pending" and d["code"] == "TEST-IT69"
    assert d["amount_total"] == 105500


def test_04_checkout_blocked_409():
    r = requests.post(f"{BASE}/api/public/quotations/{S['token']}/checkout", json={"origin_url": BASE, "pay_type": "total"})
    assert r.status_code == 409 and "No vuelvas a pagar" in r.json()["detail"] and "TEST-IT69" in r.json()["detail"]
    assert db.payment_transactions.count_documents({"quotation_id": S["qid"]}) == 1


def test_05_payment_status_token_mismatch_404():
    other = db.quotations.find_one({"public_link.token": {"$exists": True, "$ne": S["token"]}, "id": {"$ne": S["qid"]}})
    assert other
    r = requests.get(f"{BASE}/api/public/quotations/{other['public_link']['token']}/payment-status/{SID}")
    assert r.status_code == 404
    assert requests.get(f"{BASE}/api/public/quotations/{S['token']}/payment-status/cs_nope").status_code == 404


# Executive verify-stripe
def test_06_verify_stripe_exec(admin):
    r = admin.post(f"{BASE}/api/quotations/{S['qid']}/verify-stripe")
    assert r.status_code == 200
    d = r.json()
    assert d["key_type"] == "rk_"
    t = next(t for t in d["transactions"] if t["session_id"] == SID)
    assert t["local_status"] == "pending" and t["amount"] == 1055.0 and t["base_amount"] == 1000.0 and t["card_fee_amount"] == 55.0
    assert t["error"] and "inválida" in t["error"], t["error"]
    assert d["credited_now"] == 0 and d["amount_paid"] == 0


def test_07_verify_stripe_auth_and_tenant(admin, owner):
    assert requests.post(f"{BASE}/api/quotations/{S['qid']}/verify-stripe").status_code in (401, 403)
    assert admin.post(f"{BASE}/api/quotations/nonexistent-id/verify-stripe").status_code == 404
    other = db.quotations.find_one({"tenant_id": {"$ne": S["tid"]}})
    if other:
        assert admin.post(f"{BASE}/api/quotations/{other['id']}/verify-stripe").status_code == 404


# Webhook never trusts payload
def test_08_webhook_fake_paid_not_credited():
    ev = {"id": "evt_t69", "type": "checkout.session.completed",
          "data": {"object": {"id": SID, "payment_status": "paid", "amount_total": 999999, "metadata": {"tenant_id": S["tid"]}}}}
    r = requests.post(f"{BASE}/api/webhook/stripe", json=ev)
    assert r.status_code == 200
    q = db.quotations.find_one({"id": S["qid"]})
    assert (q.get("amount_paid") or 0) == 0
    assert db.payment_transactions.find_one({"session_id": SID})["payment_status"] != "paid"


def test_09_webhook_unknown_and_garbage():
    ev = {"id": "evt_t69b", "type": "checkout.session.completed", "data": {"object": {"id": "cs_unknown_it69", "payment_status": "paid"}}}
    assert requests.post(f"{BASE}/api/webhook/stripe", json=ev).status_code == 200
    assert requests.post(f"{BASE}/api/webhook/stripe", data=b"not json", headers={"Content-Type": "application/json"}).status_code == 200


# Regression Iter4 anti-double-charge
def test_10_paid_blocks_checkout_and_regen(admin):
    db.payment_transactions.update_one({"session_id": SID}, {"$set": {"payment_status": "expired", "status": "expired"}})
    r = admin.patch(f"{BASE}/api/quotations/{S['qid']}/mark-paid", json={"amount": 1000, "method": "transfer"})
    assert r.status_code == 200, r.text
    assert r.json()["payment_status"] == "paid" and r.json()["amount_paid"] == 1000
    r = requests.post(f"{BASE}/api/public/quotations/{S['token']}/checkout", json={"origin_url": BASE, "pay_type": "total"})
    assert r.status_code == 400 and "pagada" in r.json()["detail"]
    r = admin.post(f"{BASE}/api/quotations/{S['qid']}/public-link", json={})
    assert r.status_code in (200, 201), r.text
    tok = db.quotations.find_one({"id": S["qid"]})["public_link"]["token"]
    r = requests.post(f"{BASE}/api/public/quotations/{tok}/checkout", json={"origin_url": BASE, "pay_type": "total"})
    assert r.status_code == 400 and "pagada" in r.json()["detail"]
    pub = requests.get(f"{BASE}/api/public/quotations/{tok}").json()
    assert pub["quotation"]["payment_status"] == "paid" and pub["payment"]["unresolved"] is None
