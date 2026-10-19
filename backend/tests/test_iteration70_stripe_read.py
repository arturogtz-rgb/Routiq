"""Iter 70 — lectura de sesiones con StripeObject auténtico + protección contra doble acreditación."""
import os
import uuid
from types import SimpleNamespace

from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
import stripe  # noqa: E402

import database  # noqa: E402
import notifications  # noqa: E402
import payments_core  # noqa: E402


def _obj(status, payment_status, sid="cs_live_test123"):
    return stripe.StripeObject.construct_from({
        "id": sid, "object": "checkout.session", "status": status, "payment_status": payment_status,
        "amount_total": 105500, "currency": "mxn", "payment_intent": "pi_123", "url": "https://checkout.stripe.com/x",
        "metadata": {"quotation_id": "q1", "tenant_id": "t1", "pay_type": "total"},
    }, "sk_live_x")


class _FakeClient:
    def __init__(self, obj):
        self.v1 = SimpleNamespace(checkout=SimpleNamespace(sessions=SimpleNamespace(retrieve=lambda sid: obj, expire=lambda sid: obj)))


@pytest.mark.parametrize("status,pay,expected", [
    ("complete", "paid", "paid"), ("open", "unpaid", "open"),
    ("complete", "unpaid", "processing"), ("expired", "unpaid", "expired"),
])
@pytest.mark.asyncio
async def test_a_reads_real_stripeobject(monkeypatch, status, pay, expected):
    obj = _obj(status, pay)
    assert not isinstance(obj.metadata, dict)  # el caso real que rompía la librería
    monkeypatch.setattr(payments_core, "_client", lambda key: _FakeClient(obj))
    st = await payments_core.stripe_get_status("sk_live_x", "cs_live_test123")
    assert st.status == status and st.payment_status == pay and st.amount_total == 105500
    assert st.currency == "mxn" and st.payment_intent == "pi_123"
    assert st.metadata == {"quotation_id": "q1", "tenant_id": "t1", "pay_type": "total"}
    assert payments_core.classify(st) == expected


def test_payment_intent_expanded_object():
    o = stripe.StripeObject.construct_from({"id": "cs_1", "status": "complete", "payment_status": "paid",
                                            "payment_intent": {"id": "pi_9", "object": "payment_intent"}, "metadata": None}, "k")
    st = payments_core.session_from_stripe(o)
    assert st.payment_intent == "pi_9" and st.metadata == {}


@pytest.mark.skipif(not os.environ.get("STRIPE_TEST_SECRET_KEY"), reason="Sin llave sk_test_ propia (el proxy de Emergent no permite leer sesiones)")
@pytest.mark.asyncio
async def test_real_stripe_test_mode_create_and_read():
    key = os.environ["STRIPE_TEST_SECRET_KEY"]
    c = payments_core._client(key)
    s = c.v1.checkout.sessions.create(params={"mode": "payment", "success_url": "https://x/s", "cancel_url": "https://x/c",
                                              "line_items": [{"price_data": {"currency": "mxn", "product_data": {"name": "T70"}, "unit_amount": 1050}, "quantity": 1}],
                                              "metadata": {"quotation_id": "t70"}})
    st = await payments_core.stripe_get_status(key, s.id)
    assert st.status == "open" and st.payment_status == "unpaid" and st.metadata == {"quotation_id": "t70"}
    await payments_core.stripe_expire_session(key, s.id)


# ---------- doble acreditación ----------

@pytest_asyncio.fixture
async def env(monkeypatch):
    database._client = None
    database._db = None
    db = database.get_db()
    tid, qid, token = f"TEST70-{uuid.uuid4().hex[:6]}", str(uuid.uuid4()), f"tok70{uuid.uuid4().hex[:8]}"
    await db.companies.insert_one({"id": tid, "slug": tid.lower(), "name": "TEST70", "stripe": {"secret_key": "sk_live_fake"},
                                   "stripe_allowed": True, "base_currency": "MXN"})
    await db.quotations.insert_one({"id": qid, "tenant_id": tid, "code": "COT-T70", "state": "enviada", "type": "servicios",
                                    "total": 1000.0, "final_total": 1000.0, "items": [], "currency": "MXN", "dates": {},
                                    "pax": {"adultos": 2}, "amount_paid": 0, "payment_status": "unpaid", "payment_enabled": True,
                                    "allowed_pay_type": "full", "card_fee_enabled": True, "card_fee_percent": 5.5,
                                    "public_link": {"token": token}, "client_snapshot": {"name": "C", "channel": "directo"}})
    calls = {"notify": 0}

    async def _notify(*a, **k):
        calls["notify"] += 1
    monkeypatch.setattr(notifications, "notify_payment", _notify)
    status = {}
    monkeypatch.setattr(payments_core, "_client", lambda key: _FakeClient(None))

    async def get_status(key, sid):
        return payments_core.session_from_stripe(_obj(*status.get(sid, ("complete", "paid")), sid=sid))
    monkeypatch.setattr(payments_core, "stripe_get_status", get_status)
    admin = {"id": f"u-{tid}", "tenant_id": tid, "role": "company_admin", "name": "Admin T70", "email": "a@t70"}
    exec_ = {"id": f"e-{tid}", "tenant_id": tid, "role": "executive", "name": "Ejec T70", "email": "e@t70"}
    yield SimpleNamespace(db=db, tid=tid, qid=qid, token=token, calls=calls, status=status, admin=admin, exec_=exec_)
    for col in ("payment_transactions", "quotations", "audit_log"):
        await db[col].delete_many({"tenant_id": tid})
    await db.companies.delete_many({"id": tid})


async def _txn(ctx, **extra):
    sid = f"cs_live_{uuid.uuid4().hex[:10]}"
    await ctx.db.payment_transactions.insert_one({
        "id": str(uuid.uuid4()), "session_id": sid, "quotation_id": ctx.qid, "tenant_id": ctx.tid,
        "amount": 1055.0, "base_amount": 1000.0, "card_fee_amount": 55.0, "currency": "MXN",
        "status": "initiated", "payment_status": "pending", "applied": False,
        "created_at": f"2026-10-19T10:00:0{len(ctx.status)}+00:00", **extra})
    ctx.status[sid] = ("complete", "paid")
    return sid


async def _company(ctx):
    return await ctx.db.companies.find_one({"id": ctx.tid}, {"_id": 0})


async def _q(ctx):
    return await ctx.db.quotations.find_one({"id": ctx.qid}, {"_id": 0})


def _as(user):
    from server import app
    from auth import require_tenant
    app.dependency_overrides[require_tenant] = lambda: user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    from server import app
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b_unpaid_credits_once(env):
    await _txn(env)
    for _ in range(3):
        await payments_core.reconcile_quotation(env.db, env.qid, await _company(env))
    q = await _q(env)
    assert q["amount_paid"] == 1000.0 and q["payment_status"] == "paid" and env.calls["notify"] == 1  # f) solo base


@pytest.mark.asyncio
async def test_c_already_paid_goes_needs_review(env):
    await env.db.quotations.update_one({"id": env.qid}, {"$set": {"amount_paid": 1000.0, "payment_status": "paid"}})  # pago manual
    sid = await _txn(env)
    await payments_core.reconcile_quotation(env.db, env.qid, await _company(env))
    await payments_core.reconcile_quotation(env.db, env.qid, await _company(env))
    q = await _q(env)
    t = await env.db.payment_transactions.find_one({"session_id": sid})
    assert q["amount_paid"] == 1000.0 and q["payment_review"] is True
    assert t["payment_status"] == "paid" and t["applied"] is False and t["review_state"] == "needs_review"
    un = await payments_core.unresolved_state(env.db, env.qid)
    assert un["state"] == "needs_review"
    async with _as(env.exec_) as c:
        r = await c.get(f"/api/public/quotations/{env.token}/payment-status/{sid}")
        assert r.json()["state"] == "needs_review"
        rows = (await c.post(f"/api/quotations/{env.qid}/verify-stripe")).json()
        row = [x for x in rows["transactions"] if x["session_id"] == sid][0]
        assert row["review_state"] == "needs_review" and row["can_reconcile"] is False and rows["is_admin"] is False
        r = await c.post(f"/api/quotations/{env.qid}/transactions/{sid}/reconcile-manual", json={"reason": "x"})
        assert r.status_code == 403
        lst = (await c.get("/api/quotations")).json()
        assert any(x["id"] == env.qid and x.get("payment_review") for x in lst)


@pytest.mark.asyncio
async def test_partial_overpay_needs_review(env):
    await env.db.quotations.update_one({"id": env.qid}, {"$set": {"amount_paid": 500.0, "payment_status": "partial"}})
    sid = await _txn(env)
    await payments_core.reconcile_quotation(env.db, env.qid, await _company(env))
    assert (await _q(env))["amount_paid"] == 500.0
    assert (await env.db.payment_transactions.find_one({"session_id": sid}))["review_state"] == "needs_review"


@pytest.mark.asyncio
async def test_d_manual_reconcile_no_amount_and_no_recredit(env):
    await env.db.quotations.update_one({"id": env.qid}, {"$set": {"amount_paid": 1000.0, "payment_status": "paid"}})
    sid = await _txn(env)
    pending_sid = await _txn(env)
    env.status[pending_sid] = ("open", "unpaid")
    await payments_core.reconcile_quotation(env.db, env.qid, await _company(env))
    async with _as(env.admin) as c:
        r = await c.post(f"/api/quotations/{env.qid}/transactions/{sid}/reconcile-manual", json={"reason": "Registrado por transferencia"})
        assert r.status_code == 200
        r2 = await c.post(f"/api/quotations/{env.qid}/transactions/{pending_sid}/reconcile-manual", json={})
        assert r2.status_code == 200
        again = await c.post(f"/api/quotations/{env.qid}/transactions/{sid}/reconcile-manual", json={})
        assert again.status_code == 400
        await c.post(f"/api/quotations/{env.qid}/verify-stripe")
    env.status[pending_sid] = ("complete", "paid")
    for _ in range(2):
        await payments_core.reconcile_quotation(env.db, env.qid, await _company(env))
    q = await _q(env)
    t = await env.db.payment_transactions.find_one({"session_id": sid})
    tp = await env.db.payment_transactions.find_one({"session_id": pending_sid})
    assert q["amount_paid"] == 1000.0 and q["payment_review"] is False
    assert sid in q["credited_sessions"] and pending_sid not in q["credited_sessions"]  # pendiente: no se absorbe un cobro futuro
    assert t["applied"] is True and t["reconciled_manually"]["by_name"] == "Admin T70"
    assert tp["payment_status"] == "reconciled" and tp["applied"] is True
    audit = await env.db.audit_log.find_one({"tenant_id": env.tid, "action": "payment_reconciled"})
    assert audit and "Registrado por transferencia" in audit["detail"] and audit["executive_name"] == "Admin T70"
    assert await payments_core.unresolved_state(env.db, env.qid) is None


@pytest.mark.asyncio
async def test_e_two_paid_sessions_duplicate_warning(env):
    s1 = await _txn(env)
    s2 = await _txn(env)
    await payments_core.reconcile_quotation(env.db, env.qid, await _company(env))
    async with _as(env.admin) as c:
        rows = (await c.post(f"/api/quotations/{env.qid}/verify-stripe")).json()["transactions"]
    by = {r["session_id"]: r for r in rows}
    assert by[s1]["duplicate_warning"] == by[s2]["duplicate_warning"] == "Posible cobro doble: verifica un reembolso"
    q = await _q(env)
    assert q["amount_paid"] == 1000.0  # solo una se acreditó; la otra quedó en revisión
    assert sorted([by[s1]["review_state"] or "", by[s2]["review_state"] or ""]) == ["", "needs_review"]


@pytest.mark.asyncio
async def test_reconciled_pending_later_paid_goes_to_review(env, monkeypatch):
    """Una sesión pendiente conciliada a mano que luego se cobra NO se absorbe: queda en revisión."""
    await env.db.quotations.update_one({"id": env.qid}, {"$set": {"amount_paid": 1000.0, "payment_status": "paid"}})
    sid = await _txn(env)
    env.status[sid] = ("open", "unpaid")
    expired = []

    async def expire(key, s):
        expired.append(s)
        raise Exception("no se pudo expirar")
    monkeypatch.setattr(payments_core, "stripe_expire_session", expire)
    async with _as(env.admin) as c:
        assert (await c.post(f"/api/quotations/{env.qid}/transactions/{sid}/reconcile-manual", json={})).status_code == 200
        assert (await c.get(f"/api/public/quotations/{env.token}/payment-status/{sid}")).json()["state"] == "closed"
    assert expired == [sid]
    q = await _q(env)
    assert sid not in (q.get("credited_sessions") or [])
    env.status[sid] = ("complete", "paid")
    fake = {"id": "evt", "type": "checkout.session.completed", "data": {"object": {"id": sid}}}
    async with _as(env.admin) as c:
        assert (await c.post("/api/webhook/stripe", json=fake)).status_code == 200
    t = await env.db.payment_transactions.find_one({"session_id": sid})
    q = await _q(env)
    assert q["amount_paid"] == 1000.0 and t["review_state"] == "needs_review" and q["payment_review"] is True
