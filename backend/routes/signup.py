"""Self-service tenant signup funnel.

Public visitors submit a signup request from the landing pricing section. The
Super Admin reviews pending requests in the Master panel and approves/rejects.
On approval the company + admin user are created with the requested plan, a
best-effort welcome email is sent, and the credentials are returned so the
Master can share them manually if email delivery isn't configured.
"""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException

from database import get_db, new_id, now_iso, DEFAULT_PRICING_CONFIG
from auth import hash_password, require_roles
from models import SignupRequest, SignupApprove, SignupReject
from deps import PLAN_DEFAULTS, slugify
import notifications

log = logging.getLogger("routiq.signup")
router = APIRouter()

LOGIN_URL = os.environ.get("PUBLIC_LOGIN_URL", "https://routiq.com.mx/login")


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
async def submit_signup(payload: SignupRequest):
    db = get_db()
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
