"""Integrations routes: Stripe / Resend / bank transfer config + exchange rate."""
import re

from fastapi import APIRouter, Depends, HTTPException

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

from database import get_db
from auth import require_roles
from models import CompanyIntegrationsUpdate, SMTPTestInput
from deps import _integrations_view
import notifications
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
    # Gmail OAuth credentials (per company)
    if "gmail_client_id" in data:
        updates["gmail.client_id"] = data["gmail_client_id"] or ""
    if "gmail_client_secret" in data and data["gmail_client_secret"] and not data["gmail_client_secret"].startswith("••"):
        updates["gmail.client_secret"] = data["gmail_client_secret"]
    if "gmail_from_name" in data:
        updates["gmail.from_name"] = data["gmail_from_name"] or ""
    if "base_currency" in data and data["base_currency"]:
        updates["base_currency"] = data["base_currency"]
        # keep pricing currency in sync
        updates["pricing_config.currency"] = data["base_currency"]
    if "deposit_percent" in data and data["deposit_percent"]:
        updates["deposit_percent"] = float(data["deposit_percent"])
    if "notify_email" in data:
        val = (data["notify_email"] or "").strip()
        if val and not EMAIL_RE.match(val):
            raise HTTPException(status_code=400, detail="El correo de avisos debe ser una dirección válida (ej: reservas@tudominio.com)")
        updates["notify_email"] = val
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


@router.delete("/companies/me/integrations/stripe-secret")
async def clear_stripe_secret(user: dict = Depends(require_roles("company_admin"))):
    """Remove the saved Stripe secret key and disable Stripe (no SSH needed)."""
    db = get_db()
    await db.companies.update_one(
        {"id": user["tenant_id"]},
        {"$unset": {"stripe.secret_key": ""}, "$set": {"stripe.enabled": False}},
    )
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    return _integrations_view(company)

@router.post("/companies/me/test-smtp")
async def test_smtp(payload: SMTPTestInput, user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    password = payload.smtp_password
    if not password or password.startswith("••"):
        password = ((company.get("smtp") or {}).get("password")) or ""
    if not password:
        raise HTTPException(status_code=400, detail="Falta la contraseña SMTP. Ingrésala para enviar la prueba.")
    to_email = payload.to_email or payload.smtp_from_email or company.get("contact_email")
    if not to_email:
        raise HTTPException(status_code=400, detail="No hay correo destino para la prueba.")
    ok, err = await notifications.send_test_smtp(
        payload.smtp_host, payload.smtp_port, payload.smtp_username, password,
        payload.smtp_use_tls, payload.smtp_from_email, payload.smtp_from_name, to_email,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=f"No se pudo enviar: {err or 'error desconocido'}")
    return {"ok": True, "to": to_email}




@router.get("/exchange-rate")
async def exchange_rate():
    return await currency.get_rates()
