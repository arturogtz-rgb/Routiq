"""Integrations routes: Stripe / Resend / bank transfer config + exchange rate."""
from fastapi import APIRouter, Depends, HTTPException

from database import get_db
from auth import require_roles
from models import CompanyIntegrationsUpdate
from deps import _integrations_view
import currency

router = APIRouter()


@router.get("/companies/me/integrations")
async def get_my_integrations(user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return _integrations_view(company)


@router.patch("/companies/me/integrations")
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
        # cannot enable Stripe if the Master plan doesn't allow it
        company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0, "stripe_allowed": 1})
        allowed = bool((company or {}).get("stripe_allowed", True))
        updates["stripe.enabled"] = bool(data["stripe_enabled"]) and allowed
    if "resend_api_key" in data and data["resend_api_key"]:
        if not data["resend_api_key"].startswith("••"):
            updates["resend.api_key"] = data["resend_api_key"]
    if "resend_from_email" in data:
        updates["resend.from_email"] = data["resend_from_email"] or ""
    if "resend_from_name" in data:
        updates["resend.from_name"] = data["resend_from_name"] or ""
    # Per-company SMTP email
    if "email_provider" in data and data["email_provider"]:
        updates["email_provider"] = data["email_provider"]
    _SMTP_FIELDS = {
        "smtp_host": "smtp.host", "smtp_username": "smtp.username",
        "smtp_from_email": "smtp.from_email", "smtp_from_name": "smtp.from_name",
    }
    for key, path in _SMTP_FIELDS.items():
        if key in data:
            updates[path] = data[key] or ""
    if "smtp_port" in data and data["smtp_port"]:
        updates["smtp.port"] = int(data["smtp_port"])
    if "smtp_use_tls" in data:
        updates["smtp.use_tls"] = bool(data["smtp_use_tls"])
    if "smtp_password" in data and data["smtp_password"] and not data["smtp_password"].startswith("••"):
        updates["smtp.password"] = data["smtp_password"]
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
        company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0, "transfer_allowed": 1})
        allowed = bool((company or {}).get("transfer_allowed", True))
        updates["bank.enabled"] = bool(data["bank_enabled"]) and allowed
    if updates:
        await db.companies.update_one({"id": user["tenant_id"]}, {"$set": updates})
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    return _integrations_view(company)


@router.get("/exchange-rate")
async def exchange_rate():
    return await currency.get_rates()
