"""Shared helpers used across route modules (no FastAPI app dependency to avoid
circular imports). Pure functions + DB helpers consumed by the routers under
`routes/`."""
import os
import logging
from datetime import datetime, timezone
from pathlib import Path as _Path

from database import new_id, now_iso
import notifications

log = logging.getLogger("routiq")

# Plan defaults applied when a plan is selected (overridable per company by Master)
PLAN_DEFAULTS = {
    "starter": {"exec_limit": 3, "ai_enabled": False, "white_label": False,
                "stripe_allowed": False, "transfer_allowed": True},
    "pro": {"exec_limit": 15, "ai_enabled": True, "white_label": False,
            "stripe_allowed": True, "transfer_allowed": True},
    "enterprise": {"exec_limit": 0, "ai_enabled": True, "white_label": True,
                   "stripe_allowed": True, "transfer_allowed": True},
}


def slugify(name: str) -> str:
    """Lowercase, ASCII-ish slug from a company name."""
    import re as _re
    import unicodedata as _ud
    norm = _ud.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    slug = _re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")
    return slug or "empresa"

UPLOAD_DIR = _Path("/app/uploads") if _Path("/app/uploads").exists() or os.environ.get("DOCKER") else _Path(__file__).parent / "uploads"
LOGO_DIR = UPLOAD_DIR / "logos"
LOGO_DIR.mkdir(parents=True, exist_ok=True)
SITE_DIR = UPLOAD_DIR / "site"
SITE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Integrations view
# ---------------------------------------------------------------------------
def _mask_secret(value: str) -> str:
    if not value:
        return ""
    return "••••" + value[-4:] if len(value) > 4 else "••••"


# ---------------------------------------------------------------------------
# Rich-text sanitizer (cancellation policy authored by company admins)
# ---------------------------------------------------------------------------
import re as _re_html

_ALLOWED_TAGS = {"p", "br", "b", "strong", "i", "em", "u", "ul", "ol", "li",
                 "span", "div", "h1", "h2", "h3", "h4", "a"}
_TAG_RE = _re_html.compile(r"</?\s*([a-zA-Z0-9]+)([^>]*)>")


def sanitize_richtext(html: str) -> str:
    """Lenient whitelist sanitizer for admin-authored rich text. Removes script/
    style blocks, inline event handlers and javascript: URLs, and strips any tag
    not in the allowlist (keeping its inner text)."""
    if not html:
        return ""
    html = html[:20000]
    html = _re_html.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", html)
    html = _re_html.sub(r"(?i)\son\w+\s*=\s*\"[^\"]*\"", "", html)
    html = _re_html.sub(r"(?i)\son\w+\s*=\s*'[^']*'", "", html)
    html = _re_html.sub(r"(?i)javascript:", "", html)

    def _keep(m):
        return m.group(0) if m.group(1).lower() in _ALLOWED_TAGS else ""

    return _TAG_RE.sub(_keep, html).strip()


def _integrations_view(company: dict) -> dict:
    stripe = company.get("stripe") or {}
    resend = company.get("resend") or {}
    smtp = company.get("smtp") or {}
    return {
        "stripe_publishable_key": stripe.get("publishable_key", ""),
        "stripe_secret_key_masked": _mask_secret(stripe.get("secret_key", "")),
        "stripe_secret_set": bool(stripe.get("secret_key")),
        "stripe_enabled": bool(stripe.get("enabled", False)),
        "resend_api_key_masked": _mask_secret(resend.get("api_key", "")),
        "resend_api_key_set": bool(resend.get("api_key")),
        "resend_from_email": resend.get("from_email", ""),
        "resend_from_name": resend.get("from_name", ""),
        "base_currency": company.get("base_currency", "MXN"),
        "deposit_percent": company.get("deposit_percent", 50),
        "notify_email": company.get("notify_email", ""),
        # Bank transfer
        "bank_enabled": bool((company.get("bank") or {}).get("enabled", False)),
        "bank_name": (company.get("bank") or {}).get("name", ""),
        "bank_holder": (company.get("bank") or {}).get("holder", ""),
        "bank_clabe": (company.get("bank") or {}).get("clabe", ""),
        "bank_account": (company.get("bank") or {}).get("account", ""),
        "bank_usd_account": (company.get("bank") or {}).get("usd_account", ""),
        "bank_swift": (company.get("bank") or {}).get("swift", ""),
        "bank_aba": (company.get("bank") or {}).get("aba", ""),
        "bank_address": (company.get("bank") or {}).get("address", ""),
        "bank_branch": (company.get("bank") or {}).get("branch", ""),
        "bank_reference": (company.get("bank") or {}).get("reference", ""),
        # Payment permissions controlled by Master (per plan)
        "stripe_allowed": bool(company.get("stripe_allowed", True)),
        "transfer_allowed": bool(company.get("transfer_allowed", True)),
        "plan": company.get("plan", "pro"),
        # Per-company outbound email (SMTP)
        "email_provider": company.get("email_provider", "resend"),
        "smtp_host": smtp.get("host", ""),
        "smtp_port": smtp.get("port", 587),
        "smtp_username": smtp.get("username", ""),
        "smtp_password_set": bool(smtp.get("password")),
        "smtp_use_tls": bool(smtp.get("use_tls", True)),
        "smtp_from_email": smtp.get("from_email", ""),
        "smtp_from_name": smtp.get("from_name", ""),
        # Gmail OAuth (per company)
        "gmail_client_id": (company.get("gmail") or {}).get("client_id", ""),
        "gmail_client_id_set": bool((company.get("gmail") or {}).get("client_id")),
        "gmail_client_secret_set": bool((company.get("gmail") or {}).get("client_secret")),
        "gmail_from_name": (company.get("gmail") or {}).get("from_name", ""),
        "gmail_connected": bool((company.get("gmail") or {}).get("refresh_token")),
        "gmail_email": (company.get("gmail") or {}).get("email", ""),
        # Automated sales report
        "report_enabled": bool((company.get("sales_report") or {}).get("enabled", False)),
        "report_frequency": (company.get("sales_report") or {}).get("frequency", "weekly"),
        "report_day": (company.get("sales_report") or {}).get("day", 1),
        "report_hour": (company.get("sales_report") or {}).get("hour", 8),
        "report_timezone": (company.get("sales_report") or {}).get("timezone", "America/Mexico_City"),
    }


# ---------------------------------------------------------------------------
# Quotation helpers
# ---------------------------------------------------------------------------
async def _load_services_catalog(db, tenant_id: str, selected: list) -> dict:
    ids = [s["service_id"] if isinstance(s, dict) else s.service_id for s in (selected or [])]
    if not ids:
        return {}
    catalog = {}
    async for svc in db.services.find({"id": {"$in": ids}, "tenant_id": tenant_id}, {"_id": 0}):
        catalog[svc["id"]] = svc
    return catalog


async def _next_quotation_code(db, tenant_id: str) -> str:
    count = await db.quotations.count_documents({"tenant_id": tenant_id})
    return f"COT-{2026000 + count + 1}"


async def _append_history(db, quotation_id: str, user: dict, action: str, detail: str = ""):
    """Append an immutable change-log entry to the quotation's history array."""
    entry = {
        "at": now_iso(),
        "user_id": user.get("id"),
        "user_name": user.get("name", ""),
        "action": action,
        "detail": detail,
    }
    await db.quotations.update_one({"id": quotation_id}, {"$push": {"history": entry}})


async def _record_audit(db, tenant_id: str, user: dict, action: str, q: dict, detail: str = ""):
    """Write an audit-log entry (deleted / archived / restored / won)."""
    await db.audit_log.insert_one({
        "id": new_id(),
        "tenant_id": tenant_id,
        "action": action,
        "quotation_id": q.get("id"),
        "quotation_code": q.get("code", ""),
        "client_name": (q.get("client_snapshot") or {}).get("name", ""),
        "total": q.get("final_total", q.get("total", 0)),
        "currency": q.get("currency", "MXN"),
        "executive_id": user.get("id"),
        "executive_name": user.get("name", ""),
        "detail": detail,
        "at": now_iso(),
    })


def _apply_discount(total: float, discount: dict) -> tuple[float, float]:
    dt = discount.get("type", "none")
    dv = float(discount.get("value", 0) or 0)
    if dt == "percent":
        amount = round(total * dv / 100.0, 2)
    elif dt == "fixed":
        amount = round(dv, 2)
    else:
        amount = 0.0
    amount = max(0.0, min(amount, total))
    return round(total - amount, 2), amount


# ---------------------------------------------------------------------------
# Payment helpers
# ---------------------------------------------------------------------------
async def _client_email(db, q: dict) -> str:
    """Best-effort recipient email for the end client of a quotation."""
    contacts = q.get("contacts") or {}
    cl = await db.clients.find_one({"id": q.get("client_id")}, {"_id": 0, "email": 1})
    return (cl or {}).get("email") or contacts.get("agency", {}).get("email") or ""


def _bank_html(bank: dict, ccy: str, amount: float) -> str:
    rows = [
        ("Banco", bank.get("name")), ("Titular", bank.get("holder")),
        ("CLABE", bank.get("clabe")), ("Cuenta", bank.get("account")),
        ("Cuenta USD", bank.get("usd_account")), ("SWIFT/BIC", bank.get("swift")),
        ("ABA/Routing", bank.get("aba")), ("Domicilio del banco", bank.get("address")),
    ]
    body = "".join(f"<tr><td style='padding:4px 12px;color:#64748b'>{k}</td><td style='padding:4px 12px;font-weight:600'>{v}</td></tr>"
                   for k, v in rows if v)
    return (f"<p>Importe a transferir: <b>${amount:,.2f} {ccy}</b></p>"
            f"<table style='border-collapse:collapse'>{body}</table>"
            f"<p style='color:#64748b;font-size:12px'>Una vez realizada la transferencia, envíanos tu comprobante para confirmar la reserva.</p>")


def _resolve_stripe_key(company: dict) -> str:
    sk = ((company or {}).get("stripe") or {}).get("secret_key")
    return sk or os.environ.get("STRIPE_API_KEY", "")


async def _apply_payment_to_quotation(txn: dict):
    """Idempotent: called only once per session_id (guarded by caller)."""
    from database import get_db
    db = get_db()
    q = await db.quotations.find_one({"id": txn["quotation_id"]}, {"_id": 0})
    if not q:
        return
    amount_paid = round((q.get("amount_paid", 0) or 0) + float(txn["amount"]), 2)
    final_total = q.get("final_total")
    if final_total is None:
        final_total = q.get("total", 0)
    pay_status = "paid" if amount_paid >= round(final_total, 2) - 0.01 else "partial"
    updates = {
        "amount_paid": amount_paid,
        "payment_status": pay_status,
        "last_activity_at": now_iso(),
    }
    # move to ganada when client pays
    if q.get("state") not in ("ganada",):
        updates["state"] = "ganada"
    await db.quotations.update_one({"id": q["id"]}, {"$set": updates})
    if updates.get("state") == "ganada":
        try:
            await _record_audit(db, q["tenant_id"], {"id": None, "name": "Pago en línea"},
                                "won", q, "Ganada por pago del cliente")
        except Exception:
            log.exception("audit payment-won failed")
    # Fire executive notification (email + log) — best effort
    try:
        await notifications.notify_payment(db, q, txn, amount_paid, pay_status)
    except Exception:
        log.exception("payment notification failed")
