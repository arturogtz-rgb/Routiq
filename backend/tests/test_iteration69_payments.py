"""Iter 69 — verificación/acreditación de pagos con Stripe SIMULADO (sin red)."""
import asyncio
import logging
import uuid
from types import SimpleNamespace

from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
import httpx  # noqa: E402
import pytest
import pytest_asyncio

import database
import notifications
import payments_core
from routes import public_payments


def _st(status="open", payment_status="unpaid"):
    return SimpleNamespace(status=status, payment_status=payment_status, amount_total=0, currency="mxn", metadata={})


class FakeCheckout:
    created = []

    def __init__(self, api_key="", webhook_url="", **_):
        pass

    async def create_checkout_session(self, req):
        sid = f"cs_test_{uuid.uuid4().hex[:10]}"
        FakeCheckout.created.append(sid)
        return SimpleNamespace(session_id=sid, url=f"https://checkout.stripe.test/{sid}")


@pytest_asyncio.fixture
async def env(monkeypatch):
    database._client = None
    database._db = None
    db = database.get_db()
    tid, qid, token = f"TEST69-{uuid.uuid4().hex[:6]}", str(uuid.uuid4()), f"tok69{uuid.uuid4().hex[:8]}"
    await db.companies.insert_one({"id": tid, "name": "TEST69", "slug": tid.lower(), "stripe": {"secret_key": "rk_test_fake"},
                                   "stripe_allowed": True, "base_currency": "MXN", "deposit_percent": 50})
    await db.quotations.insert_one({"id": qid, "tenant_id": tid, "code": "COT-T69", "state": "enviada", "type": "servicios",
                                    "total": 1000.0, "final_total": 1000.0, "subtotal": 1000.0, "items": [], "currency": "MXN",
                                    "dates": {}, "pax": {"adultos": 2}, "amount_paid": 0, "payment_status": "unpaid",
                                    "payment_enabled": True, "allowed_pay_type": "full",
                                    "card_fee_enabled": True, "card_fee_percent": 5.5,
                                    "public_link": {"token": token}, "client_snapshot": {"name": "C", "channel": "directo"}})
    calls = {"notify": 0}

    async def _notify(*a, **k):
        calls["notify"] += 1
    monkeypatch.setattr(notifications, "notify_payment", _notify)
    monkeypatch.setattr(public_payments, "StripeCheckout", FakeCheckout)
    FakeCheckout.created = []
    ctx = SimpleNamespace(db=db, tid=tid, qid=qid, token=token, calls=calls)
    yield ctx
    await db.payment_transactions.delete_many({"tenant_id": tid})
    await db.quotations.delete_many({"tenant_id": tid})
    await db.companies.delete_many({"id": tid})
    await db.audit_log.delete_many({"tenant_id": tid})


async def _txn(ctx, sid=None, amount=1055.0, base=1000.0, **extra):
    sid = sid or f"cs_test_{uuid.uuid4().hex[:10]}"
    await ctx.db.payment_transactions.insert_one({
        "id": str(uuid.uuid4()), "session_id": sid, "quotation_id": ctx.qid, "tenant_id": ctx.tid,
        "amount": amount, "base_amount": base, "card_fee_amount": round(amount - base, 2), "currency": "MXN",
        "status": "initiated", "payment_status": "pending", "applied": False,
        "created_at": "2026-10-19T10:00:00+00:00", **extra})
    return sid


def _stripe(monkeypatch, fn):
    async def fake(api_key, sid):
        return fn(sid)
    monkeypatch.setattr(payments_core, "stripe_get_status", fake)


def _client():
    from server import app
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _q(ctx):
    return await ctx.db.quotations.find_one({"id": ctx.qid}, {"_id": 0})


@pytest.mark.asyncio
async def test_a_stripe_403_is_verification_error(env, monkeypatch, caplog):
    sid = await _txn(env)

    def boom(_):
        raise Exception("Failed to retrieve session status: Request req_1: The provided key 'rk_test_***' does not have the required permissions (403)")
    _stripe(monkeypatch, boom)
    with caplog.at_level(logging.WARNING, logger="routiq"):
        async with _client() as c:
            r = await c.get(f"/api/public/quotations/{env.token}/payment-status/{sid}")
            assert r.status_code == 200 and r.json()["state"] == "verification_error"
            assert r.json()["payment_status"] != "paid"
            pub = (await c.get(f"/api/public/quotations/{env.token}")).json()
            assert pub["payment"]["unresolved"]["state"] == "verification_error"
            assert pub["payment"]["last_session_id"] == sid
            r2 = await c.post(f"/api/public/quotations/{env.token}/checkout", json={"origin_url": "http://x", "pay_type": "total"})
            assert r2.status_code == 409 and "No vuelvas a pagar" in r2.json()["detail"]
    warn = [r for r in caplog.records if r.levelno == logging.WARNING and "get_checkout_status failed" in r.getMessage()]
    assert warn, "WARNING esperado"
    m = warn[0].getMessage()
    assert sid in m and env.qid in m and "key_type=rk_" in m and "rk_test_fake" not in m
    assert FakeCheckout.created == []


@pytest.mark.asyncio
async def test_b_apply_fails_once_then_retries_once(env, monkeypatch):
    sid = await _txn(env)
    _stripe(monkeypatch, lambda _: _st("complete", "paid"))
    real = payments_core.apply_payment_to_quotation
    state = {"n": 0}

    async def flaky(db, txn):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("db down")
        return await real(db, txn)
    monkeypatch.setattr(payments_core, "apply_payment_to_quotation", flaky)
    company = await env.db.companies.find_one({"id": env.tid}, {"_id": 0})
    await payments_core.reconcile_quotation(env.db, env.qid, company)
    t = await env.db.payment_transactions.find_one({"session_id": sid})
    assert t["payment_status"] == "paid" and t["applied"] is False and "db down" in t["apply_error"]
    assert (await _q(env))["amount_paid"] == 0
    await payments_core.reconcile_quotation(env.db, env.qid, company)
    await payments_core.reconcile_quotation(env.db, env.qid, company)
    t = await env.db.payment_transactions.find_one({"session_id": sid})
    q = await _q(env)
    assert t["applied"] is True and q["amount_paid"] == 1000.0 and q["payment_status"] == "paid"
    assert env.calls["notify"] == 1


@pytest.mark.asyncio
async def test_c_d_double_reconcile_and_card_fee(env, monkeypatch):
    await _txn(env)
    _stripe(monkeypatch, lambda _: _st("complete", "paid"))
    company = await env.db.companies.find_one({"id": env.tid}, {"_id": 0})
    await asyncio.gather(*[payments_core.reconcile_quotation(env.db, env.qid, company) for _ in range(3)])
    await payments_core.reconcile_quotation(env.db, env.qid, company)
    q = await _q(env)
    assert q["amount_paid"] == 1000.0  # base, sin el 5.5% de comisión
    assert env.calls["notify"] == 1


@pytest.mark.asyncio
async def test_e_complete_unpaid_not_credited(env, monkeypatch):
    sid = await _txn(env)
    _stripe(monkeypatch, lambda _: _st("complete", "unpaid"))
    async with _client() as c:
        r = await c.get(f"/api/public/quotations/{env.token}/payment-status/{sid}")
        assert r.json()["state"] == "processing"
        pub = (await c.get(f"/api/public/quotations/{env.token}")).json()
        assert pub["payment"]["unresolved"]["state"] == "processing"
        r2 = await c.post(f"/api/public/quotations/{env.token}/checkout", json={"origin_url": "http://x", "pay_type": "total"})
        assert r2.status_code == 409
    assert (await _q(env))["amount_paid"] == 0


@pytest.mark.asyncio
async def test_two_clicks_never_two_open_sessions(env, monkeypatch):
    _stripe(monkeypatch, lambda _: _st("open", "unpaid"))
    expired = []

    async def expire(api_key, sid):
        expired.append(sid)
        return True
    monkeypatch.setattr(payments_core, "stripe_expire_session", expire)
    async with _client() as c:
        r1 = await c.post(f"/api/public/quotations/{env.token}/checkout", json={"origin_url": "http://x", "pay_type": "total"})
        r2 = await c.post(f"/api/public/quotations/{env.token}/checkout", json={"origin_url": "http://x", "pay_type": "total"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert expired == [r1.json()["session_id"]]
    open_ = await env.db.payment_transactions.count_documents({"quotation_id": env.qid, "payment_status": "pending"})
    assert open_ == 1
    t = await env.db.payment_transactions.find_one({"session_id": r2.json()["session_id"]})
    assert t["amount"] == 1055.0 and t["base_amount"] == 1000.0


@pytest.mark.asyncio
async def test_two_clicks_expire_fails_reuses_url(env, monkeypatch):
    _stripe(monkeypatch, lambda _: _st("open", "unpaid"))

    async def expire(api_key, sid):
        raise Exception("expire not supported")
    monkeypatch.setattr(payments_core, "stripe_expire_session", expire)
    async with _client() as c:
        r1 = await c.post(f"/api/public/quotations/{env.token}/checkout", json={"origin_url": "http://x", "pay_type": "total"})
        r2 = await c.post(f"/api/public/quotations/{env.token}/checkout", json={"origin_url": "http://x", "pay_type": "total"})
    assert r2.json()["session_id"] == r1.json()["session_id"] and r2.json()["url"] == r1.json()["url"]
    assert len(FakeCheckout.created) == 1


@pytest.mark.asyncio
async def test_concurrent_clicks_lock(env, monkeypatch):
    _stripe(monkeypatch, lambda _: _st("open", "unpaid"))

    async def expire(api_key, sid):
        return True
    monkeypatch.setattr(payments_core, "stripe_expire_session", expire)
    async with _client() as c:
        rs = await asyncio.gather(*[c.post(f"/api/public/quotations/{env.token}/checkout", json={"origin_url": "http://x", "pay_type": "total"}) for _ in range(2)])
    assert await env.db.payment_transactions.count_documents({"quotation_id": env.qid, "payment_status": "pending"}) == 1
    assert sorted(r.status_code for r in rs) in ([200, 200], [200, 409])


@pytest.mark.asyncio
async def test_g_paid_quotation_blocks_second_charge(env, monkeypatch):
    await _txn(env)
    _stripe(monkeypatch, lambda _: _st("complete", "paid"))
    async with _client() as c:
        r = await c.post(f"/api/public/quotations/{env.token}/checkout", json={"origin_url": "http://x", "pay_type": "total"})
    assert r.status_code == 400 and "pagada" in r.json()["detail"]
    assert FakeCheckout.created == []


@pytest.mark.asyncio
async def test_webhook_never_trusts_payload(env, monkeypatch):
    sid = await _txn(env)
    _stripe(monkeypatch, lambda _: _st("open", "unpaid"))
    fake = {"id": "evt_1", "type": "checkout.session.completed",
            "data": {"object": {"id": sid, "payment_status": "paid", "amount_total": 99999999, "metadata": {"tenant_id": env.tid}}}}
    unknown = {"id": "evt_2", "type": "checkout.session.completed", "data": {"object": {"id": "cs_unknown", "payment_status": "paid"}}}
    async with _client() as c:
        assert (await c.post("/api/webhook/stripe", json=fake)).status_code == 200
        assert (await c.post("/api/webhook/stripe", json=unknown)).status_code == 200
    assert (await _q(env))["amount_paid"] == 0
    _stripe(monkeypatch, lambda _: _st("complete", "paid"))
    async with _client() as c:
        assert (await c.post("/api/webhook/stripe", json=fake)).status_code == 200
    assert (await _q(env))["amount_paid"] == 1000.0  # monto de NUESTRA transacción


@pytest.mark.asyncio
async def test_migration_applied_flag(env):
    s1 = await _txn(env, payment_status="paid", paid_at="2026-10-01")
    s2 = await _txn(env, payment_status="paid", paid_at="2026-10-02")
    await env.db.payment_transactions.update_many({"session_id": {"$in": [s1, s2]}}, {"$unset": {"applied": ""}})
    await env.db.quotations.update_one({"id": env.qid}, {"$set": {"final_total": 3000.0, "amount_paid": 1000.0, "payment_status": "partial"}})
    await payments_core.migrate_applied_flag(env.db)
    t1 = await env.db.payment_transactions.find_one({"session_id": s1})
    t2 = await env.db.payment_transactions.find_one({"session_id": s2})
    assert t1["applied"] is True and t2["applied"] is False
    company = await env.db.companies.find_one({"id": env.tid}, {"_id": 0})
    await payments_core.reconcile_quotation(env.db, env.qid, company)
    assert (await _q(env))["amount_paid"] == 2000.0
