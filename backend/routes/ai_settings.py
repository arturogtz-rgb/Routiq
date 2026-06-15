"""Master-level AI provider settings (BYOK). Applies platform-wide.

Stores provider/model/api_key in `platform_settings` (doc id="ai").
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import get_db, now_iso
from auth import require_roles
import ai_service

log = logging.getLogger("routiq.ai_settings")
router = APIRouter()

VALID_PROVIDERS = ("anthropic", "openai", "google")


def _mask(key: str) -> str:
    if not key:
        return ""
    return f"••••{key[-4:]}" if len(key) > 4 else "••••"


@router.get("/master/ai-settings")
async def get_ai_settings(user: dict = Depends(require_roles("super_admin"))):
    doc = await get_db().platform_settings.find_one({"id": "ai"}, {"_id": 0}) or {}
    return {
        "provider": doc.get("provider", "anthropic"),
        "model": doc.get("model", ai_service.DEFAULT_MODELS["anthropic"]),
        "api_key_set": bool(doc.get("api_key")),
        "api_key_masked": _mask(doc.get("api_key", "")),
        "default_models": ai_service.DEFAULT_MODELS,
        "updated_at": doc.get("updated_at"),
    }


class AISettingsInput(BaseModel):
    provider: str
    model: str | None = None
    api_key: str | None = None


@router.patch("/master/ai-settings")
async def update_ai_settings(payload: AISettingsInput, user: dict = Depends(require_roles("super_admin"))):
    if payload.provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail="Proveedor inválido")
    db = get_db()
    updates = {
        "provider": payload.provider,
        "model": (payload.model or ai_service.DEFAULT_MODELS.get(payload.provider, "")).strip(),
        "updated_at": now_iso(),
    }
    if payload.api_key:  # only overwrite when a new key is provided
        updates["api_key"] = payload.api_key.strip()
    await db.platform_settings.update_one({"id": "ai"}, {"$set": updates, "$setOnInsert": {"id": "ai"}}, upsert=True)
    doc = await db.platform_settings.find_one({"id": "ai"}, {"_id": 0})
    return {
        "provider": doc.get("provider"), "model": doc.get("model"),
        "api_key_set": bool(doc.get("api_key")), "api_key_masked": _mask(doc.get("api_key", "")),
    }


class AITestInput(BaseModel):
    provider: str
    model: str | None = None
    api_key: str | None = None


@router.post("/master/ai-settings/test")
async def test_ai_settings(payload: AITestInput, user: dict = Depends(require_roles("super_admin"))):
    if payload.provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail="Proveedor inválido")
    # use provided key, or fall back to stored key
    api_key = payload.api_key
    model = payload.model
    if not api_key:
        doc = await get_db().platform_settings.find_one({"id": "ai"}, {"_id": 0}) or {}
        api_key = doc.get("api_key", "")
        model = model or doc.get("model")
    if not api_key:
        raise HTTPException(status_code=400, detail="Ingresa una API key para probar la conexión.")
    try:
        out = await ai_service.test_connection(payload.provider, model or "", api_key)
        return {"ok": True, "reply": out}
    except (ai_service.AINotConfigured, ai_service.AIError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        log.exception("AI test failed")
        raise HTTPException(status_code=400, detail=f"Error: {str(e)[:200]}")
