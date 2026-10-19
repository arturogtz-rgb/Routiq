"""Iter 69 — verificación y acreditación de pagos con Stripe (robusta e idempotente).

Regla única de "pagado": Stripe `payment_status == "paid"`.
  - status "complete" + payment_status != "paid"  -> "processing" (banco procesando; NO se acredita)
  - status "expired"                               -> "expired"
  - status "open"                                  -> sigue abierta (se puede pagar)
  - excepción al consultar                         -> "verification_error" (WARNING en log)

Acreditación: la transacción se marca paid con applied=false y después se aplica a la
cotización con un único update atómico guardado por `credited_sessions` (un session_id jamás
acredita dos veces). Si la aplicación falla, queda paid/applied=false y el reconciliador la
reintenta en la siguiente verificación.
"""
import asyncio
import logging
import os
from types import SimpleNamespace

from pymongo import ReturnDocument

from database import now_iso
import notifications

log = logging.getLogger("routiq")

UNRESOLVED = {"$nin": ["paid", "expired", "failed", "reconciled"]}
NEEDS_REVIEW_REASON = "Posible pago duplicado o ya registrado manualmente: acreditarlo superaría el total de la cotización."



def resolve_stripe_key(company: dict) -> str:
    sk = ((company or {}).get("stripe") or {}).get("secret_key")
    return sk or os.environ.get("STRIPE_API_KEY", "")


def key_type(api_key: str) -> str:
    return (api_key or "")[:3] or "none"


def _checkout(api_key: str):
    from emergentintegrations.payments.stripe.checkout import StripeCheckout
    return StripeCheckout(api_key=api_key, webhook_url="")


def _client(api_key: str):
    """Cliente del SDK por llamada (sin estado global). Iter 70: no usamos el parseo de
    emergentintegrations (falla con stripe 15: metadata llega como StripeObject)."""
    import stripe
    opts = {"base_addresses": {"api": "https://integrations.emergentagent.com/stripe"}} if "sk_test_emergent" in (api_key or "") else {}
    return stripe.StripeClient(api_key, **opts)


def _plain(v):
    if v is None:
        return {}
    if hasattr(v, "to_dict"):
        try:
            return v.to_dict()
        except Exception:
            pass
    try:
        return dict(v)
    except Exception:
        return {}


def session_from_stripe(obj) -> SimpleNamespace:
    """Lee SOLO los campos que usamos de una Checkout Session (StripeObject o dict)."""
    def g(k):
        if isinstance(obj, dict):
            return obj.get(k)
        return getattr(obj, k, None)
    pi = g("payment_intent")
    if pi is not None and not isinstance(pi, str):
        pi = getattr(pi, "id", None) or (pi.get("id") if isinstance(pi, dict) else None)
    return SimpleNamespace(id=g("id"), status=g("status"), payment_status=g("payment_status"),
                           amount_total=g("amount_total"), currency=g("currency"),
                           payment_intent=pi, url=g("url"), metadata=_plain(g("metadata")))


async def stripe_get_status(api_key: str, session_id: str):
    """Consulta directa al SDK (punto único, fácil de simular en pruebas)."""
    obj = await asyncio.to_thread(_client(api_key).v1.checkout.sessions.retrieve, session_id)
    return session_from_stripe(obj)


async def stripe_expire_session(api_key: str, session_id: str) -> bool:
    await asyncio.to_thread(_client(api_key).v1.checkout.sessions.expire, session_id)
    return True


async def stripe_session_url(api_key: str, session_id: str) -> str:
    return (await stripe_get_status(api_key, session_id)).url or ""


def readable_error(e: Exception) -> str:
    msg = str(e)
    low = msg.lower()
    if "permission" in low or "rak_" in low or "restricted" in low or "403" in low:
        return "La llave de Stripe no tiene permiso de lectura de Checkout Sessions."
    if "invalid api key" in low or "401" in low or "authentication" in low:
        return "La llave de Stripe es inválida o fue revocada."
    if "no such checkout.session" in low or "no such checkout session" in low:
        return "La sesión no existe en esta cuenta de Stripe (¿llave de otra cuenta o de otro modo test/live?)."
    if "timeout" in low or "timed out" in low or "connection" in low or "network" in low:
        return "Stripe no respondió a tiempo (error de conexión)."
    return f"Stripe devolvió un error: {msg[:200]}"


def classify(st) -> str:
    if getattr(st, "payment_status", None) == "paid":
        return "paid"
    status = getattr(st, "status", None)
    if status == "expired":
        return "expired"
    if status == "complete":
        return "processing"
    return "open"


class NeedsReview(Exception):
    """Acreditar haría que amount_paid supere final_total."""


async def apply_payment_to_quotation(db, txn: dict) -> bool:
    """Acredita base_amount (sin comisión bancaria) una sola vez por session_id. True si acreditó.
    Iter 70: nunca deja amount_paid por encima de final_total (lanza NeedsReview)."""
    sid = txn["session_id"]
    credit = round(float(txn.get("base_amount", txn["amount"])), 2)
    fits = {"$lte": [{"$add": [{"$ifNull": ["$amount_paid", 0]}, credit]},
                     {"$add": [{"$ifNull": ["$final_total", {"$ifNull": ["$total", 0]}]}, 0.01]}]}
    q = await db.quotations.find_one_and_update(
        {"id": txn["quotation_id"], "credited_sessions": {"$ne": sid}, "$expr": fits},
        {"$inc": {"amount_paid": credit}, "$addToSet": {"credited_sessions": sid},
         "$set": {"last_activity_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if q is None:
        cur = await db.quotations.find_one({"id": txn["quotation_id"]}, {"_id": 0, "id": 1, "credited_sessions": 1})
        if not cur:
            raise RuntimeError(f"cotización {txn['quotation_id']} no encontrada")
        if sid in (cur.get("credited_sessions") or []):
            return False  # ya acreditada antes
        raise NeedsReview(NEEDS_REVIEW_REASON)
    amount_paid = round(q.get("amount_paid", 0) or 0, 2)
    final_total = q.get("final_total")
    if final_total is None:
        final_total = q.get("total", 0)
    pay_status = "paid" if amount_paid >= round(final_total, 2) - 0.01 else "partial"
    updates = {"amount_paid": amount_paid, "payment_status": pay_status}
    won = q.get("state") != "ganada"
    if won:
        updates["state"] = "ganada"
    await db.quotations.update_one({"id": q["id"]}, {"$set": updates})
    if won:
        try:
            from deps import _record_audit
            await _record_audit(db, q["tenant_id"], {"id": None, "name": "Pago en línea"}, "won", q, "Ganada por pago del cliente")
        except Exception:
            log.exception("audit payment-won failed")
    try:
        await notifications.notify_payment(db, {**q, **updates}, txn, amount_paid, pay_status)
    except Exception:
        log.exception("payment notification failed")
    return True


async def apply_pending_credit(db, session_id: str) -> dict:
    """Aplica una transacción paid con applied != true. Idempotente."""
    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not txn or txn.get("payment_status") != "paid" or txn.get("applied") is True:
        return {"applied": bool(txn and txn.get("applied")), "credited": False}
    if txn.get("review_state") == "needs_review":
        return {"applied": False, "credited": False, "needs_review": True}
    try:
        credited = await apply_payment_to_quotation(db, txn)
    except NeedsReview as e:
        log.warning("payment needs_review session_id=%s quotation_id=%s base=%s: %s",
                    session_id, txn.get("quotation_id"), txn.get("base_amount"), e)
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"applied": False, "review_state": "needs_review", "review_reason": str(e), "review_at": now_iso()}})
        await db.quotations.update_one({"id": txn["quotation_id"]}, {"$set": {"payment_review": True}})
        return {"applied": False, "credited": False, "needs_review": True}
    except Exception as e:
        log.warning("payment apply failed session_id=%s quotation_id=%s exc=%s: %s",
                    session_id, txn.get("quotation_id"), type(e).__name__, e)
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"applied": False, "apply_error": f"{type(e).__name__}: {e}"[:300], "apply_error_at": now_iso()}})
        return {"applied": False, "credited": False, "error": str(e)}
    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {"applied": True, "applied_at": now_iso()}, "$unset": {"apply_error": "", "apply_error_at": ""}})
    return {"applied": True, "credited": credited}


async def verify_session(db, txn: dict, api_key: str, source: str) -> dict:
    """Consulta Stripe para una transacción y actúa según la regla única."""
    sid, qid = txn["session_id"], txn.get("quotation_id")
    out = {"session_id": sid, "local_status": txn.get("payment_status"), "amount": txn.get("amount"),
           "base_amount": txn.get("base_amount", txn.get("amount")), "card_fee_amount": txn.get("card_fee_amount", 0)}
    try:
        st = await stripe_get_status(api_key, sid)
    except Exception as e:
        log.warning("stripe get_checkout_status failed source=%s session_id=%s quotation_id=%s key_type=%s exc=%s: %s",
                    source, sid, qid, key_type(api_key), type(e).__name__, e)
        reason = readable_error(e)
        if txn.get("payment_status") != "paid":
            await db.payment_transactions.update_one(
                {"session_id": sid},
                {"$set": {"verification_state": "error", "last_error": reason, "last_error_at": now_iso()}})
        return {**out, "outcome": "verification_error", "stripe_status": None, "error": reason}
    outcome = classify(st)
    out.update({"stripe_status": getattr(st, "status", None), "stripe_payment_status": getattr(st, "payment_status", None)})
    base_set = {"stripe_status": out["stripe_status"], "stripe_payment_status": out["stripe_payment_status"],
                "last_checked_at": now_iso(), "verification_state": outcome}
    if outcome == "paid":
        await db.payment_transactions.update_one(
            {"session_id": sid, "payment_status": {"$ne": "paid"}},
            {"$set": {**base_set, "payment_status": "paid", "status": out["stripe_status"] or "complete",
                      "paid_at": now_iso(), "applied": False}})
        res = await apply_pending_credit(db, sid)
        out.update(res)
    elif txn.get("payment_status") != "paid":
        extra = {"payment_status": "expired", "status": "expired"} if outcome == "expired" else \
                {"payment_status": "processing", "status": "complete"} if outcome == "processing" else {}
        await db.payment_transactions.update_one(
            {"session_id": sid, "payment_status": {"$ne": "paid"}},
            {"$set": {**base_set, **extra}, "$unset": {"last_error": "", "last_error_at": ""}})
    out["outcome"] = outcome
    fresh = await db.payment_transactions.find_one({"session_id": sid}, {"_id": 0, "applied": 1, "payment_status": 1, "review_state": 1})
    out["applied"] = bool((fresh or {}).get("applied"))
    out["review_state"] = (fresh or {}).get("review_state")
    if outcome == "paid" and out["review_state"] == "needs_review":
        out["outcome"] = outcome = "needs_review"
    out["local_status"] = (fresh or {}).get("payment_status")
    return out


async def reconcile_quotation(db, quotation_id: str, company: dict, source: str = "reconcile") -> list:
    """1) reintenta paid/applied!=true; 2) verifica en Stripe las no finalizadas."""
    results = []
    async for t in db.payment_transactions.find(
            {"quotation_id": quotation_id, "payment_status": "paid", "applied": False,
             "review_state": {"$ne": "needs_review"}}, {"_id": 0, "session_id": 1}):
        results.append({"session_id": t["session_id"], "outcome": "paid", **(await apply_pending_credit(db, t["session_id"]))})
    api_key = resolve_stripe_key(company)
    if not api_key:
        return results
    pend = await db.payment_transactions.find({"quotation_id": quotation_id, "payment_status": UNRESOLVED}, {"_id": 0}).sort("created_at", -1).to_list(10)
    for t in pend:
        results.append(await verify_session(db, t, api_key, source))
    return results


async def unresolved_state(db, quotation_id: str) -> dict | None:
    """Transacción más reciente que impide volver a cobrar: paid sin aplicar, en proceso o sin verificar."""
    t = await db.payment_transactions.find_one(
        {"quotation_id": quotation_id, "$or": [
            {"review_state": "needs_review", "applied": False},
            {"payment_status": "paid", "applied": False},
            {"payment_status": "processing"},
            {"payment_status": UNRESOLVED, "verification_state": "error"},
        ]}, {"_id": 0}, sort=[("created_at", -1)])
    if not t:
        return None
    if t.get("review_state") == "needs_review" and not t.get("applied"):
        state = "needs_review"
    elif t.get("payment_status") == "paid":
        state = "registering"
    elif t.get("payment_status") == "processing":
        state = "processing"
    else:
        state = "verification_error"
    return {"state": state, "session_id": t["session_id"]}


async def migrate_applied_flag(db) -> int:
    """Migración segura (idempotente): transacciones paid sin `applied`."""
    changed = 0
    qids = await db.payment_transactions.distinct("quotation_id", {"payment_status": "paid", "applied": {"$exists": False}})
    for qid in qids:
        txns = await db.payment_transactions.find({"quotation_id": qid, "payment_status": "paid"}, {"_id": 0}).sort("paid_at", 1).to_list(None)
        legacy = [t for t in txns if "applied" not in t]
        q = await db.quotations.find_one({"id": qid}, {"_id": 0, "amount_paid": 1, "payment_status": 1})
        paid_sum = sum(round(float(t.get("base_amount", t["amount"])), 2) for t in txns if t.get("applied") is not False)
        amount_paid = float((q or {}).get("amount_paid", 0) or 0)
        unapplied = []
        if q and q.get("payment_status") != "paid" and amount_paid + 0.01 < paid_sum:
            deficit = paid_sum - amount_paid
            for t in reversed(legacy):  # las más recientes son las que faltan
                if deficit <= 0.01:
                    break
                unapplied.append(t["session_id"])
                deficit -= round(float(t.get("base_amount", t["amount"])), 2)
        for t in legacy:
            ok = t["session_id"] not in unapplied
            await db.payment_transactions.update_one({"session_id": t["session_id"]}, {"$set": {"applied": ok, "migrated_applied": True}})
            if ok and q:
                await db.quotations.update_one({"id": qid}, {"$addToSet": {"credited_sessions": t["session_id"]}})
            changed += 1
    if changed:
        log.warning("payments migration: %d legacy paid transactions flagged (applied)", changed)
    return changed


async def reconcile_manually(db, txn: dict, user: dict, reason: str = "") -> dict:
    """Cierra una transacción sin sumar nada (el pago ya se registró a mano). Solo admins."""
    sid, qid = txn["session_id"], txn["quotation_id"]
    info = {"by_id": user.get("id"), "by_name": user.get("name") or user.get("email", ""), "at": now_iso(), "reason": (reason or "").strip()[:300]}
    sets = {"applied": True, "review_state": "manual", "reconciled_manually": info}
    if txn.get("payment_status") != "paid":
        sets["payment_status"] = "reconciled"
    await db.payment_transactions.update_one({"session_id": sid}, {"$set": sets})
    await db.quotations.update_one({"id": qid}, {"$addToSet": {"credited_sessions": sid}})
    still = await db.payment_transactions.count_documents({"quotation_id": qid, "review_state": "needs_review", "applied": False})
    await db.quotations.update_one({"id": qid}, {"$set": {"payment_review": still > 0}})
    q = await db.quotations.find_one({"id": qid}, {"_id": 0})
    try:
        from deps import _record_audit
        detail = f"Transacción {sid} conciliada manualmente (sin sumar monto)" + (f". Motivo: {info['reason']}" if info["reason"] else "")
        await _record_audit(db, q["tenant_id"], user, "payment_reconciled", q, detail)
    except Exception:
        log.exception("audit payment_reconciled failed")
    return info
