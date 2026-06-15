"""Automatic 48h payment reminders.

Runs as a lightweight background loop (started in server startup) plus a manual
trigger endpoint. Finds quotations the client ACCEPTED via the public link more
than REMINDER_HOURS ago that are still unpaid and sends a reminder email with a
direct "Pagar ahora" button. Each quotation is reminded at most once.
"""
import os
import logging
from datetime import datetime, timezone, timedelta

from database import get_db, now_iso
import notifications

log = logging.getLogger("routiq")

REMINDER_HOURS = int(os.environ.get("PAYMENT_REMINDER_HOURS", "48"))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")


def _pay_button_html(company_name: str, client_name: str, amount_due: float, ccy: str, link: str) -> str:
    btn = (f"<a href='{link}' style='background:#185FA5;color:#fff;padding:14px 26px;border-radius:10px;"
           f"text-decoration:none;font-weight:600;display:inline-block'>Pagar ahora</a>") if link else ""
    return (f"<h2>{company_name}</h2>"
            f"<p>Hola {client_name}, te recordamos que tu reserva está pendiente de pago.</p>"
            f"<p>Saldo pendiente: <b>${amount_due:,.2f} {ccy}</b></p>"
            f"<p style='margin:22px 0'>{btn}</p>"
            f"<p style='color:#64748b;font-size:12px'>Puedes pagar con tarjeta o por transferencia bancaria desde el enlace. "
            f"Si ya realizaste tu pago, ignora este mensaje.</p>")


def _resolve_link(q: dict) -> str:
    base = (q.get("public_link") or {}).get("base_url") or PUBLIC_BASE_URL
    token = (q.get("public_link") or {}).get("token")
    if not token:
        return ""
    base = (base or "").rstrip("/")
    return f"{base}/q/{token}" if base else ""


async def run_payment_reminders(db=None) -> dict:
    """Send reminders for unpaid accepted quotations older than REMINDER_HOURS.
    Returns a small summary. Idempotent per quotation (reminder_48h_sent flag)."""
    db = db or get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=REMINDER_HOURS)).isoformat()
    query = {
        "deleted": {"$ne": True},
        "public_link.accepted_at": {"$ne": None, "$lte": cutoff},
        "payment_status": {"$ne": "paid"},
        "public_link.reminder_48h_sent": {"$ne": True},
    }
    candidates = await db.quotations.find(query, {"_id": 0}).to_list(500)
    sent, skipped = 0, 0
    for q in candidates:
        final_total = q.get("final_total")
        if final_total is None:
            final_total = q.get("total", 0)
        amount_due = round(max(0.0, final_total - (q.get("amount_paid", 0) or 0)), 2)
        if amount_due <= 0:
            await db.quotations.update_one({"id": q["id"]}, {"$set": {"public_link.reminder_48h_sent": True}})
            skipped += 1
            continue
        company = await db.companies.find_one({"id": q["tenant_id"]}, {"_id": 0})
        # recipient
        contacts = q.get("contacts") or {}
        cl = await db.clients.find_one({"id": q.get("client_id")}, {"_id": 0, "email": 1})
        to = (cl or {}).get("email") or contacts.get("agency", {}).get("email") or ""
        link = _resolve_link(q)
        if to:
            html = _pay_button_html(company.get("name", ""), q.get("client_snapshot", {}).get("name", ""),
                                    amount_due, q.get("currency", "MXN"), link)
            try:
                await notifications.send_email(company, to, f"Recordatorio de pago — {q.get('code')}", html)
            except Exception:
                log.exception("reminder email failed for %s", q.get("code"))
        await db.quotations.update_one(
            {"id": q["id"]},
            {"$set": {"public_link.reminder_48h_sent": True, "public_link.reminder_sent_at": now_iso()}},
        )
        try:
            await db.quotations.update_one({"id": q["id"]}, {"$push": {"history": {
                "at": now_iso(), "user_id": None, "user_name": "Sistema (automático)",
                "action": "reminder", "detail": f"Recordatorio de pago automático enviado ({REMINDER_HOURS}h)",
            }}})
        except Exception:
            pass
        sent += 1
    return {"checked": len(candidates), "sent": sent, "skipped": skipped}
