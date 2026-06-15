"""Notification dispatch: executive alerts on payment / acceptance.

Email delivery via Resend is wired in Task 3 (uses per-company resend.api_key).
For now this logs the intent and stores an in-app notification document so the
flow is observable and testable. The email hook is centralized in `send_email`.
"""
from __future__ import annotations
import logging
import os

import httpx

log = logging.getLogger("routiq.notifications")


async def send_email(company: dict, to_email: str, subject: str, html: str) -> bool:
    """Send an email using the company's Resend API key. Best-effort.

    Returns True if accepted by Resend, False otherwise (never raises).
    """
    resend = (company or {}).get("resend") or {}
    api_key = resend.get("api_key") or os.environ.get("RESEND_API_KEY")
    if not api_key or not to_email:
        log.info("send_email skipped (no resend key or recipient) -> %s | %s", to_email, subject)
        return False
    from_email = resend.get("from_email") or "onboarding@resend.dev"
    from_name = resend.get("from_name") or company.get("name") or "Routiq"
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"from": f"{from_name} <{from_email}>", "to": [to_email], "subject": subject, "html": html},
            )
            ok = r.status_code in (200, 201)
            if not ok:
                log.warning("Resend rejected email (%s): %s", r.status_code, r.text[:300])
            return ok
    except Exception as e:
        log.warning("Resend send failed: %s", e)
        return False


def _money(v: float, ccy: str = "MXN") -> str:
    return f"${float(v or 0):,.2f} {ccy}"


async def _recipient(db, company: dict, q: dict) -> str:
    # priority: company.notify_email -> assigned executive email -> contact_email
    if company.get("notify_email"):
        return company["notify_email"]
    assigned = q.get("assigned_to")
    if assigned:
        u = await db.users.find_one({"id": assigned}, {"_id": 0, "email": 1})
        if u and u.get("email"):
            return u["email"]
    return company.get("contact_email", "")


async def _store_inapp(db, q: dict, kind: str, title: str, body: str):
    from datetime import datetime, timezone
    await db.notifications.insert_one({
        "tenant_id": q["tenant_id"], "quotation_id": q["id"],
        "kind": kind, "title": title, "body": body,
        "read": False, "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def _send_push(db, q: dict, title: str, body: str):
    """Send Web Push to all subscriptions of the tenant. Best-effort."""
    import push as push_mod
    cfg = await db.app_config.find_one({"id": "vapid"}, {"_id": 0})
    if not cfg:
        return
    vapid = {"public_key": cfg.get("public_key"), "private_key": cfg.get("private_key")}
    subs = await db.push_subscriptions.find({"tenant_id": q["tenant_id"]}, {"_id": 0}).to_list(200)
    payload = {"title": title, "body": body, "url": f"/app/quotations/{q['id']}"}
    for s in subs:
        status = push_mod.send_push(s.get("subscription") or {}, payload, vapid)
        if status in (404, 410):
            await db.push_subscriptions.delete_one({"endpoint": s.get("endpoint")})


async def notify_acceptance(db, q: dict):
    company = await db.companies.find_one({"id": q["tenant_id"]}, {"_id": 0})
    client = q.get("client_snapshot", {}).get("name", "Cliente")
    ccy = q.get("currency", "MXN")
    title = f"✅ Cotización {q.get('code')} aceptada"
    body = f"{client} aceptó la cotización {q.get('code')} por {_money(q.get('final_total', q.get('total')), ccy)}."
    log.info("ACCEPTANCE: %s", body)
    await _store_inapp(db, q, "acceptance", title, body)
    await _send_push(db, q, title, body)
    to = await _recipient(db, company, q)
    html = f"<h2>{title}</h2><p>{body}</p><p>Paquete: {q.get('package_snapshot', {}).get('name', '')}</p>"
    await send_email(company, to, title, html)


async def notify_payment(db, q: dict, txn: dict, amount_paid: float, pay_status: str):
    company = await db.companies.find_one({"id": q["tenant_id"]}, {"_id": 0})
    client = q.get("client_snapshot", {}).get("name", "Cliente")
    ccy = txn.get("currency", q.get("currency", "MXN"))
    label = "pago total" if pay_status == "paid" else "pago parcial"
    title = f"💳 {label.capitalize()} recibido — {q.get('code')}"
    body = (f"{client} realizó un {label} de {_money(txn.get('amount'), ccy)} "
            f"en la cotización {q.get('code')}. Acumulado: {_money(amount_paid, ccy)}.")
    log.info("PAYMENT: %s", body)
    await _store_inapp(db, q, "payment", title, body)
    await _send_push(db, q, title, body)
    to = await _recipient(db, company, q)
    html = f"<h2>{title}</h2><p>{body}</p>"
    await send_email(company, to, title, html)
