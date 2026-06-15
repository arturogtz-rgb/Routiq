"""Routiq FastAPI server — multi-tenant SaaS for tourism quotations."""
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

import os
import io
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
    InviteExecutive, PackageCreate, PackageUpdate, ClientCreate,
    QuotationCreate, QuotationStateUpdate, QuotationUpdate, WhatsAppNumber,
    ServiceCreate, ServiceUpdate, CompanyIntegrationsUpdate, QuotationPricingAdjust,
    PublicCheckoutRequest, QuotationArchive, ManualPaymentInput, SendPaymentInput,
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
# Company integrations (Stripe / Resend / currency) — admin configurable, no SSH
# ---------------------------------------------------------------------------
def _mask_secret(value: str) -> str:
    if not value:
        return ""
    return "••••" + value[-4:] if len(value) > 4 else "••••"


def _integrations_view(company: dict) -> dict:
    stripe = company.get("stripe") or {}
    resend = company.get("resend") or {}
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
    }


@api.get("/companies/me/integrations")
async def get_my_integrations(user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return _integrations_view(company)


@api.patch("/companies/me/integrations")
async def update_my_integrations(payload: CompanyIntegrationsUpdate, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    data = payload.model_dump(exclude_unset=True)
    updates: dict = {}
    if "stripe_publishable_key" in data:
        updates["stripe.publishable_key"] = data["stripe_publishable_key"] or ""
    if "stripe_secret_key" in data and data["stripe_secret_key"]:
        # only overwrite when a non-empty value is provided (avoid wiping with masked value)
        if not data["stripe_secret_key"].startswith("••"):
            updates["stripe.secret_key"] = data["stripe_secret_key"]
    if "stripe_enabled" in data:
        updates["stripe.enabled"] = bool(data["stripe_enabled"])
    if "resend_api_key" in data and data["resend_api_key"]:
        if not data["resend_api_key"].startswith("••"):
            updates["resend.api_key"] = data["resend_api_key"]
    if "resend_from_email" in data:
        updates["resend.from_email"] = data["resend_from_email"] or ""
    if "resend_from_name" in data:
        updates["resend.from_name"] = data["resend_from_name"] or ""
    if "base_currency" in data and data["base_currency"]:
        updates["base_currency"] = data["base_currency"]
        # keep pricing currency in sync
        updates["pricing_config.currency"] = data["base_currency"]
    if "deposit_percent" in data and data["deposit_percent"]:
        updates["deposit_percent"] = float(data["deposit_percent"])
    if "notify_email" in data:
        updates["notify_email"] = data["notify_email"] or ""
    _BANK_FIELDS = {
        "bank_name": "bank.name", "bank_holder": "bank.holder", "bank_clabe": "bank.clabe",
        "bank_account": "bank.account", "bank_usd_account": "bank.usd_account",
        "bank_swift": "bank.swift", "bank_aba": "bank.aba", "bank_address": "bank.address",
    }
    for key, path in _BANK_FIELDS.items():
        if key in data:
            updates[path] = data[key] or ""
    if "bank_enabled" in data:
        updates["bank.enabled"] = bool(data["bank_enabled"])
    if updates:
        await db.companies.update_one({"id": user["tenant_id"]}, {"$set": updates})
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    return _integrations_view(company)


@api.get("/exchange-rate")
async def exchange_rate():
    return await currency.get_rates()


@api.patch("/companies/{company_id}/status")
async def toggle_company_status(company_id: str, status: str, user: dict = Depends(require_roles("super_admin"))):
    if status not in ("active", "suspended"):
        raise HTTPException(status_code=400, detail="Status inválido")
    db = get_db()
    await db.companies.update_one({"id": company_id}, {"$set": {"status": status}})
    return {"ok": True, "status": status}


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


async def _load_services_catalog(db, tenant_id: str, selected: list) -> dict:
    ids = [s["service_id"] if isinstance(s, dict) else s.service_id for s in (selected or [])]
    if not ids:
        return {}
    catalog = {}
    async for svc in db.services.find({"id": {"$in": ids}, "tenant_id": tenant_id}, {"_id": 0}):
        catalog[svc["id"]] = svc
    return catalog


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
@api.get("/clients")
async def list_clients(user: dict = Depends(require_tenant)):
    db = get_db()
    return await db.clients.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).to_list(500)


@api.post("/clients", status_code=201)
async def create_client(payload: ClientCreate, user: dict = Depends(require_tenant)):
    db = get_db()
    doc = {"id": new_id(), "tenant_id": user["tenant_id"], "created_at": now_iso(), **payload.model_dump()}
    await db.clients.insert_one(dict(doc))
    return doc


# ---------------------------------------------------------------------------
# Quotations
# ---------------------------------------------------------------------------
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


@api.get("/quotations")
async def list_quotations(state: str | None = None, archived: bool = False, user: dict = Depends(require_tenant)):
    db = get_db()
    q = {"tenant_id": user["tenant_id"], "deleted": {"$ne": True}}
    if archived:
        q["archived"] = True
    else:
        q["archived"] = {"$ne": True}
    if state:
        q["state"] = state
    items = await db.quotations.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    # enrich with days_idle
    now = datetime.now(timezone.utc)
    for it in items:
        try:
            last = datetime.fromisoformat(it.get("last_activity_at", it.get("created_at")))
            it["days_idle"] = (now - last).days
        except Exception:
            it["days_idle"] = 0
    return items


@api.get("/quotations/{quotation_id}")
async def get_quotation(quotation_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    return q


@api.post("/quotations", status_code=201)
async def create_quotation(payload: QuotationCreate, user: dict = Depends(require_tenant)):
    db = get_db()
    client = await db.clients.find_one({"id": payload.client_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    pricing_config = company.get("pricing_config") or DEFAULT_PRICING_CONFIG
    services_sel = [s.model_dump() for s in payload.services]
    services_catalog = await _load_services_catalog(db, user["tenant_id"], services_sel)

    is_services = payload.type == "servicios" or not payload.package_id
    pack = None
    package_snapshot = None
    if not is_services:
        pack = await db.packages.find_one({"id": payload.package_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not pack:
            raise HTTPException(status_code=404, detail="Paquete no encontrado")
        package_snapshot = {"name": pack["name"], "code": pack["code"], "nights": pack["nights"]}
    elif not services_sel:
        raise HTTPException(status_code=400, detail="Agrega al menos un servicio para una cotización a la carta")

    # Defensive: swap dates if start > end
    d_start = payload.dates.start
    d_end = payload.dates.end
    if d_start and d_end and d_start > d_end:
        d_start, d_end = d_end, d_start
    extra_cfg = payload.extra_nights.model_dump() if payload.extra_nights else None
    pack_nights = pack["nights"] if pack else 0
    calc = compute_quotation(pack, payload.hotel_name, payload.pax.model_dump(),
                             pack_nights, client["channel"], pricing_config,
                             services_catalog, services_sel,
                             dates={"start": d_start, "end": d_end}, extra_nights_cfg=extra_cfg)
    code = await _next_quotation_code(db, user["tenant_id"])
    doc = {
        "id": new_id(), "tenant_id": user["tenant_id"], "code": code,
        "client_id": client["id"], "client_snapshot": {"name": client["name"], "channel": client["channel"]},
        "type": "servicios" if is_services else "paquete",
        "package_id": pack["id"] if pack else None,
        "package_snapshot": package_snapshot,
        "hotel_selected": payload.hotel_name if pack else "",
        "dates": {"start": d_start, "end": d_end},
        "pax": payload.pax.model_dump(),
        "services": services_sel,
        "contacts": payload.contacts.model_dump() if payload.contacts else None,
        "extra_nights_cfg": extra_cfg,
        "nights_total": calc["nights_total"],
        "extra_nights": calc["extra_nights"],
        "season_applied": calc.get("season_applied"),
        "items": calc["items"],
        "subtotal": calc["subtotal"],
        "commission": calc["commission"],
        "commission_rate": calc["commission_rate"],
        "total": calc["total"],
        "currency": calc["currency"],
        "state": "nueva_consulta",
        "archived": False,
        "deleted": False,
        "assigned_to": payload.assigned_to or user["id"],
        "created_by": user["id"],
        "notes": payload.notes,
        "history": [{
            "at": now_iso(), "user_id": user["id"], "user_name": user.get("name", ""),
            "action": "created", "detail": f"Cotización creada ({'servicios a la carta' if is_services else 'paquete'})",
        }],
        "last_activity_at": now_iso(),
        "created_at": now_iso(),
    }
    await db.quotations.insert_one(dict(doc))
    return doc


@api.patch("/quotations/{quotation_id}/state")
async def update_quotation_state(quotation_id: str, payload: QuotationStateUpdate, user: dict = Depends(require_tenant)):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    prev = q.get("state")
    await db.quotations.update_one(
        {"id": quotation_id, "tenant_id": user["tenant_id"]},
        {"$set": {"state": payload.state, "last_activity_at": now_iso()}},
    )
    STATE_LABELS = {
        "nueva_consulta": "Nueva consulta", "cotizando": "Cotizando", "enviada": "Enviada",
        "negociacion": "En negociación", "ganada": "Ganada", "perdida": "Perdida",
    }
    await _append_history(db, quotation_id, user, "state_change",
                          f"Estado: {STATE_LABELS.get(prev, prev)} → {STATE_LABELS.get(payload.state, payload.state)}")
    if payload.state == "ganada" and prev != "ganada":
        await _record_audit(db, user["tenant_id"], user, "won", q, "Marcada como ganada")
    return {"ok": True, "state": payload.state}


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


@api.patch("/quotations/{quotation_id}/pricing-adjust")
async def adjust_quotation_pricing(quotation_id: str, payload: QuotationPricingAdjust, user: dict = Depends(require_tenant)):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    discount = {"type": payload.discount_type, "value": payload.discount_value}
    final_total, amount = _apply_discount(float(q.get("total", 0) or 0), discount)
    discount["amount"] = amount
    await db.quotations.update_one(
        {"id": quotation_id, "tenant_id": user["tenant_id"]},
        {"$set": {"discount": discount, "final_total": final_total, "last_activity_at": now_iso()}},
    )
    dlabel = "sin descuento" if payload.discount_type == "none" else (
        f"{payload.discount_value}%" if payload.discount_type == "percent" else f"${payload.discount_value}")
    await _append_history(db, quotation_id, user, "discount", f"Descuento aplicado: {dlabel}")
    return await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})


@api.patch("/quotations/{quotation_id}")
async def update_quotation(quotation_id: str, payload: QuotationUpdate, user: dict = Depends(require_tenant)):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    # Recompute totals if pax/hotel/dates changed
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    changed_fields = [k for k in updates.keys()]
    if any(k in updates for k in ("pax", "hotel_name", "services", "dates", "extra_nights")):
        pack = None
        if q.get("package_id"):
            pack = await db.packages.find_one({"id": q["package_id"], "tenant_id": user["tenant_id"]}, {"_id": 0})
        client = await db.clients.find_one({"id": q["client_id"], "tenant_id": user["tenant_id"]}, {"_id": 0})
        company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
        pricing_config = company.get("pricing_config") or DEFAULT_PRICING_CONFIG
        hotel = updates.get("hotel_name", q["hotel_selected"])
        pax = updates.get("pax", q["pax"])
        services_sel = updates.get("services", q.get("services", []))
        new_dates = updates.get("dates", q.get("dates"))
        if new_dates and new_dates.get("start") and new_dates.get("end") and new_dates["start"] > new_dates["end"]:
            new_dates = {"start": new_dates["end"], "end": new_dates["start"]}
        extra_cfg = updates.get("extra_nights", q.get("extra_nights_cfg"))
        services_catalog = await _load_services_catalog(db, user["tenant_id"], services_sel)
        pack_nights = pack["nights"] if pack else 0
        calc = compute_quotation(pack, hotel, pax, pack_nights, client["channel"], pricing_config,
                                 services_catalog, services_sel,
                                 dates=new_dates, extra_nights_cfg=extra_cfg)
        updates.update({
            "hotel_selected": hotel if pack else "",
            "services": services_sel,
            "dates": new_dates,
            "extra_nights_cfg": extra_cfg,
            "nights_total": calc["nights_total"],
            "extra_nights": calc["extra_nights"],
            "season_applied": calc.get("season_applied"),
            "items": calc["items"], "subtotal": calc["subtotal"],
            "commission": calc["commission"], "commission_rate": calc["commission_rate"],
            "total": calc["total"],
        })
        updates.pop("hotel_name", None)
        # Re-apply an existing discount so final_total stays consistent
        if q.get("discount") and q["discount"].get("type") != "none":
            final_total, amount = _apply_discount(calc["total"], q["discount"])
            disc = dict(q["discount"]); disc["amount"] = amount
            updates["discount"] = disc
            updates["final_total"] = final_total
    updates["last_activity_at"] = now_iso()
    await db.quotations.update_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"$set": updates})
    if changed_fields:
        FIELD_ES = {"dates": "fechas", "pax": "habitaciones/pax", "services": "servicios",
                    "extra_nights": "noches extra", "hotel_name": "hotel", "contacts": "contactos",
                    "notes": "notas", "assigned_to": "responsable"}
        detail = "Editó: " + ", ".join(FIELD_ES.get(f, f) for f in changed_fields)
        await _append_history(db, quotation_id, user, "edited", detail)
    return await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})


@api.patch("/quotations/{quotation_id}/archive")
async def archive_quotation(quotation_id: str, payload: QuotationArchive, user: dict = Depends(require_tenant)):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    await db.quotations.update_one(
        {"id": quotation_id, "tenant_id": user["tenant_id"]},
        {"$set": {"archived": payload.archived, "last_activity_at": now_iso()}},
    )
    action = "archived" if payload.archived else "restored"
    await _append_history(db, quotation_id, user, action, "Archivada" if payload.archived else "Restaurada")
    await _record_audit(db, user["tenant_id"], user, action, q,
                        "Cotización archivada" if payload.archived else "Cotización restaurada")
    return {"ok": True, "archived": payload.archived}


@api.delete("/quotations/{quotation_id}")
async def delete_quotation(quotation_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    await db.quotations.update_one(
        {"id": quotation_id, "tenant_id": user["tenant_id"]},
        {"$set": {"deleted": True, "deleted_at": now_iso(), "deleted_by": user["id"]}},
    )
    await _record_audit(db, user["tenant_id"], user, "deleted", q, "Cotización eliminada")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Audit log (company_admin) — deleted / archived / won quotations
# ---------------------------------------------------------------------------
@api.get("/audit-log")
async def get_audit_log(action: str | None = None, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    q = {"tenant_id": user["tenant_id"]}
    if action:
        q["action"] = action
    return await db.audit_log.find(q, {"_id": 0}).sort("at", -1).to_list(500)


@api.get("/metrics/audit")
async def get_audit_metrics(user: dict = Depends(require_roles("company_admin"))):
    """Mini-dashboard: won this month, amount recovered, top executive."""
    db = get_db()
    tid = user["tenant_id"]
    now = datetime.now(timezone.utc)
    month_prefix = now.strftime("%Y-%m")
    quotations = await db.quotations.find(
        {"tenant_id": tid, "deleted": {"$ne": True}}, {"_id": 0}).to_list(2000)
    won = [q for q in quotations if q.get("state") == "ganada"]
    won_month = [q for q in won if (q.get("last_activity_at", "") or "").startswith(month_prefix)]
    amount_recovered = round(sum(float(q.get("amount_paid", 0) or 0) for q in quotations), 2)
    # top executive by won count
    counts: dict = {}
    for q in won:
        counts[q.get("assigned_to")] = counts.get(q.get("assigned_to"), 0) + 1
    top_id, top_count = (None, 0)
    if counts:
        top_id, top_count = max(counts.items(), key=lambda kv: kv[1])
    top_name = ""
    if top_id:
        u = await db.users.find_one({"id": top_id}, {"_id": 0, "name": 1})
        top_name = (u or {}).get("name", "")
    currency_code = (await db.companies.find_one({"id": tid}, {"_id": 0, "base_currency": 1}) or {}).get("base_currency", "MXN")
    return {
        "won_this_month": len(won_month),
        "won_total": len(won),
        "amount_recovered": amount_recovered,
        "currency": currency_code,
        "top_executive": {"name": top_name, "won": top_count} if top_name else None,
    }


@api.get("/quotations/{quotation_id}/pdf")
async def download_quotation_pdf(quotation_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    pack = None
    if q.get("package_id"):
        pack = await db.packages.find_one({"id": q["package_id"], "tenant_id": user["tenant_id"]}, {"_id": 0})
    client = await db.clients.find_one({"id": q["client_id"], "tenant_id": user["tenant_id"]}, {"_id": 0})
    pdf = generate_quotation_pdf(company, q, pack or {}, client or {"name": q.get("client_snapshot", {}).get("name", "")})
    return StreamingResponse(
        io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{q["code"]}.pdf"'},
    )


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
# Public quotation link (cliente acepta cotización con un click)
# ---------------------------------------------------------------------------
@api.post("/quotations/{quotation_id}/public-link")
async def create_public_link(quotation_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    token = secrets.token_urlsafe(18)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    public = {"token": token, "expires_at": expires_at, "created_at": now_iso(), "accepted_at": None}
    await db.quotations.update_one({"id": quotation_id}, {"$set": {"public_link": public}})
    return {"token": token, "expires_at": expires_at}


@api.delete("/quotations/{quotation_id}/public-link")
async def revoke_public_link(quotation_id: str, user: dict = Depends(require_tenant)):
    db = get_db()
    await db.quotations.update_one(
        {"id": quotation_id, "tenant_id": user["tenant_id"]},
        {"$unset": {"public_link": ""}},
    )
    return {"ok": True}


@api.get("/public/quotations/{token}")
async def get_public_quotation(token: str):
    db = get_db()
    q = await db.quotations.find_one({"public_link.token": token}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Enlace inválido")
    expires = q.get("public_link", {}).get("expires_at")
    if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Enlace expirado")
    company = await db.companies.find_one({"id": q["tenant_id"]}, {"_id": 0, "pricing_config": 0})
    pack = None
    if q.get("package_id"):
        pack = await db.packages.find_one({"id": q["package_id"]}, {"_id": 0})
    base_currency = company.get("base_currency", q.get("currency", "MXN"))
    final_total = q.get("final_total")
    if final_total is None:
        final_total = q.get("total", 0)
    amount_paid = q.get("amount_paid", 0) or 0
    payment_enabled = bool(((company.get("stripe") or {}).get("secret_key")) or os.environ.get("STRIPE_API_KEY"))
    bank = company.get("bank") or {}
    transfer_enabled = bool(bank.get("enabled")) and any(
        bank.get(k) for k in ("name", "clabe", "account", "usd_account"))
    rates = await currency.get_rates()
    total_usd = currency.convert(final_total, base_currency, "USD", rates) if base_currency == "MXN" else None
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
        },
        "company": {
            "name": company.get("name", ""), "logo_url": company.get("logo_url", ""),
            "primary_color": company.get("primary_color", "#185FA5"),
            "contact_email": company.get("contact_email", ""),
            "contact_phone": company.get("contact_phone", ""),
        },
        "payment": {
            "enabled": payment_enabled,
            "transfer_enabled": transfer_enabled,
            "base_currency": base_currency,
            "deposit_percent": company.get("deposit_percent", 50),
            "total_usd_equivalent": total_usd,
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
    }


@api.post("/public/quotations/{token}/accept")
async def accept_public_quotation(token: str):
    db = get_db()
    q = await db.quotations.find_one({"public_link.token": token}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Enlace inválido")
    expires = q.get("public_link", {}).get("expires_at")
    if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Enlace expirado")
    accepted_at = now_iso()
    was_won = q.get("state") == "ganada"
    await db.quotations.update_one(
        {"id": q["id"]},
        {"$set": {
            "state": "ganada",
            "public_link.accepted_at": accepted_at,
            "last_activity_at": accepted_at,
        }},
    )
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


@api.post("/public/quotations/{token}/request-transfer")
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


@api.patch("/quotations/{quotation_id}/mark-paid")
async def mark_quotation_paid(quotation_id: str, payload: ManualPaymentInput, user: dict = Depends(require_tenant)):
    """Executive manually registers a received payment (e.g. bank transfer)."""
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    amount_paid = round((q.get("amount_paid", 0) or 0) + float(payload.amount), 2)
    final_total = q.get("final_total")
    if final_total is None:
        final_total = q.get("total", 0)
    pay_status = "paid" if amount_paid >= round(final_total, 2) - 0.01 else "partial"
    was_won = q.get("state") == "ganada"
    updates = {"amount_paid": amount_paid, "payment_status": pay_status, "last_activity_at": now_iso()}
    if not was_won:
        updates["state"] = "ganada"
    await db.quotations.update_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"$set": updates})
    METHOD_ES = {"transfer": "transferencia", "cash": "efectivo", "card": "tarjeta", "other": "otro"}
    detail = f"Pago manual de {q.get('currency','MXN')} ${float(payload.amount):,.2f} ({METHOD_ES.get(payload.method, payload.method)})"
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


@api.post("/quotations/{quotation_id}/send-payment")
async def send_payment_link(quotation_id: str, payload: SendPaymentInput, user: dict = Depends(require_tenant)):
    """Email the client the public payment link (Stripe + transfer options)."""
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    # ensure a public link exists
    public = q.get("public_link")
    if not public or not public.get("token"):
        token = secrets.token_urlsafe(18)
        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        public = {"token": token, "expires_at": expires_at, "created_at": now_iso(), "accepted_at": None}
        await db.quotations.update_one({"id": quotation_id}, {"$set": {"public_link": public}})
    base = (payload.public_url or "").rstrip("/")
    link = f"{base}/q/{public['token']}" if base else f"/q/{public['token']}"
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    to = payload.to_email or await _client_email(db, q)
    if not to:
        raise HTTPException(status_code=400, detail="No hay correo del cliente. Agrega uno en el cliente o en los contactos.")
    final_total = q.get("final_total")
    if final_total is None:
        final_total = q.get("total", 0)
    title = f"Tu cotización {q.get('code')} — opciones de pago"
    html = (f"<h2>{company.get('name','')}</h2><p>Hola {q.get('client_snapshot',{}).get('name','')}, "
            f"aquí tienes tu cotización por <b>${float(final_total):,.2f} {q.get('currency','MXN')}</b>.</p>"
            f"<p><a href='{link}' style='background:#185FA5;color:#fff;padding:12px 20px;border-radius:10px;text-decoration:none'>Ver y pagar mi cotización</a></p>"
            f"<p style='color:#64748b;font-size:12px'>Podrás pagar con tarjeta o por transferencia bancaria.</p>")
    sent = await notifications.send_email(company, to, title, html)
    await _append_history(db, quotation_id, user, "sent_payment", f"Enlace de cobro enviado por correo a {to}")
    return {"ok": True, "email_sent": sent, "to": to, "link": link}


# ---------------------------------------------------------------------------
# Stripe payments (per-tenant key, partial/total from public link)
# ---------------------------------------------------------------------------
def _resolve_stripe_key(company: dict) -> str:
    sk = ((company or {}).get("stripe") or {}).get("secret_key")
    return sk or os.environ.get("STRIPE_API_KEY", "")


async def _apply_payment_to_quotation(txn: dict):
    """Idempotent: called only once per session_id (guarded by caller)."""
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


@api.post("/public/quotations/{token}/checkout")
async def public_checkout(token: str, payload: PublicCheckoutRequest, request: Request):
    db = get_db()
    q = await db.quotations.find_one({"public_link.token": token}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Enlace inválido")
    expires = q.get("public_link", {}).get("expires_at")
    if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Enlace expirado")
    company = await db.companies.find_one({"id": q["tenant_id"]}, {"_id": 0})
    api_key = _resolve_stripe_key(company)
    if not api_key:
        raise HTTPException(status_code=400, detail="Pagos no configurados para esta empresa")

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

    base_currency = (company.get("base_currency") or q.get("currency", "MXN")).lower()
    origin = payload.origin_url.rstrip("/")
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
        "amount": float(amount), "currency": base_currency.upper(),
        "pay_type": payload.pay_type, "metadata": metadata,
        "status": "initiated", "payment_status": "pending",
        "created_at": now_iso(),
    })
    return {"url": session.url, "session_id": session.session_id}


@api.get("/public/quotations/{token}/payment-status/{session_id}")
async def public_payment_status(token: str, session_id: str, request: Request):
    db = get_db()
    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not txn:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    company = await db.companies.find_one({"id": txn["tenant_id"]}, {"_id": 0})
    api_key = _resolve_stripe_key(company)
    stripe_status = None
    try:
        stripe_checkout = StripeCheckout(api_key=api_key, webhook_url="")
        st = await stripe_checkout.get_checkout_status(session_id)
        stripe_status = st
        if st.payment_status == "paid":
            flipped = await db.payment_transactions.find_one_and_update(
                {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                {"$set": {"payment_status": "paid", "status": st.status, "paid_at": now_iso()}},
            )
            if flipped is not None:
                await _apply_payment_to_quotation(flipped)
    except Exception as e:
        # The platform fallback key (sk_test_emergent) cannot retrieve sessions;
        # for real per-tenant keys this path works. Degrade to local txn (updated by webhook).
        log.info("payment-status: get_checkout_status fallback to local txn (%s): %s", session_id, e)

    # Re-read latest txn (may have been flipped by the webhook)
    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if stripe_status is not None:
        return {
            "payment_status": stripe_status.payment_status,
            "status": stripe_status.status,
            "amount_total": stripe_status.amount_total,
            "currency": stripe_status.currency,
        }
    is_paid = txn.get("payment_status") == "paid"
    return {
        "payment_status": "paid" if is_paid else "pending",
        "status": txn.get("status", "open"),
        "amount_total": int(round(float(txn["amount"]) * 100)),
        "currency": txn.get("currency", "MXN").lower(),
        "source": "local",
    }


@api.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    db = get_db()
    body = await request.body()
    sig = request.headers.get("Stripe-Signature")
    try:
        stripe_checkout = StripeCheckout(api_key=os.environ.get("STRIPE_API_KEY", ""), webhook_url="")
        event = await stripe_checkout.handle_webhook(body, sig)
        if event.payment_status == "paid":
            flipped = await db.payment_transactions.find_one_and_update(
                {"session_id": event.session_id, "payment_status": {"$ne": "paid"}},
                {"$set": {"payment_status": "paid", "status": "complete", "paid_at": now_iso()}},
            )
            if flipped is not None:
                await _apply_payment_to_quotation(flipped)
    except Exception as e:
        log.warning("stripe webhook error: %s", e)
    return {"ok": True}


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
    doc = await db.site_settings.find_one({"id": "default"}) or {"draft": {}, "published": {}}
    draft = doc.get("draft") or {}
    for section in ("landing", "login"):
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
# IA operativa (Claude Sonnet 4.5)
# ---------------------------------------------------------------------------
@api.post("/ai/chat-summary")
async def ai_chat_summary(payload: dict, user: dict = Depends(require_tenant)):
    messages = payload.get("messages") or []
    if not messages:
        raise HTTPException(status_code=400, detail="Sin mensajes")
    try:
        summary = await ai_service.summarize_chat(messages)
        return {"summary": summary}
    except Exception as e:
        log.exception("AI summary failed")
        raise HTTPException(status_code=503, detail=f"IA no disponible: {e}")


async def _load_quotation_context(quotation_id: str, tenant_id: str):
    db = get_db()
    q = await db.quotations.find_one({"id": quotation_id, "tenant_id": tenant_id}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    pack = await db.packages.find_one({"id": q["package_id"], "tenant_id": tenant_id}, {"_id": 0})
    client = await db.clients.find_one({"id": q["client_id"], "tenant_id": tenant_id}, {"_id": 0})
    # enrich days_idle
    try:
        last = datetime.fromisoformat(q.get("last_activity_at", q.get("created_at")))
        q["days_idle"] = (datetime.now(timezone.utc) - last).days
    except Exception:
        q["days_idle"] = 0
    return q, pack, client


@api.post("/ai/quotations/{quotation_id}/next-step")
async def ai_next_step(quotation_id: str, user: dict = Depends(require_tenant)):
    q, pack, client = await _load_quotation_context(quotation_id, user["tenant_id"])
    try:
        suggestion = await ai_service.suggest_next_step(q, pack, client)
        return {"suggestion": suggestion}
    except Exception as e:
        log.exception("AI next-step failed")
        raise HTTPException(status_code=503, detail=f"IA no disponible: {e}")


@api.post("/ai/quotations/{quotation_id}/missing-fields")
async def ai_missing_fields(quotation_id: str, user: dict = Depends(require_tenant)):
    q, pack, client = await _load_quotation_context(quotation_id, user["tenant_id"])
    try:
        fields = await ai_service.detect_missing_fields(q, pack, client)
        return {"fields": fields}
    except Exception as e:
        log.exception("AI missing-fields failed")
        raise HTTPException(status_code=503, detail=f"IA no disponible: {e}")


@api.post("/ai/quotations/{quotation_id}/client-message")
async def ai_client_message(quotation_id: str, user: dict = Depends(require_tenant)):
    q, pack, client = await _load_quotation_context(quotation_id, user["tenant_id"])
    try:
        msg = await ai_service.generate_client_message(q, pack, client)
        return {"message": msg}
    except Exception as e:
        log.exception("AI client-message failed")
        raise HTTPException(status_code=503, detail=f"IA no disponible: {e}")


# ---------------------------------------------------------------------------
# Router + CORS
# ---------------------------------------------------------------------------
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
