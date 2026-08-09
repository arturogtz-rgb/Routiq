"""Payment follow-up helpers.

IMPORTANT (Iter 5 / P0): the product no longer sends payment reminders to
CLIENTS automatically. Client-facing payment reminders are now a MANUAL action
the executive triggers from the follow-up assistant.

This module only provides an INTERNAL, opt-in daily digest sent to the EXECUTIVE
(never to the client) listing their accepted-but-unpaid reservations so they can
decide whether to follow up. It is idempotent per company per day via an atomic
guard (find_one_and_update) so a loop overlap or a backend restart can never send
a duplicate digest.
"""
import os
import logging
from datetime import datetime, timezone, timedelta

from database import get_db, now_iso

log = logging.getLogger("routiq")

DIGEST_HOURS = int(os.environ.get("PAYMENT_REMINDER_HOURS", "48"))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")


def _resolve_link(q: dict) -> str:
    base = (q.get("public_link") or {}).get("base_url") or PUBLIC_BASE_URL
    token = (q.get("public_link") or {}).get("token")
    if not token:
        return ""
    base = (base or "").rstrip("/")
    return f"{base}/q/{token}" if base else ""


def _amount_due(q: dict) -> float:
    final_total = q.get("final_total")
    if final_total is None:
        final_total = q.get("total", 0)
    return round(max(0.0, final_total - (q.get("amount_paid", 0) or 0)), 2)


def _digest_html(company_name: str, exec_name: str, rows: list) -> str:
    items = "".join(
        f"<li style='margin:8px 0'><b>{r['code']}</b> — {r['client']} · saldo "
        f"<b>${r['due']:,.2f} {r['ccy']}</b>{(' · <a href=' + chr(39) + r['link'] + chr(39) + '>ver enlace</a>') if r['link'] else ''}</li>"
        for r in rows
    )
    return (
        f"<h2>{company_name}</h2>"
        f"<p>Hola {exec_name or ''}, este es tu resumen interno de reservas <b>aceptadas sin pago</b>. "
        f"Es solo para ti: decide si das seguimiento desde el panel de la cotización.</p>"
        f"<ul style='padding-left:18px'>{items}</ul>"
        f"<p style='color:#64748b;font-size:12px'>Este correo es interno (no se envía al cliente). "
        f"Puedes desactivarlo en Ajustes → Pagos.</p>"
    )


async def run_internal_payment_digest(db=None, force: bool = False) -> dict:
    """Send an INTERNAL daily digest to each executive with their accepted-unpaid
    reservations. Opt-in per company (companies.internal_payment_digest=True).
    Atomic per-company-per-day guard prevents duplicates. Never emails clients."""
    import notifications
    db = db or get_db()
    today = datetime.now(timezone.utc).date().isoformat()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=DIGEST_HOURS)).isoformat()
    companies = await db.companies.find({"internal_payment_digest": True}, {"_id": 0}).to_list(500)
    total_sent = 0
    for company in companies:
        # Atomic guard: claim today's digest BEFORE doing any work/sending.
        if not force:
            claimed = await db.companies.find_one_and_update(
                {"id": company["id"], "last_internal_digest_date": {"$ne": today}},
                {"$set": {"last_internal_digest_date": today}},
            )
            if claimed is None:
                continue  # already sent today
        query = {
            "tenant_id": company["id"],
            "deleted": {"$ne": True},
            "public_link.accepted_at": {"$ne": None, "$lte": cutoff},
            "payment_status": {"$ne": "paid"},
        }
        candidates = await db.quotations.find(query, {"_id": 0}).to_list(500)
        # Group by elaborating executive (created_by); fallback to company notify_email.
        by_exec: dict = {}
        for q in candidates:
            if _amount_due(q) <= 0:
                continue
            key = q.get("created_by") or "__company__"
            by_exec.setdefault(key, []).append({
                "code": q.get("code", ""),
                "client": (q.get("client_snapshot") or {}).get("name", ""),
                "due": _amount_due(q),
                "ccy": q.get("currency", "MXN"),
                "link": _resolve_link(q),
            })
        for exec_key, rows in by_exec.items():
            to, exec_name = "", ""
            if exec_key != "__company__":
                u = await db.users.find_one({"id": exec_key}, {"_id": 0, "email": 1, "name": 1})
                if u:
                    to, exec_name = u.get("email", ""), u.get("name", "")
            if not to:
                to = company.get("notify_email") or ""
            if not to:
                continue
            html = _digest_html(company.get("name", ""), exec_name, rows)
            try:
                await notifications.send_email(company, to, f"Resumen interno · reservas por cobrar ({len(rows)})", html)
                total_sent += 1
            except Exception:
                log.exception("internal digest email failed for %s", company.get("id"))
    return {"companies": len(companies), "digests_sent": total_sent}
