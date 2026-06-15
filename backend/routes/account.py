"""Account & user management: password reset (forgot/reset), self-service profile
edits, admin/master reset-link generation, master company contact edits, and a
public config endpoint (demo credentials toggle).

Password reset tokens are stored hashed (sha256) in `password_reset_tokens` with a
real datetime `expires_at` (1h) for the TTL index. Single-use enforced via `used`.
"""
import os
import hashlib
import secrets
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from pymongo.errors import DuplicateKeyError

from database import get_db, new_id, now_iso
from auth import get_current_user, require_roles, require_tenant, hash_password, verify_password
import notifications

log = logging.getLogger("routiq.account")
router = APIRouter()

RESET_TTL_MIN = 60


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _base_url(request: Request, override: str | None = None) -> str:
    if override:
        return override.rstrip("/")
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")
    login = os.environ.get("PUBLIC_LOGIN_URL", "")
    return login.rsplit("/login", 1)[0].rstrip("/") if login else ""


async def _create_reset_token(db, user_id: str) -> str:
    raw = secrets.token_urlsafe(32)
    await db.password_reset_tokens.insert_one({
        "id": new_id(),
        "user_id": user_id,
        "token_hash": _hash_token(raw),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=RESET_TTL_MIN),
        "used": False,
        "created_at": now_iso(),
    })
    return raw


async def _send_reset_email(db, user: dict, link: str) -> bool:
    subject = "Restablece tu contraseña — Routiq"
    html = (
        f"<div style='font-family:system-ui,Arial,sans-serif'>"
        f"<h2 style='color:#185FA5'>Restablecer contraseña</h2>"
        f"<p>Hola {user.get('name','')}, recibimos una solicitud para restablecer tu contraseña.</p>"
        f"<p><a href='{link}' style='display:inline-block;background:#185FA5;color:#fff;"
        f"padding:12px 22px;border-radius:9999px;text-decoration:none;font-weight:600'>Crear nueva contraseña</a></p>"
        f"<p style='color:#64748b;font-size:12px'>El enlace expira en 1 hora. Si no fuiste tú, ignora este correo.</p></div>"
    )
    if user.get("tenant_id"):
        company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
        return await notifications.send_email(company or {}, user["email"], subject, html)
    # super_admin / no tenant -> platform email
    return await notifications.send_platform_email(user["email"], subject, html)


# ---------------------------------------------------------------------------
# Public: forgot / reset password
# ---------------------------------------------------------------------------
class ForgotInput(BaseModel):
    email: EmailStr
    base_url: str | None = None


@router.post("/auth/forgot-password")
async def forgot_password(payload: ForgotInput, request: Request):
    db = get_db()
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user and user.get("status") != "suspended":
        raw = await _create_reset_token(db, user["id"])
        link = f"{_base_url(request, payload.base_url)}/reset-password?token={raw}"
        await _send_reset_email(db, user, link)
    # never reveal whether the email exists
    return {"ok": True, "message": "Si el correo existe, enviamos un enlace de recuperación."}


class ResetInput(BaseModel):
    token: str
    password: str


@router.post("/auth/reset-password")
async def reset_password(payload: ResetInput):
    db = get_db()
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres")
    doc = await db.password_reset_tokens.find_one({"token_hash": _hash_token(payload.token)})
    if not doc or doc.get("used"):
        raise HTTPException(status_code=400, detail="Enlace inválido o ya utilizado")
    exp = doc.get("expires_at")
    if isinstance(exp, datetime):
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="El enlace expiró. Solicita uno nuevo.")
    await db.users.update_one({"id": doc["user_id"]}, {"$set": {"password_hash": hash_password(payload.password)}})
    await db.password_reset_tokens.update_one({"id": doc["id"]}, {"$set": {"used": True, "used_at": now_iso()}})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Self-service profile (any authenticated role)
# ---------------------------------------------------------------------------
class ProfileUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    current_password: str | None = None
    new_password: str | None = None


@router.patch("/auth/profile")
async def update_profile(payload: ProfileUpdate, user: dict = Depends(get_current_user)):
    db = get_db()
    full = await db.users.find_one({"id": user["id"]})
    if not full:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    updates: dict = {}
    sensitive = bool(payload.new_password) or (payload.email and payload.email.lower().strip() != full["email"])
    if sensitive:
        if not payload.current_password or not verify_password(payload.current_password, full["password_hash"]):
            raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")
    if payload.name is not None and payload.name.strip():
        updates["name"] = payload.name.strip()
    if payload.email:
        updates["email"] = payload.email.lower().strip()
    if payload.new_password:
        if len(payload.new_password) < 8:
            raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 8 caracteres")
        updates["password_hash"] = hash_password(payload.new_password)
    if updates:
        try:
            await db.users.update_one({"id": user["id"]}, {"$set": updates})
        except DuplicateKeyError:
            raise HTTPException(status_code=400, detail="Ese correo ya está en uso")
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    return fresh


# ---------------------------------------------------------------------------
# Company admin: manage executives (edit + reset link)
# ---------------------------------------------------------------------------
class UserEditInput(BaseModel):
    name: str | None = None
    email: EmailStr | None = None


@router.patch("/users/{user_id}")
async def edit_tenant_user(user_id: str, payload: UserEditInput, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    target = await db.users.find_one({"id": user_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if target.get("role") == "company_admin" and target["id"] != user["id"]:
        raise HTTPException(status_code=403, detail="No puedes editar a otro administrador")
    updates: dict = {}
    if payload.name is not None and payload.name.strip():
        updates["name"] = payload.name.strip()
    if payload.email:
        updates["email"] = payload.email.lower().strip()
    if updates:
        try:
            await db.users.update_one({"id": user_id}, {"$set": updates})
        except DuplicateKeyError:
            raise HTTPException(status_code=400, detail="Ese correo ya está en uso")
    return await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})


@router.post("/users/{user_id}/reset-link")
async def tenant_user_reset_link(user_id: str, request: Request, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    target = await db.users.find_one({"id": user_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    raw = await _create_reset_token(db, user_id)
    link = f"{_base_url(request)}/reset-password?token={raw}"
    # best-effort email too (company provider)
    await _send_reset_email(db, target, link)
    return {"ok": True, "link": link, "email": target["email"]}


# ---------------------------------------------------------------------------
# Master: edit company contact + reset link for any user
# ---------------------------------------------------------------------------
class CompanyContactInput(BaseModel):
    name: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None


@router.patch("/master/companies/{company_id}/contact")
async def master_update_company_contact(company_id: str, payload: CompanyContactInput, user: dict = Depends(require_roles("super_admin"))):
    db = get_db()
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    updates = {}
    if payload.name is not None and payload.name.strip():
        updates["name"] = payload.name.strip()
    if payload.contact_email:
        updates["contact_email"] = payload.contact_email.lower().strip()
    if payload.contact_phone is not None:
        updates["contact_phone"] = payload.contact_phone.strip()
    if updates:
        await db.companies.update_one({"id": company_id}, {"$set": updates})
    return await db.companies.find_one({"id": company_id}, {"_id": 0})


@router.post("/master/users/{user_id}/reset-link")
async def master_user_reset_link(user_id: str, request: Request, user: dict = Depends(require_roles("super_admin"))):
    db = get_db()
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    raw = await _create_reset_token(db, user_id)
    link = f"{_base_url(request)}/reset-password?token={raw}"
    await _send_reset_email(db, target, link)
    return {"ok": True, "link": link, "email": target["email"]}


@router.get("/master/company-admins")
async def master_list_company_admins(user: dict = Depends(require_roles("super_admin"))):
    """List the primary admin (company_admin) of each tenant for reset-link UX."""
    db = get_db()
    admins = await db.users.find(
        {"role": "company_admin"}, {"_id": 0, "id": 1, "name": 1, "email": 1, "tenant_id": 1}).to_list(500)
    return admins


# ---------------------------------------------------------------------------
# Public config (demo credentials toggle, etc.)
# ---------------------------------------------------------------------------
@router.get("/public-config")
async def public_config():
    show = os.environ.get("SHOW_DEMO_CREDENTIALS", "true").lower() in ("1", "true", "yes")
    return {"show_demo_credentials": show}
