"""Self-service tenant signup funnel.

Public visitors submit a signup request from the landing pricing section. The
Super Admin reviews pending requests in the Master panel and approves/rejects.
On approval the company + admin user are created with the requested plan, a
best-effort welcome email is sent, and the credentials are returned so the
Master can share them manually if email delivery isn't configured.
"""
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from database import get_db, new_id, now_iso, DEFAULT_PRICING_CONFIG
from auth import hash_password, require_roles
from models import SignupRequest, SignupApprove, SignupReject
from deps import PLAN_DEFAULTS, slugify
import notifications

log = logging.getLogger("routiq.signup")
router = APIRouter()

LOGIN_URL = os.environ.get("PUBLIC_LOGIN_URL", "https://routiq.com.mx/login")
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "")
if not TURNSTILE_SECRET_KEY:
    log.warning("TURNSTILE_SECRET_KEY no configurada — el captcha de /api/signup está DESACTIVADO (solo rate-limit + honeypot activos).")

# Rate-limit: per public IP
SIGNUP_MAX_PER_HOUR = 5
SIGNUP_MAX_PER_DAY = 20


def _client_ip(request: Request) -> str:
    """Real client IP behind ingress/nginx (X-Forwarded-For first hop)."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _verify_turnstile(token: str | None, ip: str) -> bool:
    """Verify a Cloudflare Turnstile token. Skips when no secret key is set."""
    if not TURNSTILE_SECRET_KEY:
        return True
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": TURNSTILE_SECRET_KEY, "response": token, "remoteip": ip},
            )
            return bool(resp.json().get("success", False))
    except Exception:
        log.exception("Turnstile verify failed")
        return False


async def _rate_limited(db, ip: str) -> bool:
    now = datetime.now(timezone.utc)
    per_hour = await db.signup_attempts.count_documents({"ip": ip, "at": {"$gte": now - timedelta(hours=1)}})
    if per_hour >= SIGNUP_MAX_PER_HOUR:
        return True
    per_day = await db.signup_attempts.count_documents({"ip": ip, "at": {"$gte": now - timedelta(days=1)}})
    return per_day >= SIGNUP_MAX_PER_DAY


async def _unique_slug(db, base: str) -> str:
    slug = base
    i = 2
    while await db.companies.find_one({"slug": slug}, {"_id": 1}):
        slug = f"{base}-{i}"
        i += 1
    return slug


def _request_public(r: dict) -> dict:
    return {
        "id": r["id"],
        "company_name": r["company_name"],
        "admin_name": r["admin_name"],
        "admin_email": r["admin_email"],
        "admin_phone": r.get("admin_phone", ""),
        "plan": r.get("plan", "pro"),
        "slug": r.get("slug", ""),
        "status": r.get("status", "pending"),
        "reason": r.get("reason", ""),
        "created_at": r.get("created_at", ""),
        "decided_at": r.get("decided_at", ""),
    }


# ---------------------------------------------------------------------------
# Public: submit a signup request
# ---------------------------------------------------------------------------
@router.post("/signup", status_code=201)
async def submit_signup(payload: SignupRequest, request: Request):
    db = get_db()
    ip = _client_ip(request)
    # Honeypot — bots fill the hidden field. Pretend success, store nothing.
    if (payload.website or "").strip():
        log.info("signup honeypot triggered from %s", ip)
        return {"ok": True, "id": "ok"}
    # Rate-limit per IP
    if await _rate_limited(db, ip):
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes. Intenta de nuevo más tarde.")
    # Captcha (skipped if no secret key configured)
    if not await _verify_turnstile(payload.turnstile_token, ip):
        raise HTTPException(status_code=400, detail="No pudimos verificar el captcha. Recárgalo e intenta de nuevo.")

    email = payload.admin_email.lower().strip()
    if await db.users.find_one({"email": email}, {"_id": 1}):
        raise HTTPException(status_code=400, detail="Ya existe una cuenta con ese correo. Inicia sesión.")
    if await db.tenant_requests.find_one({"admin_email": email, "status": "pending"}, {"_id": 1}):
        raise HTTPException(status_code=400, detail="Ya tienes una solicitud pendiente con ese correo.")
    req = {
        "id": new_id(),
        "company_name": payload.company_name.strip(),
        "admin_name": payload.admin_name.strip(),
        "admin_email": email,
        "admin_phone": payload.admin_phone.strip(),
        "plan": payload.plan,
        "slug": slugify(payload.company_name),
        "password_hash": hash_password(payload.admin_password),
        "status": "pending",
        "reason": "",
        "created_at": now_iso(),
        "decided_at": "",
    }
    await db.tenant_requests.insert_one(dict(req))
    await db.signup_attempts.insert_one({"ip": ip, "at": datetime.now(timezone.utc)})
    return {"ok": True, "id": req["id"]}


# ---------------------------------------------------------------------------
# Master: list / approve / reject
# ---------------------------------------------------------------------------
@router.get("/tenant-requests")
async def list_requests(status: str | None = None, user: dict = Depends(require_roles("super_admin"))):
    db = get_db()
    q = {}
    if status:
        q["status"] = status
    rows = await db.tenant_requests.find(q, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    return rows


@router.get("/tenant-requests/count")
async def pending_count(user: dict = Depends(require_roles("super_admin"))):
    db = get_db()
    return {"pending": await db.tenant_requests.count_documents({"status": "pending"})}


@router.get("/tenant-requests/metrics")
async def funnel_metrics(user: dict = Depends(require_roles("super_admin"))):
    """Conversion KPI for the Master panel: received → approved → active (this month)."""
    db = get_db()
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    rx = {"$regex": f"^{month}"}
    received = await db.tenant_requests.count_documents({"created_at": rx})
    approved = await db.tenant_requests.count_documents({"status": "approved", "decided_at": rx})
    rejected = await db.tenant_requests.count_documents({"status": "rejected", "decided_at": rx})
    active = await db.companies.count_documents({"status": "active", "created_at": rx})
    conv = round((approved / received) * 100) if received else 0
    return {
        "month": month,
        "received": received,
        "approved": approved,
        "rejected": rejected,
        "active": active,
        "conversion_pct": conv,
    }


@router.post("/tenant-requests/{request_id}/approve")
async def approve_request(request_id: str, payload: SignupApprove, user: dict = Depends(require_roles("super_admin"))):
    db = get_db()
    req = await db.tenant_requests.find_one({"id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if req.get("status") != "pending":
        raise HTTPException(status_code=400, detail="La solicitud ya fue procesada")
    if await db.users.find_one({"email": req["admin_email"]}, {"_id": 1}):
        raise HTTPException(status_code=400, detail="El correo del admin ya está registrado")

    base_slug = slugify(payload.slug) if payload.slug else req.get("slug") or slugify(req["company_name"])
    slug = await _unique_slug(db, base_slug)
    plan = req.get("plan", "pro")
    plan_defaults = PLAN_DEFAULTS.get(plan, PLAN_DEFAULTS["pro"])

    company = {
        "id": new_id(),
        "name": req["company_name"], "slug": slug,
        "logo_url": "", "primary_color": "#185FA5",
        "contact_email": req["admin_email"], "contact_phone": req.get("admin_phone", ""),
        "address": "",
        "pricing_config": DEFAULT_PRICING_CONFIG.copy(),
        "whatsapp_numbers": [],
        "status": "active",
        "plan": plan,
        **plan_defaults,
        "created_at": now_iso(),
    }
    await db.companies.insert_one(dict(company))
    await db.users.insert_one({
        "id": new_id(), "email": req["admin_email"],
        "password_hash": req["password_hash"],
        "name": req["admin_name"], "role": "company_admin",
        "tenant_id": company["id"], "status": "active", "created_at": now_iso(),
    })
    await db.tenant_requests.update_one(
        {"id": request_id},
        {"$set": {"status": "approved", "decided_at": now_iso(), "company_id": company["id"], "slug": slug},
         "$unset": {"password_hash": ""}},
    )

    # Best-effort welcome email (uses platform Resend env if configured)
    email_sent = False
    try:
        html = (
            f"<div style='font-family:system-ui,Arial,sans-serif'>"
            f"<h2 style='color:#185FA5'>¡Bienvenido a Routiq, {req['admin_name']}!</h2>"
            f"<p>Tu empresa <b>{req['company_name']}</b> ya está activa con el plan "
            f"<b>{plan.capitalize()}</b>.</p>"
            f"<p>Accede con tu correo <b>{req['admin_email']}</b> y la contraseña que elegiste al registrarte.</p>"
            f"<p><a href='{LOGIN_URL}' style='background:#185FA5;color:#fff;padding:10px 18px;"
            f"border-radius:8px;text-decoration:none'>Entrar a Routiq</a></p>"
            f"<p style='color:#64748b;font-size:12px'>Si no solicitaste esta cuenta, ignora este correo.</p></div>"
        )
        email_sent = await notifications.send_email(
            company, req["admin_email"], "Tu cuenta de Routiq está lista", html)
    except Exception:
        log.exception("welcome email failed")

    return {
        "ok": True,
        "company": {"id": company["id"], "name": company["name"], "slug": slug, "plan": plan},
        "credentials": {"email": req["admin_email"], "login_url": LOGIN_URL},
        "email_sent": bool(email_sent),
    }


@router.post("/tenant-requests/{request_id}/reject")
async def reject_request(request_id: str, payload: SignupReject, user: dict = Depends(require_roles("super_admin"))):
    db = get_db()
    req = await db.tenant_requests.find_one({"id": request_id}, {"_id": 1, "status": 1})
    if not req:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if req.get("status") != "pending":
        raise HTTPException(status_code=400, detail="La solicitud ya fue procesada")
    await db.tenant_requests.update_one(
        {"id": request_id},
        {"$set": {"status": "rejected", "reason": payload.reason or "", "decided_at": now_iso()},
         "$unset": {"password_hash": ""}},
    )
    return {"ok": True}
