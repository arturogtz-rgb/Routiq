"""IA operativa con Claude Sonnet 4.5 via Emergent Universal LLM Key."""
from __future__ import annotations
import os
import json
import uuid
import logging
from emergentintegrations.llm.chat import LlmChat, UserMessage

log = logging.getLogger("routiq.ai")

MODEL_PROVIDER = "anthropic"
MODEL_NAME = "claude-sonnet-4-5-20250929"


def _new_chat(system: str) -> LlmChat:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY no configurada")
    return LlmChat(
        api_key=api_key,
        session_id=f"routiq-{uuid.uuid4().hex[:12]}",
        system_message=system,
    ).with_model(MODEL_PROVIDER, MODEL_NAME)


def _money(v: float, c: str = "MXN") -> str:
    return f"${float(v or 0):,.0f} {c}"


def _quotation_brief(q: dict, pack: dict | None = None, client: dict | None = None) -> str:
    """Resumen compacto en texto de una cotización para el contexto del LLM."""
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


async def _ask(chat: LlmChat, prompt: str) -> str:
    """Send a message and concatenate the full response."""
    response = await chat.send_message(UserMessage(text=prompt))
    return response.strip() if isinstance(response, str) else str(response).strip()


async def summarize_chat(messages: list[dict], language: str = "es") -> str:
    """Resumen del chat de WhatsApp en 2 frases."""
    system = (
        "Eres un asistente de ventas para una empresa de turismo en México. "
        "Tu trabajo es leer conversaciones cortas de WhatsApp y resumirlas en máximo 2 frases en español, "
        "capturando: intención del cliente, fechas o pax mencionados, y cualquier objeción o duda."
    )
    chat = _new_chat(system)
    conv = "\n".join(f"{'Cliente' if not m.get('me') else 'Ejecutivo'}: {m.get('body','')}" for m in messages)
    return await _ask(chat, f"Resume esta conversación:\n\n{conv}")


async def suggest_next_step(q: dict, pack: dict | None = None, client: dict | None = None) -> str:
    """Sugiere el siguiente paso del ejecutivo en 1-2 frases."""
    system = (
        "Eres coach de ventas para un tour operador en México. Sugiere el siguiente paso concreto y accionable "
        "que el ejecutivo debe hacer, en 1 o 2 frases. Tono cercano, profesional y directo. Español de México."
    )
    chat = _new_chat(system)
    brief = _quotation_brief(q, pack, client)
    return await _ask(chat, f"Cotización actual:\n{brief}\n\n¿Cuál es el siguiente paso recomendado?")


async def detect_missing_fields(q: dict, pack: dict | None = None, client: dict | None = None) -> list[str]:
    """Devuelve lista de campos importantes que faltan/son débiles."""
    system = (
        "Eres asistente operativo de un tour operador. Devuelve SOLO un JSON array de strings (sin texto extra) "
        "listando los campos críticos que faltan o son débiles en esta cotización y que el ejecutivo debería "
        "aclarar con el cliente antes de cerrar. Máximo 5 ítems. Español, frases cortas."
    )
    chat = _new_chat(system)
    brief = _quotation_brief(q, pack, client)
    raw = await _ask(chat, f"Cotización:\n{brief}\n\nDevuelve JSON array de campos faltantes.")
    try:
        # remove markdown code fences if present
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        if isinstance(result, list):
            return [str(x) for x in result][:5]
    except Exception as e:
        log.warning(f"AI returned non-JSON: {raw[:200]} ({e})")
    return [raw[:200]] if raw else []


async def generate_client_message(q: dict, pack: dict | None = None, client: dict | None = None) -> str:
    """Borrador de mensaje WhatsApp para enviar al cliente."""
    system = (
        "Eres ejecutivo de ventas amable y profesional de un tour operador en México. "
        "Redacta un mensaje de WhatsApp de unas 80 palabras, en español de México, tono cercano (tutea), "
        "vendiendo la cotización con un CTA claro al final tipo '¿lo confirmamos?'. "
        "No uses emojis excesivos (máximo 2). Empieza con un saludo personalizado."
    )
    chat = _new_chat(system)
    brief = _quotation_brief(q, pack, client)
    return await _ask(chat, f"Cotización:\n{brief}\n\nRedacta el mensaje:")
