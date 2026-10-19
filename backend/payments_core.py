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
import logging
import os

from pymongo import ReturnDocument

from database import now_iso
import notifications

log = logging.getLogger("routiq")

UNRESOLVED = {"$nin": ["paid", "expired", "failed"]}


def resolve_stripe_key(company: dict) -> str:
    sk = ((company or {}).get("stripe") or {}).get("secret_key")
    return sk or os.environ.get("STRIPE_API_KEY", "")


def key_type(api_key: str) -> str:
    return (api_key or "")[:3] or "none"


def _checkout(api_key: str):
    from emergentintegrations.payments.stripe.checkout import StripeCheckout
    return StripeCheckout(api_key=api_key, webhook_url="")


async def stripe_get_status(api_key: str, session_id: str):
    """Consulta la sesión en Stripe (punto único, fácil de simular en pruebas)."""
    return await _checkout(api_key).get_checkout_status(session_id)


async def stripe_expire_session(api_key: str, session_id: str) -> bool:
    import stripe
    _checkout(api_key)  # fija api_key / api_base del SDK
    stripe.checkout.Session.expire(session_id)
    return True


async def stripe_session_url(api_key: str, session_id: str) -> str:
    import stripe
    _checkout(api_key)
    return getattr(stripe.checkout.Session.retrieve(session_id), "url", "") or ""


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


async def apply_payment_to_quotation(db, txn: dict) -> bool:
    """Acredita base_amount (sin comisión bancaria) una sola vez por session_id. True si acreditó."""
    sid = txn["session_id"]
    credit = round(float(txn.get("base_amount", txn["amount"])), 2)
    q = await db.quotations.find_one_and_update(
        {"id": txn["quotation_id"], "credited_sessions": {"$ne": sid}},
        {"$inc": {"amount_paid": credit}, "$addToSet": {"credited_sessions": sid},
         "$set": {"last_activity_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if q is None:
        if not await db.quotations.find_one({"id": txn["quotation_id"]}, {"_id": 0, "id": 1}):
            raise RuntimeError(f"cotización {txn['quotation_id']} no encontrada")
        return False  # ya acreditada antes
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
    try:
        credited = await apply_payment_to_quotation(db, txn)
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
    fresh = await db.payment_transactions.find_one({"session_id": sid}, {"_id": 0, "applied": 1, "payment_status": 1})
    out["applied"] = bool((fresh or {}).get("applied"))
    out["local_status"] = (fresh or {}).get("payment_status")
    return out


async def reconcile_quotation(db, quotation_id: str, company: dict, source: str = "reconcile") -> list:
    """1) reintenta paid/applied!=true; 2) verifica en Stripe las no finalizadas."""
    results = []
    async for t in db.payment_transactions.find(
            {"quotation_id": quotation_id, "payment_status": "paid", "applied": False}, {"_id": 0, "session_id": 1}):
        results.append({"session_id": t["session_id"], "outcome": "paid", **(await apply_pending_credit(db, t["session_id"]))})
    api_key = resolve_stripe_key(company)
    if not api_key:
        return results
    pend = await db.payment_transactions.find({"quotation_id": quotation_id, "payment_status": UNRESOLVED}, {"_id": 0}).to_list(50)
    for t in pend:
        results.append(await verify_session(db, t, api_key, source))
    return results


async def unresolved_state(db, quotation_id: str) -> dict | None:
    """Transacción más reciente que impide volver a cobrar: paid sin aplicar, en proceso o sin verificar."""
    t = await db.payment_transactions.find_one(
        {"quotation_id": quotation_id, "$or": [
            {"payment_status": "paid", "applied": False},
            {"payment_status": "processing"},
            {"payment_status": UNRESOLVED, "verification_state": "error"},
        ]}, {"_id": 0}, sort=[("created_at", -1)])
    if not t:
        return None
    if t.get("payment_status") == "paid":
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
