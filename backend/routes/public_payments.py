"""Public quotation + payments: client-facing view, accept, bank transfer,
manual mark-paid, send-to-charge, Stripe checkout/status/webhook."""
import os
import secrets
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from database import get_db, new_id, now_iso
from auth import require_tenant
import currency
import notifications
from deps import (
    _append_history, _record_audit, _client_email, _bank_html,
    _resolve_stripe_key, _reconcile_quotation_payments,
    _resolve_client_email,
)
from models import PublicCheckoutRequest, ManualPaymentInput, SendPaymentInput, QuotationPaymentConfig
from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionRequest
import payments_core
from pydantic import BaseModel

log = logging.getLogger("routiq")
from pricing_breakdown import build_per_person_breakdown


def _public_breakdown(q: dict):
    """Desglose por persona para el cliente: sin composición interna ni ajustes."""
    bd = build_per_person_breakdown(q)
    if not bd:
        return None
    rows = [{k: v for k, v in r.items() if k != "components"} for r in bd["rows"]]
    return {"rows": rows, "total": bd["total"], "total_pax": bd["total_pax"], "currency": bd["currency"], "note": bd["note"]}

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
    company = await db.companies.find_one({"id": q["tenant_id"]}, {"_id": 0})
    # P0 anti-doble-cobro: reconciliar pagos en vuelo con Stripe antes de mostrar montos.
    try:
        await _reconcile_quotation_payments(db, q["id"], company or {}, source="public-link")
        q = await db.quotations.find_one({"public_link.token": token}, {"_id": 0}) or q
    except Exception as e:
        log.warning("public-link reconcile failed quotation_id=%s exc=%s: %s", q.get("id"), type(e).__name__, e)
    unresolved = await payments_core.unresolved_state(db, q["id"])
    last_txn = await db.payment_transactions.find_one(
        {"quotation_id": q["id"], "payment_status": {"$nin": ["expired", "failed"]}},
        {"_id": 0, "session_id": 1}, sort=[("created_at", -1)])
    pack = None
    if q.get("package_id"):
        pack = await db.packages.find_one({"id": q["package_id"]}, {"_id": 0})
    if q.get("type") == "personalizado":
        pack = {
            "itinerary": q.get("custom_itinerary", []),
            "includes": q.get("custom_includes", []),
            "excludes": q.get("custom_excludes", []),
            "image_url": "",
        }
    # Tabla de precios por ocupación (paquetes) — réplica de lo que muestra el PDF.
    occupancy_prices = []
    if q.get("type") == "paquete" and pack and q.get("hotel_selected"):
        sel = next((h for h in (pack.get("hotels") or []) if h.get("name") == q.get("hotel_selected")), None)
        if sel:
            from pricing import occupancy_rows_selected, occupancy_rows_all
            pcfg = company.get("pricing_config") or {}
            divisor = float(pcfg.get("margin_divisor", 0.76) or 0.76)
            commissions = pcfg.get("commissions", {}) or {}
            channel = q.get("client_snapshot", {}).get("channel", "directo")
            if q.get("show_all_occupancies"):
                rows = occupancy_rows_all(sel, channel, divisor, commissions)
                occupancy_prices = [{"key": str(i), "occ": r.get("key"), "label": r["label"], "price": r["per_person"], "total": r.get("total")}
                                    for i, r in enumerate(rows)]
    exec_name = ""
    if q.get("assigned_to"):
        exec_user = await db.users.find_one({"id": q["assigned_to"]}, {"_id": 0, "name": 1})
        exec_name = (exec_user or {}).get("name", "")
    base_currency = company.get("base_currency", q.get("currency", "MXN"))
    final_total = q.get("final_total")
    if final_total is None:
        final_total = q.get("total", 0)
    amount_paid = q.get("amount_paid", 0) or 0
    stripe_allowed = bool(company.get("stripe_allowed", True))
    transfer_allowed = bool(company.get("transfer_allowed", True))
    stripe_ready = stripe_allowed and bool(((company.get("stripe") or {}).get("secret_key")) or os.environ.get("STRIPE_API_KEY"))
    # Gating por etapas (Iter 4 punto 1): el pago con tarjeta solo aparece si el ejecutivo lo habilitó.
    payment_enabled = stripe_ready and bool(q.get("payment_enabled"))
    allowed_pay_type = q.get("allowed_pay_type", "full")
    amount_due = round(max(0.0, final_total - amount_paid), 2)
    # Comisión bancaria (Iter 4 punto 2): recargo SOLO en tarjeta (Stripe), no en transferencia.
    card_fee_enabled = bool(q.get("card_fee_enabled"))
    card_fee_percent = float(q.get("card_fee_percent", company.get("card_fee_percent", 4.5)) or 0)
    card_fee_amount = round(amount_due * card_fee_percent / 100.0, 2) if (card_fee_enabled and amount_due > 0) else 0.0
    bank = company.get("bank") or {}
    transfer_enabled = transfer_allowed and bool(bank.get("enabled")) and any(
        bank.get(k) for k in ("name", "clabe", "account", "usd_account"))
    rates = await currency.get_rates()
    other_ccy = "USD" if base_currency == "MXN" else "MXN"
    equivalent_amount = currency.convert(final_total, base_currency, other_ccy, rates) if base_currency != other_ccy else None
    total_usd = equivalent_amount if other_ccy == "USD" else None
    q["final_total"] = round(final_total, 2)
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
            "presentation_text": q.get("presentation_text", ""),
            "important_info": q.get("important_info", ""),
            "price_note": q.get("price_note", ""),
            "exec_name": exec_name,
            "occupancy_prices": occupancy_prices,
            "show_price_breakdown": q.get("show_price_breakdown", True),
            "show_per_person": bool(q.get("show_per_person")),
            "per_person_breakdown": _public_breakdown(q) if q.get("show_per_person") else None,
            "contacts": q.get("contacts") or None,
        },
        "company": {
            "name": company.get("name", ""), "logo_url": company.get("logo_url", ""),
            "slug": company.get("slug", ""),
            "primary_color": company.get("primary_color", "#185FA5"),
            "contact_email": company.get("contact_email", ""),
            "contact_phone": company.get("contact_phone", ""),
        },
        "payment": {
            "enabled": payment_enabled,
            "allowed_pay_type": allowed_pay_type,
            "transfer_enabled": transfer_enabled,
            "base_currency": base_currency,
            "deposit_percent": company.get("deposit_percent", 50),
            "card_fee_enabled": card_fee_enabled,
            "card_fee_percent": card_fee_percent,
            "card_fee_amount": card_fee_amount,
            "total_usd_equivalent": total_usd,
            "equivalent_amount": equivalent_amount,
            "equivalent_currency": other_ccy,
            # Iter 69: transacción sin resolver (en proceso / sin verificar / registrando) -> no mostrar "Pagar".
            "unresolved": unresolved,
            "last_session_id": (last_txn or {}).get("session_id"),
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
        "cancellation_policy": company.get("cancellation_policy", ""),
    }


@router.get("/public/quotations/{token}/pdf")
async def public_quotation_pdf(token: str, request: Request):
    """PDF de la cotización descargable desde el enlace público (precios públicos,
    idéntico al que ve el ejecutivo; nunca expone tarifas netas confidenciales)."""
    import io as _io
    from fastapi.responses import StreamingResponse
    from pdf_generator import generate_quotation_pdf
    db = get_db()
    q = await db.quotations.find_one({"public_link.token": token}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Enlace inválido")
    expires = q.get("public_link", {}).get("expires_at")
    if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Enlace expirado")
    company = await db.companies.find_one({"id": q["tenant_id"]}, {"_id": 0})
    pack = None
    if q.get("package_id"):
        pack = await db.packages.find_one({"id": q["package_id"]}, {"_id": 0})
    if q.get("type") == "personalizado":
        pack = {
            "name": q.get("custom_title") or "Programa personalizado",
            "description": "",
            "nights": q.get("nights_total"),
            "itinerary": q.get("custom_itinerary", []),
            "includes": q.get("custom_includes", []),
            "excludes": q.get("custom_excludes", []),
        }
    client = await db.clients.find_one({"id": q.get("client_id")}, {"_id": 0})
    exec_name = ""
    if q.get("assigned_to"):
        exec_user = await db.users.find_one({"id": q["assigned_to"]}, {"_id": 0, "name": 1})
        exec_name = (exec_user or {}).get("name", "")
    base_url = f"{request.url.scheme}://{request.headers.get('host', '')}"
    pdf = generate_quotation_pdf(company or {}, q, pack or {},
                                 client or {"name": q.get("client_snapshot", {}).get("name", "")},
                                 exec_name=exec_name, base_url=base_url)
    return StreamingResponse(_io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{q["code"]}.pdf"'})


def _esc(s: str) -> str:
    """Minimal HTML attribute escaping for OG meta values."""
    return (str(s or "").replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


@router.get("/share/q/{token}", response_class=HTMLResponse)
async def share_quotation(token: str, request: Request):
    """Bot-friendly share page with per-tenant Open Graph tags (WhatsApp/FB preview),
    then redirects real browsers to the SPA quotation page /q/{token}."""
    db = get_db()
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    base = f"{proto}://{host}"
    spa_url = f"{base}/q/{token}"

    q = await db.quotations.find_one({"public_link.token": token}, {"_id": 0})
    title = "Tu cotización de viaje"
    desc = "Revisa los detalles, confirma y reserva en línea."
    image = ""
    if q:
        company = await db.companies.find_one({"id": q["tenant_id"]}, {"_id": 0}) or {}
        cname = company.get("name") or "Routiq"
        client = (q.get("client_snapshot") or {}).get("name") or "viajero"
        pkg = (q.get("package_snapshot") or {}).get("name") or q.get("custom_title") or ""
        title = f"{cname} · Cotización {q.get('code', '')}".strip()
        desc = (f"Hola {client}, tu cotización" + (f' de "{pkg}"' if pkg else "") +
                " está lista. Ábrela para ver el itinerario, el total y reservar en línea.")
        logo = company.get("logo_url") or ""
        if logo.startswith("/"):
            image = base + logo
        elif logo.startswith("http"):
            image = logo

    img_tags = (f'<meta property="og:image" content="{_esc(image)}"/>'
                f'<meta name="twitter:image" content="{_esc(image)}"/>') if image else ""
    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}"/>
<meta property="og:type" content="website"/>
<meta property="og:title" content="{_esc(title)}"/>
<meta property="og:description" content="{_esc(desc)}"/>
<meta property="og:url" content="{_esc(spa_url)}"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{_esc(title)}"/>
<meta name="twitter:description" content="{_esc(desc)}"/>
{img_tags}
<meta http-equiv="refresh" content="0; url={_esc(spa_url)}"/>
<script>window.location.replace({spa_url!r});</script>
</head><body>
<p>Redirigiendo a tu cotización… <a href="{_esc(spa_url)}">Abrir cotización</a></p>
</body></html>"""
    return HTMLResponse(content=html)


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
    pay_date = (payload.date or now_iso()[:10])
    was_won = q.get("state") == "ganada"
    updates = {"amount_paid": amount_paid, "payment_status": pay_status, "last_activity_at": now_iso(), "paid_at": pay_date}
    if not was_won:
        updates["state"] = "ganada"
    await db.quotations.update_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"$set": updates})
    METHOD_ES = {"transfer": "transferencia", "cash": "efectivo", "card": "tarjeta", "other": "otro"}
    detail = f"Pago manual de {q.get('currency','MXN')} ${float(payload.amount):,.2f} ({METHOD_ES.get(payload.method, payload.method)}) el {pay_date}"
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


@router.patch("/quotations/{quotation_id}/payment-config")
async def set_payment_config(quotation_id: str, payload: QuotationPaymentConfig, user: dict = Depends(require_tenant)):
    """El ejecutivo habilita el pago por etapas (anticipo O total) y opcionalmente la
    comisión bancaria (solo tarjeta). Iter 4 puntos 1 y 2."""
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    updates = {"last_activity_at": now_iso()}
    hist = []
    if payload.payment_enabled is not None:
        updates["payment_enabled"] = bool(payload.payment_enabled)
        hist.append("pago " + ("habilitado" if payload.payment_enabled else "deshabilitado"))
    if payload.allowed_pay_type is not None:
        updates["allowed_pay_type"] = payload.allowed_pay_type
        hist.append("tipo " + ("anticipo" if payload.allowed_pay_type == "deposit" else "total"))
    if payload.card_fee_enabled is not None:
        updates["card_fee_enabled"] = bool(payload.card_fee_enabled)
        hist.append("comisión bancaria " + ("activada" if payload.card_fee_enabled else "desactivada"))
    if payload.card_fee_percent is not None:
        updates["card_fee_percent"] = float(payload.card_fee_percent)
    await db.quotations.update_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"$set": updates})
    if hist:
        await _append_history(db, quotation_id, user, "payment_config", "Configuración de pago: " + ", ".join(hist))
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
    to = (payload.to_email or "").strip()
    if not to:
        cl = await db.clients.find_one({"id": q.get("client_id")}, {"_id": 0}) or {}
        to, err = _resolve_client_email(cl, q)
        if not to:
            raise HTTPException(status_code=400, detail=err or "No se pudo resolver el correo del destinatario.")
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

    # Gating por etapas (Iter 4 punto 1): el ejecutivo debe habilitar el pago.
    if not bool(q.get("payment_enabled")):
        raise HTTPException(status_code=403, detail="El pago aún no está habilitado. El ejecutivo lo activará cuando la reserva esté lista.")
    allowed = q.get("allowed_pay_type", "full")
    req_type = "deposit" if payload.pay_type == "deposit" else "full"
    if allowed != req_type:
        raise HTTPException(status_code=400, detail="Este método de pago no está habilitado para esta reserva.")

    # P0-B defensa en profundidad: reconciliar contra Stripe ANTES de crear un nuevo checkout,
    # para que regenerar el enlace no permita un segundo cobro de algo ya pagado.
    await _reconcile_quotation_payments(db, q["id"], company or {}, source="checkout")
    q = await db.quotations.find_one({"public_link.token": token}, {"_id": 0}) or q
    # Iter 69: no cobrar de nuevo si hay un pago en proceso, sin verificar o registrándose.
    unresolved = await payments_core.unresolved_state(db, q["id"])
    if unresolved:
        raise HTTPException(status_code=409, detail=_UNRESOLVED_MSG.get(unresolved["state"], "Hay un pago en curso.").format(code=q.get("code", "")))

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

    # Comisión bancaria (Iter 4 punto 2): recargo SOLO en pago con tarjeta (Stripe).
    base_amount = amount
    card_fee_amount = 0.0
    if bool(q.get("card_fee_enabled")):
        pct = float(q.get("card_fee_percent", company.get("card_fee_percent", 4.5)) or 0)
        card_fee_amount = round(base_amount * pct / 100.0, 2)
        amount = round(base_amount + card_fee_amount, 2)

    # Iter 69: candado por cotización -> dos clics seguidos no crean dos sesiones.
    lock_cutoff = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    my_lock = now_iso()
    locked = await db.quotations.find_one_and_update(
        {"id": q["id"], "$or": [{"checkout_lock_at": {"$exists": False}}, {"checkout_lock_at": None}, {"checkout_lock_at": {"$lt": lock_cutoff}}]},
        {"$set": {"checkout_lock_at": my_lock}})
    if locked is None:
        raise HTTPException(status_code=409, detail="Estamos preparando tu pago. Espera unos segundos e inténtalo de nuevo.")
    try:
        return await _create_or_reuse_checkout(db, q, company, api_key, token, payload, amount, base_amount, card_fee_amount)
    finally:
        await db.quotations.update_one({"id": q["id"], "checkout_lock_at": my_lock}, {"$set": {"checkout_lock_at": None}})


_UNRESOLVED_MSG = {
    "processing": "Tu banco está procesando el pago; se confirmará en cuanto se acredite. No vuelvas a pagar.",
    "registering": "Recibimos tu pago y lo estamos registrando. No vuelvas a pagar.",
    "needs_review": "Recibimos tu pago; tu ejecutivo lo está revisando. No vuelvas a pagar.",
    "verification_error": "No pudimos verificar tu pago en este momento. No vuelvas a pagar. Si ya se te hizo el cargo, avisa a tu ejecutivo con el folio {code}.",
}


async def _create_or_reuse_checkout(db, q, company, api_key, token, payload, amount, base_amount, card_fee_amount):
    # Sesiones previas abiertas: expirarlas en Stripe; si no se puede, reutilizar su URL.
    async for old in db.payment_transactions.find(
            {"quotation_id": q["id"], "payment_status": {"$nin": ["paid", "expired", "failed", "processing"]}}, {"_id": 0}):
        try:
            await payments_core.stripe_expire_session(api_key, old["session_id"])
            await db.payment_transactions.update_one(
                {"session_id": old["session_id"], "payment_status": {"$ne": "paid"}},
                {"$set": {"payment_status": "expired", "status": "expired", "expired_by": "new-checkout", "expired_at": now_iso()}})
        except Exception as e:
            log.warning("checkout: could not expire session_id=%s quotation_id=%s exc=%s: %s",
                        old["session_id"], q["id"], type(e).__name__, e)
            # Re-verificar: pudo haberse pagado/completado entre la reconciliación y el intento de expirar.
            r = await payments_core.verify_session(db, old, api_key, "checkout-expire")
            if r["outcome"] == "expired":
                continue
            if r["outcome"] in ("paid", "needs_review"):
                raise HTTPException(status_code=400, detail="Esta cotización ya tiene un pago registrado. Recarga la página.")
            if r["outcome"] in ("processing", "verification_error"):
                raise HTTPException(status_code=409, detail=_UNRESOLVED_MSG[r["outcome"]].format(code=q.get("code", "")))
            url = old.get("url") or ""
            if not url:
                try:
                    url = await payments_core.stripe_session_url(api_key, old["session_id"])
                except Exception as e2:
                    log.warning("checkout: could not retrieve url session_id=%s exc=%s: %s", old["session_id"], type(e2).__name__, e2)
            if url:
                return {"url": url, "session_id": old["session_id"], "reused": True}
            raise HTTPException(status_code=409, detail="Hay un pago anterior abierto que no pudimos cerrar. Intenta de nuevo en unos minutos o contacta a tu ejecutivo.")

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
        "amount": float(amount), "base_amount": float(base_amount),
        "card_fee_amount": float(card_fee_amount),
        "currency": base_currency.upper(),
        "pay_type": payload.pay_type, "metadata": metadata,
        "status": "initiated", "payment_status": "pending", "applied": False,
        "url": session.url or "",
        "created_at": now_iso(),
    })
    return {"url": session.url, "session_id": session.session_id}


@router.get("/public/quotations/{token}/payment-status/{session_id}")
async def public_payment_status(token: str, session_id: str, request: Request):
    """Iter 69: estado explícito — paid | processing | open | expired | registering | verification_error."""
    db = get_db()
    q = await db.quotations.find_one({"public_link.token": token}, {"_id": 0, "id": 1, "code": 1, "tenant_id": 1})
    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not q or not txn or txn.get("quotation_id") != q["id"]:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    company = await db.companies.find_one({"id": txn["tenant_id"]}, {"_id": 0}) or {}
    if txn.get("payment_status") == "reconciled":
        state = "paid"
    elif txn.get("payment_status") == "paid":
        res = await payments_core.apply_pending_credit(db, session_id) if txn.get("applied") is False else {"applied": True}
        state = "paid" if res.get("applied") else ("needs_review" if res.get("needs_review") else "registering")
    else:
        r = await payments_core.verify_session(db, txn, payments_core.resolve_stripe_key(company), "payment-status")
        state = r["outcome"]
        if state == "paid" and not r.get("applied"):
            state = "registering"
    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    return {
        "state": state,
        "payment_status": "paid" if state == "paid" else ("processing" if state == "processing" else "pending"),
        "status": txn.get("stripe_status") or txn.get("status", "open"),
        "amount_total": int(round(float(txn["amount"]) * 100)),
        "currency": txn.get("currency", "MXN").lower(),
        "code": q.get("code", ""),
    }


def _webhook_session_id(body: bytes):
    """Lee SOLO session_id / tenant_id del aviso (sin confiar en su contenido)."""
    import json
    try:
        ev = json.loads(body.decode("utf-8"))
    except Exception:
        return None, None, None
    obj = ((ev.get("data") or {}).get("object") or {})
    etype = ev.get("type", "")
    sid = obj.get("id") if etype.startswith("checkout.session.") else (obj.get("metadata") or {}).get("checkout_session_id")
    return sid, (obj.get("metadata") or {}).get("tenant_id"), etype


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Iter 69: el aviso nunca se usa como prueba de pago. Se verifica la sesión con la llave de
    la empresa dueña de NUESTRA transacción y se acredita el monto de nuestra transacción.
    Siempre responde 200 (los fallos quedan para el reconciliador)."""
    db = get_db()
    body = await request.body()
    try:
        sid, meta_tenant, etype = _webhook_session_id(body)
        if not sid:
            log.warning("stripe webhook: event without session_id (type=%s)", etype)
            return {"ok": True}
        txn = await db.payment_transactions.find_one({"session_id": sid}, {"_id": 0})
        if not txn:
            log.warning("stripe webhook: unknown session_id=%s type=%s tenant=%s — ignored", sid, etype, meta_tenant)
            return {"ok": True}
        if meta_tenant and meta_tenant != txn.get("tenant_id"):
            log.warning("stripe webhook: tenant mismatch session_id=%s meta=%s txn=%s", sid, meta_tenant, txn.get("tenant_id"))
        if txn.get("payment_status") == "paid":
            if txn.get("applied") is False:
                await payments_core.apply_pending_credit(db, sid)
            return {"ok": True}
        company = await db.companies.find_one({"id": txn["tenant_id"]}, {"_id": 0}) or {}
        await payments_core.verify_session(db, txn, payments_core.resolve_stripe_key(company), "webhook")
    except Exception as e:
        log.warning("stripe webhook error exc=%s: %s", type(e).__name__, e)
    return {"ok": True}


DUPLICATE_WARNING = "Posible cobro doble: verifica un reembolso"


@router.post("/quotations/{quotation_id}/verify-stripe")
async def verify_stripe_payments(quotation_id: str, user: dict = Depends(require_tenant)):
    """Iter 69/70: botón del ejecutivo. Reconciliación + detalle por transacción (sin correos ni loops)."""
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0, "id": 1})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0}) or {}
    api_key = payments_core.resolve_stripe_key(company)
    results = {r["session_id"]: r for r in await _reconcile_quotation_payments(db, quotation_id, company, source="executive")}
    txns = await db.payment_transactions.find({"quotation_id": quotation_id}, {"_id": 0}).sort("created_at", -1).to_list(20)
    is_admin = user.get("role") == "company_admin"
    rows = []
    for t in txns:
        r = results.get(t["session_id"])
        st_status, st_pay, error = None, None, None
        if r and r.get("stripe_status") is not None:
            st_status, st_pay = r.get("stripe_status"), r.get("stripe_payment_status")
        elif r and r.get("error"):
            error = r.get("error")
        elif api_key:
            try:
                st = await payments_core.stripe_get_status(api_key, t["session_id"])
                st_status, st_pay = st.status, st.payment_status
            except Exception as e:
                log.warning("verify-stripe read failed session_id=%s quotation_id=%s key_type=%s exc=%s: %s",
                            t["session_id"], quotation_id, payments_core.key_type(api_key), type(e).__name__, e)
                error = payments_core.readable_error(e)
        t = await db.payment_transactions.find_one({"session_id": t["session_id"]}, {"_id": 0}) or t
        stripe_paid = st_pay == "paid" if st_pay is not None else t.get("payment_status") == "paid"
        rows.append({
            "session_id": t["session_id"], "local_status": t.get("payment_status"),
            "stripe_status": f"{st_status} / {st_pay}" if st_status else None, "stripe_paid": stripe_paid,
            "amount": t.get("amount"), "base_amount": t.get("base_amount", t.get("amount")),
            "card_fee_amount": t.get("card_fee_amount", 0),
            "applied": bool(t.get("applied")) if t.get("payment_status") in ("paid", "reconciled") or t.get("review_state") else None,
            "review_state": t.get("review_state"), "review_reason": t.get("review_reason"), "review_at": t.get("review_at"),
            "reconciled_manually": t.get("reconciled_manually"),
            "created_at": t.get("created_at"), "paid_at": t.get("paid_at"),
            "error": error or t.get("apply_error"),
            "can_reconcile": is_admin and not t.get("applied"),
        })
    if sum(1 for r in rows if r["stripe_paid"]) >= 2:
        for r in rows:
            if r["stripe_paid"]:
                r["duplicate_warning"] = DUPLICATE_WARNING
    fresh = await db.quotations.find_one({"id": quotation_id}, {"_id": 0, "amount_paid": 1, "payment_status": 1, "payment_review": 1})
    return {"key_type": payments_core.key_type(api_key) if api_key else None, "transactions": rows, "is_admin": is_admin,
            "amount_paid": round(fresh.get("amount_paid", 0) or 0, 2), "payment_status": fresh.get("payment_status", "unpaid"),
            "payment_review": bool(fresh.get("payment_review")),
            "credited_now": sum(1 for r in results.values() if r.get("credited"))}


class ManualReconcileInput(BaseModel):
    reason: str = ""


@router.post("/quotations/{quotation_id}/transactions/{session_id}/reconcile-manual")
async def reconcile_manual(quotation_id: str, session_id: str, payload: ManualReconcileInput,
                           user: dict = Depends(require_tenant)):
    """Iter 70: solo administradores. Cierra la transacción sin sumar monto (pago ya registrado a mano)."""
    if user.get("role") != "company_admin":
        raise HTTPException(status_code=403, detail="Solo un administrador puede conciliar pagos manualmente.")
    db = get_db()
    txn = await db.payment_transactions.find_one(
        {"session_id": session_id, "quotation_id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not txn:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    if txn.get("applied") is True:
        raise HTTPException(status_code=400, detail="Esta transacción ya está aplicada o conciliada.")
    info = await payments_core.reconcile_manually(db, txn, user, payload.reason)
    return {"ok": True, "reconciled_manually": info}
