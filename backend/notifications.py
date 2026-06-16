"""Notification dispatch: executive alerts on payment / acceptance.

Email delivery via Resend is wired in Task 3 (uses per-company resend.api_key).
For now this logs the intent and stores an in-app notification document so the
flow is observable and testable. The email hook is centralized in `send_email`.
"""
from __future__ import annotations
import logging
import os

import httpx
import aiosmtplib
from email.message import EmailMessage

log = logging.getLogger("routiq.notifications")

ROUTIQ_FOOTER = (
    "<hr style='margin-top:28px;border:none;border-top:1px solid #e2e8f0'/>"
    "<p style='color:#94a3b8;font-size:11px'>Enviado con <b>Routiq</b> · routiq.com.mx</p>"
)


def _with_footer(company: dict, html: str) -> str:
    if (company or {}).get("white_label"):
        return html
    return html + ROUTIQ_FOOTER


async def send_platform_email(to_email: str, subject: str, html: str) -> bool:
    """Send a platform-level email (no tenant) via Resend using PLATFORM_* env vars.
    Used for Master notifications and Master password resets. Best-effort."""
    api_key = os.environ.get("PLATFORM_RESEND_API_KEY")
    from_email = os.environ.get("PLATFORM_FROM_EMAIL", "no-reply@routiq.com.mx")
    if not api_key or not to_email:
        log.info("platform email skipped (no key/recipient) -> %s", subject)
        return False
    html = html + ROUTIQ_FOOTER
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"from": f"Routiq <{from_email}>", "to": [to_email], "subject": subject, "html": html},
            )
            ok = r.status_code in (200, 201)
            if not ok:
                log.warning("platform Resend rejected (%s): %s", r.status_code, r.text[:300])
            return ok
    except Exception as e:
        log.warning("platform email failed: %s", e)
        return False




async def _send_smtp(company: dict, to_email: str, subject: str, html: str) -> bool:
    smtp = (company or {}).get("smtp") or {}
    host = smtp.get("host")
    if not host:
        return False
    msg = EmailMessage()
    from_email = smtp.get("from_email") or smtp.get("username")
    from_name = smtp.get("from_name") or company.get("name") or "Routiq"
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content("Este correo requiere un cliente con soporte HTML.")
    msg.add_alternative(html, subtype="html")
    port = int(smtp.get("port", 587) or 587)
    use_tls = bool(smtp.get("use_tls", True))
    try:
        # 465 -> implicit TLS; 587/others -> STARTTLS
        if port == 465:
            await aiosmtplib.send(msg, hostname=host, port=port, username=smtp.get("username"),
                                  password=smtp.get("password"), use_tls=True, timeout=15)
        else:
            await aiosmtplib.send(msg, hostname=host, port=port, username=smtp.get("username"),
                                  password=smtp.get("password"), start_tls=use_tls, timeout=15)
        return True
    except Exception as e:
        log.warning("SMTP send failed: %s", e)
        return False


async def send_test_smtp(host: str, port: int, username: str, password: str,
                         use_tls: bool, from_email: str, from_name: str, to_email: str):
    """Send a one-off SMTP test email with explicit credentials.
    Returns (ok: bool, error: str)."""
    msg = EmailMessage()
    msg["From"] = f"{from_name or 'Routiq'} <{from_email}>"
    msg["To"] = to_email
    msg["Subject"] = "Prueba de configuración SMTP — Routiq"
    msg.set_content("Tu configuración SMTP de Routiq funciona correctamente.")
    msg.add_alternative(
        "<div style='font-family:system-ui,Arial,sans-serif'>"
        "<h2 style='color:#185FA5'>✅ Configuración SMTP correcta</h2>"
        "<p>Tu correo corporativo está listo. A partir de ahora, las cotizaciones y "
        "los cobros se enviarán desde tu propio remitente.</p>"
        f"<p style='color:#64748b;font-size:12px'>Enviado por Routiq como prueba.</p></div>",
        subtype="html",
    )
    try:
        p = int(port or 587)
        if p == 465:
            await aiosmtplib.send(msg, hostname=host, port=p, username=username,
                                  password=password, use_tls=True, timeout=20)
        else:
            await aiosmtplib.send(msg, hostname=host, port=p, username=username,
                                  password=password, start_tls=bool(use_tls), timeout=20)
        return True, ""
    except Exception as e:
        log.warning("SMTP test failed: %s", e)
        return False, str(e)




async def send_email(company: dict, to_email: str, subject: str, html: str) -> bool:
    """Send an email using the company's configured provider (SMTP or Resend).
    Best-effort: returns True if accepted, False otherwise (never raises)."""
    if not to_email:
        log.info("send_email skipped (no recipient) -> %s", subject)
        return False
    html = _with_footer(company, html)
    provider = (company or {}).get("email_provider")
    if provider == "gmail" and ((company or {}).get("gmail") or {}).get("refresh_token"):
        return await _send_gmail(company, to_email, subject, html)
    if provider == "smtp" and ((company or {}).get("smtp") or {}).get("host"):
        return await _send_smtp(company, to_email, subject, html)
    # default: Resend
    resend = (company or {}).get("resend") or {}
    api_key = resend.get("api_key") or os.environ.get("RESEND_API_KEY")
    if not api_key:
        # Platform fallback: lets tenants without their own email provider still
        # deliver transactional mail (e.g. password reset) via Routiq's verified domain.
        plat_key = os.environ.get("PLATFORM_RESEND_API_KEY")
        if plat_key:
            plat_from = os.environ.get("PLATFORM_FROM_EMAIL", "no-reply@routiq.com.mx")
            from_name = (company or {}).get("name") or "Routiq"
            try:
                async with httpx.AsyncClient(timeout=12) as client:
                    r = await client.post(
                        "https://api.resend.com/emails",
                        headers={"Authorization": f"Bearer {plat_key}", "Content-Type": "application/json"},
                        json={"from": f"{from_name} <{plat_from}>", "to": [to_email], "subject": subject, "html": html},
                    )
                    ok = r.status_code in (200, 201)
                    if not ok:
                        log.warning("platform-fallback Resend rejected (%s): %s", r.status_code, r.text[:300])
                    return ok
            except Exception as e:
                log.warning("platform-fallback Resend failed: %s", e)
                return False
        log.info("send_email skipped (no provider configured) -> %s | %s", to_email, subject)
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


async def _send_gmail(company: dict, to_email: str, subject: str, html: str) -> bool:
    """Send via the company's Gmail account (OAuth2 refresh token). Best-effort."""
    import base64
    from email.message import EmailMessage as _EM
    gmail = (company or {}).get("gmail") or {}
    cid, secret, rtoken = gmail.get("client_id"), gmail.get("client_secret"), gmail.get("refresh_token")
    from_email = gmail.get("email")
    if not (cid and secret and rtoken and from_email):
        log.info("gmail send skipped (incomplete config) -> %s", subject)
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            tok = await client.post("https://oauth2.googleapis.com/token", data={
                "client_id": cid, "client_secret": secret,
                "refresh_token": rtoken, "grant_type": "refresh_token",
            })
            if tok.status_code != 200:
                log.warning("gmail token refresh failed (%s): %s", tok.status_code, tok.text[:200])
                return False
            access_token = tok.json().get("access_token")
            msg = _EM()
            from_name = gmail.get("from_name") or company.get("name") or "Routiq"
            msg["From"] = f"{from_name} <{from_email}>"
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.set_content("Tu cliente de correo no soporta HTML.")
            msg.add_alternative(html, subtype="html")
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            r = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": raw},
            )
            ok = r.status_code in (200, 202)
            if not ok:
                log.warning("gmail send rejected (%s): %s", r.status_code, r.text[:200])
            return ok
    except Exception as e:
        log.warning("gmail send failed: %s", e)
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
    html = f"<h2>{title}</h2><p>{body}</p><p>Paquete: {(q.get('package_snapshot') or {}).get('name', '')}</p>"
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
