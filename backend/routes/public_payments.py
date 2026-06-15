"""Public quotation + payments: client-facing view, accept, bank transfer,
manual mark-paid, send-to-charge, Stripe checkout/status/webhook."""
import os
import secrets
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request

from database import get_db, new_id, now_iso
from auth import require_tenant
from models import PublicCheckoutRequest, ManualPaymentInput, SendPaymentInput
import currency
import notifications
from deps import (
    _append_history, _record_audit, _client_email, _bank_html,
    _resolve_stripe_key, _apply_payment_to_quotation,
)
from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionRequest

log = logging.getLogger("routiq")
router = APIRouter()


@router.get("/public/quotations/{token}")
async def get_public_quotation(token: str):
    db = get_db()
    q = await db.quotations.find_one({"public_link.token": token}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Enlace inválido")
    expires = q.get("public_link", {}).get("expires_at")
    if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Enlace expirado")
    company = await db.companies.find_one({"id": q["tenant_id"]}, {"_id": 0, "pricing_config": 0})
    pack = None
    if q.get("package_id"):
        pack = await db.packages.find_one({"id": q["package_id"]}, {"_id": 0})
    base_currency = company.get("base_currency", q.get("currency", "MXN"))
    final_total = q.get("final_total")
    if final_total is None:
        final_total = q.get("total", 0)
    amount_paid = q.get("amount_paid", 0) or 0
    stripe_allowed = bool(company.get("stripe_allowed", True))
    transfer_allowed = bool(company.get("transfer_allowed", True))
    payment_enabled = stripe_allowed and bool(((company.get("stripe") or {}).get("secret_key")) or os.environ.get("STRIPE_API_KEY"))
    bank = company.get("bank") or {}
    transfer_enabled = transfer_allowed and bool(bank.get("enabled")) and any(
        bank.get(k) for k in ("name", "clabe", "account", "usd_account"))
    rates = await currency.get_rates()
    total_usd = currency.convert(final_total, base_currency, "USD", rates) if base_currency == "MXN" else None
    return {
        "quotation": {
            "code": q["code"], "type": q.get("type", "paquete"),
            "package_snapshot": q.get("package_snapshot"),
            "hotel_selected": q.get("hotel_selected", ""), "dates": q["dates"], "pax": q["pax"],
            "items": q["items"], "subtotal": q["subtotal"], "commission": q.get("commission", 0),
            "total": q["total"], "currency": q.get("currency", "MXN"), "state": q["state"],
            "nights_total": q.get("nights_total"), "extra_nights": q.get("extra_nights", 0),
            "package_nights": (q.get("package_snapshot") or {}).get("nights"),
            "discount": q.get("discount"),
            "final_total": round(final_total, 2),
            "amount_paid": round(amount_paid, 2),
            "amount_due": round(max(0.0, final_total - amount_paid), 2),
            "payment_status": q.get("payment_status", "unpaid"),
            "client_name": q.get("client_snapshot", {}).get("name", ""),
            "accepted_at": q.get("public_link", {}).get("accepted_at"),
        },
        "company": {
            "name": company.get("name", ""), "logo_url": company.get("logo_url", ""),
            "primary_color": company.get("primary_color", "#185FA5"),
            "contact_email": company.get("contact_email", ""),
            "contact_phone": company.get("contact_phone", ""),
        },
        "payment": {
            "enabled": payment_enabled,
            "transfer_enabled": transfer_enabled,
            "base_currency": base_currency,
            "deposit_percent": company.get("deposit_percent", 50),
            "total_usd_equivalent": total_usd,
            "rate_mxn_per_usd": rates.get("mxn_per_usd"),
            "bank": {
                "name": bank.get("name", ""), "holder": bank.get("holder", ""),
                "clabe": bank.get("clabe", ""), "account": bank.get("account", ""),
                "usd_account": bank.get("usd_account", ""), "swift": bank.get("swift", ""),
                "aba": bank.get("aba", ""), "address": bank.get("address", ""),
            } if transfer_enabled else None,
        },
        "itinerary": (pack or {}).get("itinerary", []),
        "includes": (pack or {}).get("includes", []),
        "excludes": (pack or {}).get("excludes", []),
        "package_image_url": (pack or {}).get("image_url", ""),
        "season_applied": q.get("season_applied"),
    }


@router.post("/public/quotations/{token}/accept")
async def accept_public_quotation(token: str, request: Request):
    db = get_db()
    q = await db.quotations.find_one({"public_link.token": token}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Enlace inválido")
    expires = q.get("public_link", {}).get("expires_at")
    if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Enlace expirado")
    accepted_at = now_iso()
    was_won = q.get("state") == "ganada"
    set_fields = {
        "state": "ganada",
        "public_link.accepted_at": accepted_at,
        "last_activity_at": accepted_at,
    }
    origin = request.headers.get("origin") or request.headers.get("referer")
    if origin:
        # store the public base url so the 48h reminder can build a pay link
        base = origin.split("/q/")[0].rstrip("/")
        set_fields["public_link.base_url"] = base
    await db.quotations.update_one({"id": q["id"]}, {"$set": set_fields})
    try:
        await _append_history(db, q["id"], {"id": None, "name": "Cliente (enlace público)"},
                              "accepted", "El cliente aceptó la cotización desde el enlace público")
        if not was_won:
            await _record_audit(db, q["tenant_id"], {"id": None, "name": "Cliente (enlace público)"},
                                "won", q, "Aceptada por el cliente (enlace público)")
    except Exception:
        log.exception("audit accept failed")
    try:
        q["final_total"] = q.get("final_total", q.get("total"))
        await notifications.notify_acceptance(db, q)
    except Exception:
        log.exception("acceptance notification failed")
    return {"ok": True, "accepted_at": accepted_at}


@router.post("/public/quotations/{token}/request-transfer")
async def request_bank_transfer(token: str):
    """Client chose bank transfer: email them the bank details (best-effort)."""
    db = get_db()
    q = await db.quotations.find_one({"public_link.token": token}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Enlace inválido")
    company = await db.companies.find_one({"id": q["tenant_id"]}, {"_id": 0})
    bank = company.get("bank") or {}
    if not bank.get("enabled"):
        raise HTTPException(status_code=400, detail="La transferencia bancaria no está habilitada")
    final_total = q.get("final_total")
    if final_total is None:
        final_total = q.get("total", 0)
    amount_due = round(max(0.0, final_total - (q.get("amount_paid", 0) or 0)), 2)
    to = await _client_email(db, q)
    sent = False
    if to:
        title = f"Datos para transferencia — {q.get('code')}"
        html = f"<h2>Datos bancarios de {company.get('name','')}</h2>" + _bank_html(bank, q.get("currency", "MXN"), amount_due)
        sent = await notifications.send_email(company, to, title, html)
    try:
        await _append_history(db, q["id"], {"id": None, "name": "Cliente (enlace público)"},
                              "transfer_requested", "El cliente solicitó pagar por transferencia bancaria")
    except Exception:
        log.exception("transfer history failed")
    return {"ok": True, "email_sent": sent, "to": to, "bank": {k: bank.get(k, "") for k in ("name", "holder", "clabe", "account", "usd_account", "swift", "aba", "address")}}


@router.patch("/quotations/{quotation_id}/mark-paid")
async def mark_quotation_paid(quotation_id: str, payload: ManualPaymentInput, user: dict = Depends(require_tenant)):
    """Executive manually registers a received payment (e.g. bank transfer)."""
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    final_total = q.get("final_total")
    if final_total is None:
        final_total = q.get("total", 0)
    remaining = round(max(0.0, final_total - (q.get("amount_paid", 0) or 0)), 2)
    if float(payload.amount) > remaining + 0.01:
        raise HTTPException(status_code=400, detail=f"El monto excede lo pendiente ({q.get('currency','MXN')} ${remaining:,.2f})")
    amount_paid = round((q.get("amount_paid", 0) or 0) + float(payload.amount), 2)
    pay_status = "paid" if amount_paid >= round(final_total, 2) - 0.01 else "partial"
    was_won = q.get("state") == "ganada"
    updates = {"amount_paid": amount_paid, "payment_status": pay_status, "last_activity_at": now_iso()}
    if not was_won:
        updates["state"] = "ganada"
    await db.quotations.update_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"$set": updates})
    METHOD_ES = {"transfer": "transferencia", "cash": "efectivo", "card": "tarjeta", "other": "otro"}
    detail = f"Pago manual de {q.get('currency','MXN')} ${float(payload.amount):,.2f} ({METHOD_ES.get(payload.method, payload.method)})"
    if payload.note:
        detail += f" — {payload.note}"
    await _append_history(db, quotation_id, user, "payment", detail)
    if not was_won:
        await _record_audit(db, user["tenant_id"], user, "won", q, f"Ganada por {detail}")
    try:
        q2 = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
        txn = {"amount": float(payload.amount), "currency": q.get("currency", "MXN")}
        await notifications.notify_payment(db, q2, txn, amount_paid, pay_status)
    except Exception:
        log.exception("manual payment notification failed")
    return await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})


@router.post("/quotations/{quotation_id}/send-payment")
async def send_payment_link(quotation_id: str, payload: SendPaymentInput, user: dict = Depends(require_tenant)):
    """Email the client the public payment link (Stripe + transfer options)."""
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    public = q.get("public_link")
    if not public or not public.get("token"):
        token = secrets.token_urlsafe(18)
        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        public = {"token": token, "expires_at": expires_at, "created_at": now_iso(), "accepted_at": None}
        await db.quotations.update_one({"id": quotation_id}, {"$set": {"public_link": public}})
    base = (payload.public_url or "").rstrip("/")
    link = f"{base}/q/{public['token']}" if base else f"/q/{public['token']}"
    if base:
        await db.quotations.update_one({"id": quotation_id}, {"$set": {"public_link.base_url": base}})
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    to = payload.to_email or await _client_email(db, q)
    if not to:
        raise HTTPException(status_code=400, detail="No hay correo del cliente. Agrega uno en el cliente o en los contactos.")
    final_total = q.get("final_total")
    if final_total is None:
        final_total = q.get("total", 0)
    title = f"Tu cotización {q.get('code')} — opciones de pago"
    html = (f"<h2>{company.get('name','')}</h2><p>Hola {q.get('client_snapshot',{}).get('name','')}, "
            f"aquí tienes tu cotización por <b>${float(final_total):,.2f} {q.get('currency','MXN')}</b>.</p>"
            f"<p style='margin:22px 0'><a href='{link}' style='background:#185FA5;color:#fff;padding:14px 26px;border-radius:10px;text-decoration:none;font-weight:600;display:inline-block'>Pagar ahora</a></p>"
            f"<p style='color:#64748b;font-size:12px'>Podrás pagar con tarjeta o por transferencia bancaria.</p>")
    sent = await notifications.send_email(company, to, title, html)
    await _append_history(db, quotation_id, user, "sent_payment", f"Enlace de cobro enviado por correo a {to}")
    return {"ok": True, "email_sent": sent, "to": to, "link": link}


@router.post("/public/quotations/{token}/checkout")
async def public_checkout(token: str, payload: PublicCheckoutRequest, request: Request):
    db = get_db()
    q = await db.quotations.find_one({"public_link.token": token}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Enlace inválido")
    expires = q.get("public_link", {}).get("expires_at")
    if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Enlace expirado")
    company = await db.companies.find_one({"id": q["tenant_id"]}, {"_id": 0})
    if not bool(company.get("stripe_allowed", True)):
        raise HTTPException(status_code=403, detail="El pago con tarjeta no está habilitado para esta empresa")
    api_key = _resolve_stripe_key(company)
    if not api_key:
        raise HTTPException(status_code=400, detail="Pagos no configurados para esta empresa")

    final_total = q.get("final_total")
    if final_total is None:
        final_total = q.get("total", 0)
    amount_paid = q.get("amount_paid", 0) or 0
    amount_due = round(max(0.0, final_total - amount_paid), 2)
    if amount_due <= 0:
        raise HTTPException(status_code=400, detail="Esta cotización ya está pagada")

    if payload.pay_type == "deposit":
        deposit_pct = float(company.get("deposit_percent", 50) or 50)
        amount = round(final_total * deposit_pct / 100.0, 2)
        amount = min(amount, amount_due)
    else:
        amount = amount_due
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Monto inválido")

    base_currency = (company.get("base_currency") or q.get("currency", "MXN")).lower()
    origin = payload.origin_url.rstrip("/")
    await db.quotations.update_one({"id": q["id"]}, {"$set": {"public_link.base_url": origin}})
    webhook_url = f"{origin}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=api_key, webhook_url=webhook_url)
    success_url = f"{origin}/q/{token}?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/q/{token}"
    metadata = {
        "quotation_id": q["id"], "tenant_id": q["tenant_id"],
        "token": token, "pay_type": payload.pay_type, "code": q.get("code", ""),
    }
    req = CheckoutSessionRequest(
        amount=float(amount), currency=base_currency,
        success_url=success_url, cancel_url=cancel_url, metadata=metadata,
    )
    session = await stripe_checkout.create_checkout_session(req)
    await db.payment_transactions.insert_one({
        "id": new_id(), "session_id": session.session_id,
        "quotation_id": q["id"], "tenant_id": q["tenant_id"],
        "amount": float(amount), "currency": base_currency.upper(),
        "pay_type": payload.pay_type, "metadata": metadata,
        "status": "initiated", "payment_status": "pending",
        "created_at": now_iso(),
    })
    return {"url": session.url, "session_id": session.session_id}


@router.get("/public/quotations/{token}/payment-status/{session_id}")
async def public_payment_status(token: str, session_id: str, request: Request):
    db = get_db()
    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not txn:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    company = await db.companies.find_one({"id": txn["tenant_id"]}, {"_id": 0})
    api_key = _resolve_stripe_key(company)
    stripe_status = None
    try:
        stripe_checkout = StripeCheckout(api_key=api_key, webhook_url="")
        st = await stripe_checkout.get_checkout_status(session_id)
        stripe_status = st
        if st.payment_status == "paid":
            flipped = await db.payment_transactions.find_one_and_update(
                {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                {"$set": {"payment_status": "paid", "status": st.status, "paid_at": now_iso()}},
            )
            if flipped is not None:
                await _apply_payment_to_quotation(flipped)
    except Exception as e:
        log.info("payment-status: get_checkout_status fallback to local txn (%s): %s", session_id, e)

    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if stripe_status is not None:
        return {
            "payment_status": stripe_status.payment_status,
            "status": stripe_status.status,
            "amount_total": stripe_status.amount_total,
            "currency": stripe_status.currency,
        }
    is_paid = txn.get("payment_status") == "paid"
    return {
        "payment_status": "paid" if is_paid else "pending",
        "status": txn.get("status", "open"),
        "amount_total": int(round(float(txn["amount"]) * 100)),
        "currency": txn.get("currency", "MXN").lower(),
        "source": "local",
    }


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    db = get_db()
    body = await request.body()
    sig = request.headers.get("Stripe-Signature")
    try:
        stripe_checkout = StripeCheckout(api_key=os.environ.get("STRIPE_API_KEY", ""), webhook_url="")
        event = await stripe_checkout.handle_webhook(body, sig)
        if event.payment_status == "paid":
            flipped = await db.payment_transactions.find_one_and_update(
                {"session_id": event.session_id, "payment_status": {"$ne": "paid"}},
                {"$set": {"payment_status": "paid", "status": "complete", "paid_at": now_iso()}},
            )
            if flipped is not None:
                await _apply_payment_to_quotation(flipped)
    except Exception as e:
        log.warning("stripe webhook error: %s", e)
    return {"ok": True}
