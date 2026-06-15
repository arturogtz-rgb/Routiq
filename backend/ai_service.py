"""IA operativa BYOK (Bring Your Own Key).

El proveedor (Anthropic / OpenAI / Google), el modelo y la API key se configuran
desde el Panel Master y se guardan en `platform_settings` (doc id="ai"). Aplica a
todas las empresas. Independiente de Emergent.
"""
from __future__ import annotations
import json
import logging

from database import get_db

log = logging.getLogger("routiq.ai")

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o",
    "google": "gemini-1.5-pro",
}

NOT_CONFIGURED_MSG = (
    "La IA no está configurada. Pide al administrador de Routiq que configure el "
    "proveedor y la API key en el Panel Master (Ajustes → Inteligencia Artificial)."
)


class AINotConfigured(Exception):
    pass


class AIError(Exception):
    pass


async def get_ai_config() -> dict | None:
    """Lee la config global de IA. Devuelve dict o None si no hay key."""
    doc = await get_db().platform_settings.find_one({"id": "ai"}, {"_id": 0})
    if not doc or not doc.get("api_key"):
        return None
    return {
        "provider": doc.get("provider", "anthropic"),
        "model": doc.get("model") or DEFAULT_MODELS.get(doc.get("provider", "anthropic"), "claude-sonnet-4-5"),
        "api_key": doc["api_key"],
    }


def _map_provider_error(provider: str, e: Exception) -> Exception:
    msg = str(e).lower()
    if any(k in msg for k in ("api key", "api-key", "apikey", "401", "403", "unauthorized", "authentication", "permission")):
        return AIError(f"La API key de {provider.capitalize()} no es válida o no tiene permisos. Actualízala en el Panel Master.")
    if "quota" in msg or "billing" in msg or "insufficient" in msg or "429" in msg:
        return AIError(f"La cuenta de {provider.capitalize()} no tiene saldo/cuota disponible.")
    return AIError(f"No se pudo conectar con {provider.capitalize()}: {str(e)[:200]}")


async def _complete(provider: str, model: str, api_key: str, system: str, prompt: str, max_tokens: int = 700) -> str:
    """Llamada de completado para el proveedor indicado. Lanza AIError en fallo."""
    try:
        if provider == "anthropic":
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model=model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            return (resp.content[0].text if resp.content else "").strip()

        if provider == "openai":
            import openai
            client = openai.AsyncOpenAI(api_key=api_key)
            resp = await client.chat.completions.create(
                model=model, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            )
            return (resp.choices[0].message.content or "").strip()

        if provider == "google":
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=api_key)
            resp = await client.aio.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens),
            )
            return (resp.text or "").strip()

        raise AIError(f"Proveedor de IA desconocido: {provider}")
    except (AINotConfigured, AIError):
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("AI provider error (%s/%s): %s", provider, model, e)
        raise _map_provider_error(provider, e)


async def _ask(system: str, prompt: str, max_tokens: int = 700) -> str:
    cfg = await get_ai_config()
    if not cfg:
        raise AINotConfigured(NOT_CONFIGURED_MSG)
    return await _complete(cfg["provider"], cfg["model"], cfg["api_key"], system, prompt, max_tokens)


async def test_connection(provider: str, model: str, api_key: str) -> str:
    """Llamada de prueba con la key/modelo dados. Lanza AIError si falla."""
    if not api_key:
        raise AINotConfigured("Falta la API key.")
    model = model or DEFAULT_MODELS.get(provider, "")
    if not model:
        raise AIError("Falta el nombre del modelo.")
    system = "Eres un asistente que responde en español de México, breve y claro."
    out = await _complete(provider, model, api_key, system,
                          "Responde solo con: 'Conexión exitosa con Routiq.'", max_tokens=64)
    return out or "OK"


def _money(v: float, c: str = "MXN") -> str:
    return f"${float(v or 0):,.0f} {c}"


def _quotation_brief(q: dict, pack: dict | None = None, client: dict | None = None) -> str:
    parts = []
    if client:
        parts.append(f"Cliente: {client.get('name','?')} ({client.get('channel','directo')})")
    parts.append(f"Paquete: {q.get('package_snapshot',{}).get('name','?')}")
    parts.append(f"Hotel: {q.get('hotel_selected','?')}")
    parts.append(f"Fechas: {q.get('dates',{}).get('start','?')} → {q.get('dates',{}).get('end','?')}")
    pax = q.get("pax", {})
    if pax.get("rooms"):
        rooms_desc = ", ".join(f"{r['count']} {r['ocupacion']}" for r in pax["rooms"])
        parts.append(f"Habitaciones: {rooms_desc}")
    else:
        parts.append(f"Pax: {pax.get('adultos',0)} adultos, {pax.get('menores',0)} menores ({pax.get('ocupacion','?')})")
    parts.append(f"Total: {_money(q.get('total',0), q.get('currency','MXN'))}")
    parts.append(f"Estado: {q.get('state','?')} ({q.get('days_idle','?')} días sin movimiento)")
    if q.get("notes"):
        parts.append(f"Notas: {q['notes']}")
    return "\n".join(parts)


async def summarize_chat(messages: list[dict], language: str = "es") -> str:
    system = (
        "Eres un asistente de ventas para una empresa de turismo en México. "
        "Tu trabajo es leer conversaciones cortas de WhatsApp y resumirlas en máximo 2 frases en español, "
        "capturando: intención del cliente, fechas o pax mencionados, y cualquier objeción o duda."
    )
    conv = "\n".join(f"{'Cliente' if not m.get('me') else 'Ejecutivo'}: {m.get('body','')}" for m in messages)
    return await _ask(system, f"Resume esta conversación:\n\n{conv}", max_tokens=300)


async def suggest_next_step(q: dict, pack: dict | None = None, client: dict | None = None) -> str:
    system = (
        "Eres coach de ventas para un tour operador en México. Sugiere el siguiente paso concreto y accionable "
        "que el ejecutivo debe hacer, en 1 o 2 frases. Tono cercano, profesional y directo. Español de México."
    )
    brief = _quotation_brief(q, pack, client)
    return await _ask(system, f"Cotización actual:\n{brief}\n\n¿Cuál es el siguiente paso recomendado?", max_tokens=300)


async def detect_missing_fields(q: dict, pack: dict | None = None, client: dict | None = None) -> list[str]:
    system = (
        "Eres asistente operativo de un tour operador. Devuelve SOLO un JSON array de strings (sin texto extra) "
        "listando los campos críticos que faltan o son débiles en esta cotización y que el ejecutivo debería "
        "aclarar con el cliente antes de cerrar. Máximo 5 ítems. Español, frases cortas."
    )
    brief = _quotation_brief(q, pack, client)
    raw = await _ask(system, f"Cotización:\n{brief}\n\nDevuelve JSON array de campos faltantes.", max_tokens=300)
    try:
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        if isinstance(result, list):
            return [str(x) for x in result][:5]
    except Exception as e:
        log.warning(f"AI returned non-JSON: {raw[:200]} ({e})")
    return [raw[:200]] if raw else []


async def generate_client_message(q: dict, pack: dict | None = None, client: dict | None = None) -> str:
    system = (
        "Eres ejecutivo de ventas amable y profesional de un tour operador en México. "
        "Redacta un mensaje de WhatsApp de unas 80 palabras, en español de México, tono cercano (tutea), "
        "vendiendo la cotización con un CTA claro al final tipo '¿lo confirmamos?'. "
        "No uses emojis excesivos (máximo 2). Empieza con un saludo personalizado."
    )
    brief = _quotation_brief(q, pack, client)
    return await _ask(system, f"Cotización:\n{brief}\n\nRedacta el mensaje:", max_tokens=400)
