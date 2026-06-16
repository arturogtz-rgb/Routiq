"""Routiq FastAPI server — multi-tenant SaaS for tourism quotations."""
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

import os
import io
import re
import asyncio
import logging
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path as _Path
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Response, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from database import get_db, new_id, now_iso, ensure_indexes, seed_super_admin, seed_demo_tenant, DEFAULT_PRICING_CONFIG, ensure_app_config, ensure_site_settings
from auth import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_token, set_auth_cookies, clear_auth_cookies,
    get_current_user, require_roles, require_tenant,
)
from models import (
    LoginInput, UserPublic, CompanyCreate, CompanyPublic, CompanyUpdate, PricingConfig,
    InviteExecutive, PackageCreate, PackageUpdate, ClientCreate, ClientUpdate,
    QuotationCreate, QuotationStateUpdate, QuotationUpdate, WhatsAppNumber,
    ServiceCreate, ServiceUpdate, CompanyIntegrationsUpdate, QuotationPricingAdjust,
    PublicCheckoutRequest, QuotationArchive, ManualPaymentInput, SendPaymentInput,
    CompanyPlanUpdate, SMTPTestInput,
)
from pricing import compute_quotation
from pdf_generator import generate_quotation_pdf
import ai_service
import currency
import notifications
import site_content
import push
from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionRequest

UPLOAD_DIR = _Path("/app/uploads") if _Path("/app/uploads").exists() or os.environ.get("DOCKER") else _Path(__file__).parent / "uploads"
LOGO_DIR = UPLOAD_DIR / "logos"
LOGO_DIR.mkdir(parents=True, exist_ok=True)
SITE_DIR = UPLOAD_DIR / "site"
SITE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
log = logging.getLogger("routiq")

app = FastAPI(title="Routiq API", version="1.0.0")
api = APIRouter(prefix="/api")

# Estados de cotización considerados "activos" (en curso)
ACTIVE_QUOTATION_STATES = ["nueva_consulta", "cotizando", "enviada", "negociacion"]

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def _startup():
    await ensure_indexes()
    await ensure_app_config()
    await ensure_site_settings()
    await seed_super_admin()
    await seed_demo_tenant()
    log.info("Startup complete — super admin + demo tenant seeded")
    asyncio.create_task(_reminder_loop())
    asyncio.create_task(_backup_check_loop())


async def _backup_check_loop():
    """Every 6h, alert the Master if the daily MongoDB backup is missing/stale (>24h).
    Sends a platform email when PLATFORM_RESEND_API_KEY is configured (no-op otherwise)."""
    import routes.backups as backups_mod
    import notifications
    while True:
        try:
            await asyncio.sleep(6 * 3600)
            status = backups_mod.freshness()
            if status.get("stale"):
                to = os.environ.get("SUPER_ADMIN_EMAIL", "")
                log.warning("BACKUP ALERT: %s", status.get("message"))
                html = (f"<h2 style='color:#b91c1c'>⚠️ Alerta de respaldo</h2>"
                        f"<p>{status.get('message')}</p>"
                        f"<p>Último respaldo: {status.get('last_at') or '—'} "
                        f"(hace {status.get('hours_since') if status.get('hours_since') is not None else '—'} h).</p>")
                await notifications.send_platform_email(to, "⚠️ Respaldo de MongoDB pendiente — Routiq", html)
        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("backup check loop error")


async def _reminder_loop():
    """Background loop: check for unpaid accepted quotations every 30 min."""
    import reminders
    while True:
        try:
            await asyncio.sleep(1800)
            res = await reminders.run_payment_reminders()
            if res.get("sent"):
                log.info("payment reminders sent: %s", res)
        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("reminder loop error")


@api.post("/internal/run-reminders")
async def run_reminders_now(user: dict = Depends(require_roles("super_admin"))):
    import reminders
    return await reminders.run_payment_reminders()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@api.get("/")
async def root():
    return {"service": "Routiq API", "status": "ok"}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@api.post("/auth/login", response_model=UserPublic)
async def login(payload: LoginInput, response: Response):
    db = get_db()
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")
    if user.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="Usuario suspendido")
    access = create_access_token(user["id"], user["email"], user["role"], user.get("tenant_id"))
    refresh = create_refresh_token(user["id"])
    set_auth_cookies(response, access, refresh)
    user.pop("password_hash", None)
    return user


@api.get("/auth/me", response_model=UserPublic)
async def me(user: dict = Depends(get_current_user)):
    return user


@api.post("/auth/logout")
async def logout(response: Response):
    clear_auth_cookies(response)
    return {"ok": True}


@api.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    import jwt as _jwt
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = decode_token(token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except _jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    db = get_db()
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    access = create_access_token(user["id"], user["email"], user["role"], user.get("tenant_id"))
    new_refresh = create_refresh_token(user["id"])
    set_auth_cookies(response, access, new_refresh)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Companies (tenants) — super_admin manages
# ---------------------------------------------------------------------------
@api.get("/companies", response_model=list[CompanyPublic])
async def list_companies(user: dict = Depends(require_roles("super_admin"))):
    db = get_db()
    return await db.companies.find({}, {"_id": 0}).to_list(500)


@api.post("/companies", response_model=CompanyPublic, status_code=201)
async def create_company(payload: CompanyCreate, user: dict = Depends(require_roles("super_admin"))):
    db = get_db()
    if await db.companies.find_one({"slug": payload.slug}):
        raise HTTPException(status_code=400, detail="Slug ya en uso")
    if await db.users.find_one({"email": payload.admin_email.lower()}):
        raise HTTPException(status_code=400, detail="Email de admin ya registrado")
    company = {
        "id": new_id(), "name": payload.name, "slug": payload.slug,
        "logo_url": "", "primary_color": "#185FA5",
        "contact_email": payload.contact_email, "contact_phone": payload.contact_phone,
        "address": payload.address,
        "pricing_config": DEFAULT_PRICING_CONFIG.copy(),
        "whatsapp_numbers": [],
        "status": "active",
        "created_at": now_iso(),
    }
    await db.companies.insert_one(dict(company))
    await db.users.insert_one({
        "id": new_id(), "email": payload.admin_email.lower(),
        "password_hash": hash_password(payload.admin_password),
        "name": payload.admin_name, "role": "company_admin",
        "tenant_id": company["id"], "status": "active", "created_at": now_iso(),
    })
    return company


@api.get("/companies/me", response_model=CompanyPublic)
async def get_my_company(user: dict = Depends(require_tenant)):
    db = get_db()
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return company


@api.patch("/companies/me", response_model=CompanyPublic)
async def update_my_company(payload: CompanyUpdate, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if updates:
        await db.companies.update_one({"id": user["tenant_id"]}, {"$set": updates})
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    return company


@api.patch("/companies/me/pricing", response_model=CompanyPublic)
async def update_pricing(payload: PricingConfig, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    await db.companies.update_one(
        {"id": user["tenant_id"]},
        {"$set": {"pricing_config": payload.model_dump()}},
    )
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    return company


# ---------------------------------------------------------------------------


@api.patch("/companies/{company_id}/status")
async def toggle_company_status(company_id: str, status: str, user: dict = Depends(require_roles("super_admin"))):
    if status not in ("active", "suspended"):
        raise HTTPException(status_code=400, detail="Status inválido")
    db = get_db()
    await db.companies.update_one({"id": company_id}, {"$set": {"status": status}})
    return {"ok": True, "status": status}


# Plan defaults (applied when a plan is selected; individually overridable) — see deps.PLAN_DEFAULTS
from deps import PLAN_DEFAULTS


@api.patch("/companies/{company_id}/plan", response_model=CompanyPublic)
async def update_company_plan(company_id: str, payload: CompanyPlanUpdate, user: dict = Depends(require_roles("super_admin"))):
    db = get_db()
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    updates = {}
    data = payload.model_dump(exclude_unset=True)
    if data.get("plan"):
        updates["plan"] = data["plan"]
        updates.update(PLAN_DEFAULTS.get(data["plan"], {}))
    # explicit per-field overrides win over plan defaults
    for k in ("exec_limit", "ai_enabled", "white_label", "routiq_logo_fallback", "stripe_allowed", "transfer_allowed"):
        if k in data and data[k] is not None:
            updates[k] = data[k]
    # If the Master disables a payment method, also turn off the company's own switch
    if updates.get("stripe_allowed") is False:
        updates["stripe.enabled"] = False
    if updates.get("transfer_allowed") is False:
        updates["bank.enabled"] = False
    await db.companies.update_one({"id": company_id}, {"$set": updates})
    return await db.companies.find_one({"id": company_id}, {"_id": 0})


# Collections fully owned by a tenant (keyed by tenant_id) — wiped on hard-delete.
_TENANT_COLLECTIONS = [
    "users", "packages", "services", "tours", "transfers", "clients",
    "quotations", "quotation_templates", "quote_requests", "payment_transactions",
    "notifications", "push_subscriptions", "audit_log", "ai_usage",
    "whatsapp_links", "whatsapp_messages",
]


@api.delete("/master/companies/{company_id}")
async def delete_company(company_id: str, confirm_name: str = "", user: dict = Depends(require_roles("super_admin"))):
    """Hard-delete a tenant and ALL its associated data (irreversible).
    Requires `confirm_name` to exactly match the company name (double confirmation)."""
    db = get_db()
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    if (confirm_name or "").strip() != company.get("name", ""):
        raise HTTPException(status_code=400, detail="El nombre de confirmación no coincide con el de la empresa.")
    deleted = {}
    for coll in _TENANT_COLLECTIONS:
        res = await db[coll].delete_many({"tenant_id": company_id})
        if res.deleted_count:
            deleted[coll] = res.deleted_count
    await db.companies.delete_one({"id": company_id})
    return {"ok": True, "company": company.get("name"), "deleted": deleted}


# ---------------------------------------------------------------------------
# WhatsApp numbers (mock for now)
# ---------------------------------------------------------------------------
@api.post("/companies/me/whatsapp-numbers", response_model=CompanyPublic)
async def add_whatsapp_number(number: str, label: str = "", user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    wa = {"id": new_id(), "number": number, "label": label, "status": "disconnected"}
    await db.companies.update_one({"id": user["tenant_id"]}, {"$push": {"whatsapp_numbers": wa}})
    return await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})


@api.delete("/companies/me/whatsapp-numbers/{wa_id}")
async def remove_whatsapp_number(wa_id: str, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    await db.companies.update_one({"id": user["tenant_id"]}, {"$pull": {"whatsapp_numbers": {"id": wa_id}}})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Users (team) — company_admin invites executives
# ---------------------------------------------------------------------------
@api.get("/users", response_model=list[UserPublic])
async def list_tenant_users(user: dict = Depends(require_tenant)):
    db = get_db()
    return await db.users.find({"tenant_id": user["tenant_id"]}, {"_id": 0, "password_hash": 0}).to_list(200)


@api.post("/users/invite-executive", response_model=UserPublic, status_code=201)
async def invite_executive(payload: InviteExecutive, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email ya registrado")
    # Enforce the contracted executive limit of the company's plan
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    exec_limit = int((company or {}).get("exec_limit", 0) or 0)
    if exec_limit > 0:
        active_execs = await db.users.count_documents({
            "tenant_id": user["tenant_id"], "role": "executive", "status": {"$ne": "suspended"},
        })
        if active_execs >= exec_limit:
            plan = (company or {}).get("plan", "tu plan")
            raise HTTPException(
                status_code=403,
                detail=(f"Alcanzaste el límite de {exec_limit} ejecutivos del plan {plan.capitalize()}. "
                        f"Suspende un ejecutivo o solicita una actualización de plan al administrador de Routiq."),
            )
    new_user = {
        "id": new_id(), "email": email, "name": payload.name,
        "password_hash": hash_password(payload.password),
        "role": "executive", "tenant_id": user["tenant_id"],
        "status": "active", "created_at": now_iso(),
    }
    await db.users.insert_one(dict(new_user))
    new_user.pop("password_hash", None)
    return new_user


@api.patch("/users/{user_id}/status")
async def toggle_user_status(user_id: str, status: str, user: dict = Depends(require_roles("company_admin"))):
    if status not in ("active", "suspended"):
        raise HTTPException(status_code=400, detail="Status inválido")
    db = get_db()
    target = await db.users.find_one({"id": user_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    await db.users.update_one({"id": user_id}, {"$set": {"status": status}})
    return {"ok": True}


@api.get("/users/{user_id}/workload")
async def user_workload(user_id: str, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    target = await db.users.find_one({"id": user_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    total = await db.quotations.count_documents({"tenant_id": user["tenant_id"], "assigned_to": user_id})
    active = await db.quotations.count_documents({
        "tenant_id": user["tenant_id"], "assigned_to": user_id, "state": {"$in": ACTIVE_QUOTATION_STATES}})
    return {"total": total, "active": active}


@api.delete("/users/{user_id}")
async def delete_tenant_user(user_id: str, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    target = await db.users.find_one({"id": user_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if target["id"] == user["id"]:
        raise HTTPException(status_code=400, detail="No puedes eliminarte a ti mismo")
    if target.get("role") == "company_admin":
        raise HTTPException(status_code=403, detail="No puedes eliminar a un administrador")
    # Reassign the executive's assigned quotations to the admin so nothing gets orphaned.
    res = await db.quotations.update_many(
        {"tenant_id": user["tenant_id"], "assigned_to": user_id},
        {"$set": {"assigned_to": user["id"]}},
    )
    await db.users.delete_one({"id": user_id, "tenant_id": user["tenant_id"]})
    return {"ok": True, "reassigned": res.modified_count}


@api.post("/companies/me/email/test")
async def test_company_email(payload: SMTPTestInput, user: dict = Depends(require_roles("company_admin"))):
    """Verify SMTP credentials by sending a test email before saving."""
    company = {
        "name": "Routiq", "white_label": True,
        "email_provider": "smtp",
        "smtp": {
            "host": payload.smtp_host, "port": payload.smtp_port,
            "username": payload.smtp_username, "password": payload.smtp_password,
            "use_tls": payload.smtp_use_tls, "from_email": payload.smtp_from_email,
            "from_name": payload.smtp_from_name,
        },
    }
    to = payload.to_email or payload.smtp_from_email
    html = ("<h2>✅ Conexión de correo verificada</h2>"
            "<p>Tu configuración SMTP funciona correctamente. Desde ahora tus cotizaciones "
            "y cobros se enviarán desde este correo.</p><p>— Routiq</p>")
    ok = await notifications.send_email(company, to, "Prueba de conexión — Routiq", html)
    if not ok:
        raise HTTPException(status_code=400, detail="No se pudo enviar el correo de prueba. Revisa host, puerto, usuario y contraseña.")
    return {"ok": True, "sent_to": to}


# ---------------------------------------------------------------------------
# Packages catalog
# ---------------------------------------------------------------------------
@api.get("/packages")
async def list_packages(user: dict = Depends(require_tenant)):
    db = get_db()
    return await db.packages.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).to_list(500)


@api.get("/packages/{package_id}")
async def get_package(package_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    pack = await db.packages.find_one({"id": package_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not pack:
        raise HTTPException(status_code=404, detail="Paquete no encontrado")
    return pack


def _ensure_season_ids(data: dict) -> dict:
    for s in (data.get("seasons") or []):
        if not s.get("id"):
            s["id"] = new_id()
    return data


@api.post("/packages", status_code=201)
async def create_package(payload: PackageCreate, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    if await db.packages.find_one({"tenant_id": user["tenant_id"], "code": payload.code}):
        raise HTTPException(status_code=400, detail="Código de paquete ya existe")
    data = _ensure_season_ids(payload.model_dump())
    doc = {"id": new_id(), "tenant_id": user["tenant_id"], "created_at": now_iso(), **data}
    await db.packages.insert_one(dict(doc))
    return doc


@api.patch("/packages/{package_id}")
async def update_package(package_id: str, payload: PackageUpdate, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if "seasons" in updates:
        _ensure_season_ids(updates)
    if updates:
        await db.packages.update_one({"id": package_id, "tenant_id": user["tenant_id"]}, {"$set": updates})
    pack = await db.packages.find_one({"id": package_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not pack:
        raise HTTPException(status_code=404, detail="Paquete no encontrado")
    return pack


@api.post("/packages/upload-image")
async def upload_package_image(file: UploadFile = File(...), user: dict = Depends(require_roles("company_admin"))):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Imagen muy grande (máx 5 MB)")
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
        ext = "png"
    pkg_dir = UPLOAD_DIR / "packages"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{new_id()}.{ext}"
    (pkg_dir / filename).write_bytes(content)
    return {"url": f"/api/uploads/packages/{filename}"}


@api.delete("/packages/{package_id}")
async def delete_package(package_id: str, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    await db.packages.delete_one({"id": package_id, "tenant_id": user["tenant_id"]})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Services catalog (a la carte: tours, traslados, accesos, extras)
# ---------------------------------------------------------------------------
@api.get("/services")
async def list_services(user: dict = Depends(require_tenant)):
    db = get_db()
    return await db.services.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("name", 1).to_list(500)


async def _auto_public_price(db, tenant_id: str, net_price: float, public_price: float) -> float:
    if public_price and public_price > 0:
        return round(public_price, 2)
    company = await db.companies.find_one({"id": tenant_id}, {"_id": 0, "pricing_config": 1})
    divisor = float((company or {}).get("pricing_config", {}).get("margin_divisor") or 0.76) or 0.76
    return round((net_price or 0) / divisor, 2)


@api.post("/services", status_code=201)
async def create_service(payload: ServiceCreate, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    data = payload.model_dump()
    data["public_price"] = await _auto_public_price(db, user["tenant_id"], data.get("net_price", 0), data.get("public_price", 0))
    doc = {"id": new_id(), "tenant_id": user["tenant_id"], "created_at": now_iso(), **data}
    await db.services.insert_one(dict(doc))
    return doc


@api.patch("/services/{service_id}")
async def update_service(service_id: str, payload: ServiceUpdate, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    existing = await db.services.find_one({"id": service_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    # recompute public if net changed and public not explicitly provided
    if "net_price" in updates and "public_price" not in updates:
        updates["public_price"] = await _auto_public_price(db, user["tenant_id"], updates["net_price"], 0)
    if updates:
        await db.services.update_one({"id": service_id, "tenant_id": user["tenant_id"]}, {"$set": updates})
    return await db.services.find_one({"id": service_id, "tenant_id": user["tenant_id"]}, {"_id": 0})


@api.delete("/services/{service_id}")
async def delete_service(service_id: str, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    await db.services.delete_one({"id": service_id, "tenant_id": user["tenant_id"]})
    return {"ok": True}



# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
@api.get("/clients")
async def list_clients(user: dict = Depends(require_tenant)):
    db = get_db()
    t = user["tenant_id"]
    clients = await db.clients.find({"tenant_id": t}, {"_id": 0}).to_list(2000)
    # Aggregate per-client activity (count, active count, won sales, last activity)
    pipeline = [
        {"$match": {"tenant_id": t, "deleted": {"$ne": True}}},
        {"$group": {
            "_id": "$client_id",
            "count": {"$sum": 1},
            "active": {"$sum": {"$cond": [{"$in": ["$state", ACTIVE_QUOTATION_STATES]}, 1, 0]}},
            "sales": {"$sum": {"$cond": [{"$eq": ["$state", "ganada"]}, {"$ifNull": ["$total", 0]}, 0]}},
            "last": {"$max": "$last_activity_at"},
        }},
    ]
    stats = {row["_id"]: row async for row in db.quotations.aggregate(pipeline)}
    for c in clients:
        s = stats.get(c["id"], {})
        c["quotations_count"] = s.get("count", 0)
        c["active_count"] = s.get("active", 0)
        c["sales_total"] = round(s.get("sales", 0) or 0, 2)
        c["last_activity_at"] = s.get("last") or c.get("created_at")
    return clients


@api.post("/clients", status_code=201)
async def create_client(payload: ClientCreate, user: dict = Depends(require_tenant)):
    db = get_db()
    doc = {"id": new_id(), "tenant_id": user["tenant_id"], "created_at": now_iso(), **payload.model_dump()}
    await db.clients.insert_one(dict(doc))
    return doc


@api.patch("/clients/{client_id}")
async def update_client(client_id: str, payload: ClientUpdate, user: dict = Depends(require_tenant)):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nada que actualizar")
    res = await db.clients.update_one({"id": client_id, "tenant_id": user["tenant_id"]}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return await db.clients.find_one({"id": client_id, "tenant_id": user["tenant_id"]}, {"_id": 0})


@api.delete("/clients/{client_id}")
async def delete_client(client_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    res = await db.clients.delete_one({"id": client_id, "tenant_id": user["tenant_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return {"ok": True}



# ---------------------------------------------------------------------------
# Dashboard metrics
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# In-app notifications (executive alerts)
# ---------------------------------------------------------------------------
@api.get("/notifications")
async def list_notifications(user: dict = Depends(require_tenant)):
    db = get_db()
    items = await db.notifications.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    unread = await db.notifications.count_documents({"tenant_id": user["tenant_id"], "read": False})
    return {"items": items, "unread": unread}


@api.post("/notifications/read-all")
async def mark_notifications_read(user: dict = Depends(require_tenant)):
    db = get_db()
    await db.notifications.update_many({"tenant_id": user["tenant_id"], "read": False}, {"$set": {"read": True}})
    return {"ok": True}


@api.get("/metrics/dashboard")
async def dashboard_metrics(user: dict = Depends(require_tenant)):
    db = get_db()
    t = user["tenant_id"]
    total = await db.quotations.count_documents({"tenant_id": t})
    won = await db.quotations.count_documents({"tenant_id": t, "state": "ganada"})
    lost = await db.quotations.count_documents({"tenant_id": t, "state": "perdida"})
    active = await db.quotations.count_documents({"tenant_id": t, "state": {"$in": ["nueva_consulta", "cotizando", "enviada", "negociacion"]}})
    closed = won + lost
    conversion = round((won / closed) * 100, 1) if closed > 0 else 0.0
    # Projected revenue = sum of total for active + ganada
    cursor = db.quotations.find({"tenant_id": t, "state": {"$in": ["cotizando", "enviada", "negociacion"]}}, {"_id": 0, "total": 1})
    projected = 0.0
    async for doc in cursor:
        projected += doc.get("total", 0) or 0
    revenue_cursor = db.quotations.find({"tenant_id": t, "state": "ganada"}, {"_id": 0, "total": 1})
    revenue = 0.0
    async for doc in revenue_cursor:
        revenue += doc.get("total", 0) or 0
    return {
        "quotations_total": total,
        "quotations_active": active,
        "quotations_won": won,
        "quotations_lost": lost,
        "conversion_rate": conversion,
        "projected_revenue": round(projected, 2),
        "revenue_won": round(revenue, 2),
    }


@api.get("/metrics/master")
async def master_metrics(user: dict = Depends(require_roles("super_admin"))):
    db = get_db()
    companies = await db.companies.count_documents({})
    active = await db.companies.count_documents({"status": "active"})
    quotations = await db.quotations.count_documents({})
    users = await db.users.count_documents({"role": {"$ne": "super_admin"}})
    # per-company stats
    per_company = []
    async for c in db.companies.find({}, {"_id": 0}):
        q_total = await db.quotations.count_documents({"tenant_id": c["id"]})
        q_won = await db.quotations.count_documents({"tenant_id": c["id"], "state": "ganada"})
        per_company.append({
            "id": c["id"], "name": c["name"], "slug": c["slug"],
            "status": c.get("status", "active"),
            "quotations_total": q_total, "quotations_won": q_won,
        })
    return {
        "companies_total": companies,
        "companies_active": active,
        "quotations_total": quotations,
        "users_total": users,
        "per_company": per_company,
    }


# ---------------------------------------------------------------------------
# Logo upload
# ---------------------------------------------------------------------------
@api.post("/companies/me/logo", response_model=CompanyPublic)
async def upload_company_logo(file: UploadFile = File(...), user: dict = Depends(require_roles("company_admin"))):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Imagen muy grande (máx 2 MB)")
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("png", "jpg", "jpeg", "svg", "webp"):
        ext = "png"
    filename = f"{user['tenant_id']}.{ext}"
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    # Remove old logo files for this tenant
    for old in LOGO_DIR.glob(f"{user['tenant_id']}.*"):
        try:
            old.unlink()
        except Exception:
            pass
    (LOGO_DIR / filename).write_bytes(content)
    logo_url = f"/api/uploads/logos/{filename}"
    db = get_db()
    await db.companies.update_one({"id": user["tenant_id"]}, {"$set": {"logo_url": logo_url}})
    return await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})


@api.delete("/companies/me/logo", response_model=CompanyPublic)
async def remove_company_logo(user: dict = Depends(require_roles("company_admin"))):
    for old in LOGO_DIR.glob(f"{user['tenant_id']}.*"):
        try:
            old.unlink()
        except Exception:
            pass
    db = get_db()
    await db.companies.update_one({"id": user["tenant_id"]}, {"$set": {"logo_url": ""}})
    return await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})




# ---------------------------------------------------------------------------
# Site content editor (Landing + Login) — super_admin, preview before publish
# ---------------------------------------------------------------------------
@api.get("/site-settings/public")
async def site_settings_public():
    db = get_db()
    doc = await db.site_settings.find_one({"id": "default"}, {"_id": 0}) or {}
    return site_content.merged_with_defaults(doc.get("published"))


@api.get("/site-settings")
async def site_settings_get(user: dict = Depends(require_roles("super_admin"))):
    db = get_db()
    doc = await db.site_settings.find_one({"id": "default"}, {"_id": 0}) or {}
    draft_src = doc.get("draft") or doc.get("published")
    return {
        "draft": site_content.merged_with_defaults(draft_src),
        "published": site_content.merged_with_defaults(doc.get("published")),
    }


@api.patch("/site-settings")
async def site_settings_patch(payload: dict, user: dict = Depends(require_roles("super_admin"))):
    db = get_db()
    # Validate theme primary color to avoid persisting a value that breaks the UI
    theme_in = payload.get("theme")
    if isinstance(theme_in, dict) and theme_in.get("primary"):
        if not re.match(r"^#[0-9A-Fa-f]{6}$", str(theme_in["primary"]).strip()):
            raise HTTPException(status_code=400, detail="Color principal inválido (usa formato #RRGGBB)")
    doc = await db.site_settings.find_one({"id": "default"}) or {"draft": {}, "published": {}}
    draft = doc.get("draft") or {}
    for section in ("landing", "login", "theme"):
        if section in payload and isinstance(payload[section], dict):
            draft.setdefault(section, {})
            draft[section].update({k: v for k, v in payload[section].items()})
    await db.site_settings.update_one({"id": "default"}, {"$set": {"draft": draft}}, upsert=True)
    return site_content.merged_with_defaults(draft)


@api.post("/site-settings/publish")
async def site_settings_publish(user: dict = Depends(require_roles("super_admin"))):
    db = get_db()
    doc = await db.site_settings.find_one({"id": "default"}) or {}
    draft = doc.get("draft") or {}
    await db.site_settings.update_one({"id": "default"}, {"$set": {"published": draft}}, upsert=True)
    return {"ok": True, "published": site_content.merged_with_defaults(draft)}


@api.post("/site-settings/reset-draft")
async def site_settings_reset(user: dict = Depends(require_roles("super_admin"))):
    db = get_db()
    doc = await db.site_settings.find_one({"id": "default"}) or {}
    await db.site_settings.update_one({"id": "default"}, {"$set": {"draft": doc.get("published") or {}}}, upsert=True)
    return {"ok": True}


@api.post("/site-settings/upload-image")
async def site_settings_upload_image(file: UploadFile = File(...), user: dict = Depends(require_roles("super_admin"))):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Imagen muy grande (máx 5 MB)")
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("png", "jpg", "jpeg", "svg", "webp", "gif"):
        ext = "png"
    filename = f"{new_id()}.{ext}"
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / filename).write_bytes(content)
    return {"url": f"/api/uploads/site/{filename}"}


# ---------------------------------------------------------------------------
# Web Push (VAPID)
# ---------------------------------------------------------------------------
@api.get("/push/vapid-public-key")
async def push_vapid_public_key():
    db = get_db()
    cfg = await db.app_config.find_one({"id": "vapid"}, {"_id": 0})
    return {"public_key": (cfg or {}).get("public_key", "")}


@api.post("/push/subscribe")
async def push_subscribe(payload: dict, user: dict = Depends(require_tenant)):
    db = get_db()
    sub = payload.get("subscription") or payload
    endpoint = sub.get("endpoint")
    if not endpoint:
        raise HTTPException(status_code=400, detail="Suscripción inválida")
    await db.push_subscriptions.update_one(
        {"endpoint": endpoint},
        {"$set": {
            "endpoint": endpoint, "subscription": sub,
            "tenant_id": user["tenant_id"], "user_id": user["id"], "created_at": now_iso(),
        }},
        upsert=True,
    )
    return {"ok": True}


@api.post("/push/unsubscribe")
async def push_unsubscribe(payload: dict, user: dict = Depends(require_tenant)):
    db = get_db()
    endpoint = (payload.get("subscription") or payload).get("endpoint")
    if endpoint:
        await db.push_subscriptions.delete_one({"endpoint": endpoint})
    return {"ok": True}




# ---------------------------------------------------------------------------
# Router + CORS
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Modular routers (Fase D refactor): quotations, public payments, audit, integrations
# ---------------------------------------------------------------------------
from routes import (
    quotations as quotations_routes,
    public_payments as public_payments_routes,
    audit as audit_routes,
    integrations as integrations_routes,
    signup as signup_routes,
    whatsapp as whatsapp_routes,
    backups as backups_routes,
    catalog_import as catalog_import_routes,
    gmail_oauth as gmail_oauth_routes,
    public_package as public_package_routes,
    account as account_routes,
    ai_settings as ai_settings_routes,
    templates as templates_routes,
)

api.include_router(quotations_routes.router)
api.include_router(public_payments_routes.router)
api.include_router(audit_routes.router)
api.include_router(integrations_routes.router)
api.include_router(signup_routes.router)
api.include_router(whatsapp_routes.router)
api.include_router(backups_routes.router)
api.include_router(catalog_import_routes.router)
api.include_router(gmail_oauth_routes.router)
api.include_router(public_package_routes.router)
api.include_router(account_routes.router)
api.include_router(ai_settings_routes.router)
api.include_router(templates_routes.router)

app.include_router(api)

# Static files for uploaded logos — mounted under /api so it passes through ingress
app.mount("/api/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
