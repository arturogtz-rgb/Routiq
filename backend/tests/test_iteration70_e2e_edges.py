"""Iter 70 — edge cases HTTP (URL pública) para needs_review / conciliación manual / regresión 69.
Siembra directamente en Mongo una cotización TEST temporal en el tenant demo y la elimina al final."""
import os
import uuid
import concurrent.futures
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
NOW = datetime.now(timezone.utc).isoformat()


def _login(email):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "Demo2026!"})
    if r.status_code != 200:
        pytest.skip(f"login failed {email}")
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@aventurate.mx")


@pytest.fixture(scope="module")
def executive():
    return _login("ejecutivo@aventurate.mx")


@pytest.fixture
def quote():
    tenant = db.companies.find_one({"slug": "aventurate"}, {"_id": 0, "id": 1})["id"]
    base = db.quotations.find_one({"tenant_id": tenant, "public_link.token": {"$exists": True}}, {"_id": 0})
    qid, token = f"TEST_it70_{uuid.uuid4().hex[:8]}", f"TEST_it70_tok_{uuid.uuid4().hex[:10]}"
    doc = {**base, "id": qid, "code": f"TEST-IT70-{qid[-4:]}", "final_total": 1000.0, "total": 1000.0,
           "amount_paid": 0.0, "payment_status": "unpaid", "payment_enabled": True, "allowed_pay_type": "full",
           "card_fee_enabled": False, "credited_sessions": [], "payment_review": False, "archived": False,
           "public_link": {"token": token, "expires_at": "2099-01-01T00:00:00+00:00", "created_at": NOW}}
    db.quotations.insert_one(doc)
    yield {"id": qid, "token": token, "tenant": tenant, "code": doc["code"]}
    db.quotations.delete_many({"id": qid})
    db.payment_transactions.delete_many({"quotation_id": qid})
    db.audit_log.delete_many({"quotation_id": qid})


def _txn(q, sid, **extra):
    d = {"id": "it70e-" + sid, "session_id": sid, "quotation_id": q["id"], "tenant_id": q["tenant"], "amount": 500.0,
         "base_amount": 500.0, "card_fee_amount": 0.0, "currency": "MXN", "status": "complete", "payment_status": "paid",
         "applied": False, "created_at": NOW, "paid_at": NOW, "pay_type": "total"}
    d.update(extra)
    db.payment_transactions.insert_one(d)
    return sid


def _checkout(q):
    return requests.post(f"{BASE_URL}/api/public/quotations/{q['token']}/checkout",
                         json={"pay_type": "total", "origin_url": BASE_URL})


# needs_review en cotización parcial -> 409 + payment-status needs_review + unresolved en la vista pública
def test_needs_review_partial_blocks_checkout(quote):
    db.quotations.update_one({"id": quote["id"]}, {"$set": {"amount_paid": 500.0, "payment_status": "partial", "payment_review": True}})
    sid = _txn(quote, "cs_live_it70e_nr", review_state="needs_review", review_reason="x", review_at=NOW)
    r = _checkout(quote)
    assert r.status_code == 409 and r.json()["detail"] == "Recibimos tu pago; tu ejecutivo lo está revisando. No vuelvas a pagar."
    ps = requests.get(f"{BASE_URL}/api/public/quotations/{quote['token']}/payment-status/{sid}").json()
    assert ps["state"] == "needs_review"
    pub = requests.get(f"{BASE_URL}/api/public/quotations/{quote['token']}").json()
    assert pub["payment"]["unresolved"]["state"] == "needs_review"
    assert db.payment_transactions.find_one({"session_id": sid})["applied"] is False
    assert db.quotations.find_one({"id": quote["id"]})["amount_paid"] == 500.0


# ejecutivo no admin: 403; anónimo: 401
def test_reconcile_requires_admin(quote, executive):
    sid = _txn(quote, "cs_live_it70e_ex", review_state="needs_review")
    r = executive.post(f"{BASE_URL}/api/quotations/{quote['id']}/transactions/{sid}/reconcile-manual", json={"reason": "x"})
    assert r.status_code == 403
    v = executive.post(f"{BASE_URL}/api/quotations/{quote['id']}/verify-stripe").json()
    assert v["is_admin"] is False and v["transactions"][0]["can_reconcile"] is False
    assert requests.post(f"{BASE_URL}/api/quotations/{quote['id']}/transactions/{sid}/reconcile-manual", json={}).status_code == 401


# conciliación: ya aplicada -> 400; sesión de otra cotización -> 404
def test_reconcile_already_applied_and_wrong_quote(quote, admin):
    sid = _txn(quote, "cs_live_it70e_ap", applied=True)
    r = admin.post(f"{BASE_URL}/api/quotations/{quote['id']}/transactions/{sid}/reconcile-manual", json={})
    assert r.status_code == 400
    r = admin.post(f"{BASE_URL}/api/quotations/OTHER_QID/transactions/{sid}/reconcile-manual", json={})
    assert r.status_code == 404


# conciliar una transacción pendiente con verification_error -> 'reconciled', desbloquea, no suma
def test_reconcile_pending_verification_error_unblocks(quote, admin):
    sid = _txn(quote, "cs_live_it70e_ve", payment_status="pending", status="initiated",
               verification_state="error", last_error="boom", paid_at=None)
    pub = requests.get(f"{BASE_URL}/api/public/quotations/{quote['token']}").json()
    assert pub["payment"]["unresolved"]["state"] == "verification_error"
    r = _checkout(quote)
    assert r.status_code == 409 and quote["code"] in r.json()["detail"] and "No vuelvas a pagar" in r.json()["detail"]
    r = admin.post(f"{BASE_URL}/api/quotations/{quote['id']}/transactions/{sid}/reconcile-manual", json={"reason": "TEST transfer"})
    assert r.status_code == 200 and r.json()["reconciled_manually"]["reason"] == "TEST transfer"
    t = db.payment_transactions.find_one({"session_id": sid})
    assert t["payment_status"] == "reconciled" and t["applied"] is True
    q = db.quotations.find_one({"id": quote["id"]})
    assert q["amount_paid"] == 0.0 and sid not in q["credited_sessions"] and q["payment_review"] is False
    pub = requests.get(f"{BASE_URL}/api/public/quotations/{quote['token']}").json()
    assert not pub["payment"].get("unresolved")
    audits = list(db.audit_log.find({"quotation_id": quote["id"], "action": "payment_reconciled"}))
    assert len(audits) == 1 and "TEST transfer" in audits[0]["detail"]


# conciliación concurrente: solo una debe ganar (una auditoría)
def test_reconcile_concurrent_single_audit(quote, admin):
    sid = _txn(quote, "cs_live_it70e_cc", review_state="needs_review")
    url = f"{BASE_URL}/api/quotations/{quote['id']}/transactions/{sid}/reconcile-manual"
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        codes = [f.result().status_code for f in [ex.submit(admin.post, url, json={}) for _ in range(4)]]
    audits = db.audit_log.count_documents({"quotation_id": quote["id"], "action": "payment_reconciled"})
    print("concurrent codes", codes, "audits", audits)
    assert codes.count(200) == 1 and audits == 1


# regresión 4/69: cotización pagada sin pendientes -> 400 'ya está pagada'
def test_paid_quotation_checkout_400(quote):
    db.quotations.update_one({"id": quote["id"]}, {"$set": {"amount_paid": 1000.0, "payment_status": "paid"}})
    r = _checkout(quote)
    assert r.status_code == 400 and "ya está pagada" in r.json()["detail"]


# doble cobro: dos transacciones pagadas -> ambas con duplicate_warning
def test_duplicate_warning_api(quote, admin):
    _txn(quote, "cs_live_it70e_d1", applied=True)
    _txn(quote, "cs_live_it70e_d2", review_state="needs_review")
    v = admin.post(f"{BASE_URL}/api/quotations/{quote['id']}/verify-stripe").json()
    rows = {t["session_id"]: t for t in v["transactions"]}
    assert all(rows[s].get("duplicate_warning") == "Posible cobro doble: verifica un reembolso" for s in ("cs_live_it70e_d1", "cs_live_it70e_d2"))
    assert v["is_admin"] is True and rows["cs_live_it70e_d2"]["can_reconcile"] is True and rows["cs_live_it70e_d1"]["can_reconcile"] is False
