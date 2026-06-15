"""Default editable content for the public Landing & Login pages.

Stored in the `site_settings` collection as a singleton doc with `draft` and
`published` copies so the Master admin can preview before publishing.
"""
from __future__ import annotations

DEFAULT_SITE = {
    "landing": {
        "hero_pill": "Cotiza, da seguimiento y cierra — sin perderte en WhatsApp",
        "hero_title": "La memoria operativa",
        "hero_highlight": "de tu tour operador.",
        "hero_subtitle": (
            "Routiq convierte tus chats de WhatsApp en cotizaciones estructuradas, con pipeline visual, "
            "PDF profesional y un motor de precios 100% configurable. Hecho para DMCs y operadores receptivos en Latinoamérica."
        ),
        "cta_primary": "Empezar ahora",
        "cta_secondary": "Ver características",
        "waitlist_text": "+30 tour operadores ya en lista de espera",
        "hero_image_url": "https://images.unsplash.com/photo-1745936720392-20a9af92a025?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NjZ8MHwxfHNlYXJjaHwyfHxhZ2F2ZSUyMGZpZWxkJTIwbGFuZHNjYXBlJTIwamFsaXNjb3xlbnwwfHx8fDE3NzY5ODQyNzN8MA&ixlib=rb-4.1.0&q=85",
        "feature_image_url": "https://images.unsplash.com/photo-1758518729685-f88df7890776?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NTYxODd8MHwxfHNlYXJjaHwzfHxwcm9mZXNzaW9uYWwlMjBidXNpbmVzcyUyMG1lZXRpbmclMjBvZmZpY2V8ZW58MHx8fHwxNzc2OTg0MjczfDA&ixlib=rb-4.1.0&q=85",
        "features_title": "Todo lo que tu equipo necesita antes de la venta.",
        "features_subtitle": "Fareharbor y Bokun resuelven la post-venta. Routiq cubre el hueco: desde el primer mensaje hasta el cierre.",
        "final_cta_title": "Digitaliza tu cotización hoy.",
        "final_cta_subtitle": "Reserva una demo de 20 min o entra directo con tus credenciales de prueba.",
        # Order + visibility of the optional landing sections. The Hero (top) and
        # Footer (bottom) are fixed; everything in between is reorderable/hideable.
        "sections": [
            {"key": "features", "label": "Características", "visible": True},
            {"key": "how", "label": "Cómo funciona", "visible": True},
            {"key": "pricing", "label": "Planes / Precios", "visible": True},
            {"key": "affiliates", "label": "Logos de empresas afiliadas", "visible": True},
            {"key": "final_cta", "label": "Llamado final (CTA)", "visible": True},
        ],
        # Affiliated-company logo carousel (managed from Master panel)
        "affiliates_title": "Empresas que ya operan con Routiq",
        "affiliate_logos": [],  # list of {"url": str, "name": str}
        # Editable Pricing / Planes section.
        "pricing_pill": "Planes",
        "pricing_title": "Precios simples que crecen con tu operación.",
        "pricing_subtitle": "MXN al mes por empresa. Sin costo por mensaje. Sin costo por usuario extra hasta el límite del plan.",
        "pricing_tiers": [
            {
                "name": "Starter", "price": "$890", "period": "/mes", "highlight": False, "cta": "Comenzar",
                "perks": ["1 número WhatsApp", "Hasta 3 ejecutivos", "Cotizaciones ilimitadas", "PDF con branding"],
            },
            {
                "name": "Pro", "price": "$1,890", "period": "/mes", "highlight": True, "cta": "Comenzar",
                "perks": ["Hasta 5 números", "Hasta 15 ejecutivos", "IA operativa", "Kanban + alertas", "Motor de precios avanzado"],
            },
            {
                "name": "Enterprise", "price": "A medida", "period": "/mes", "highlight": False, "cta": "Comenzar",
                "perks": ["Números ilimitados", "Meta API oficial", "SLA dedicado", "Onboarding + capacitación"],
            },
        ],
    },
    "login": {
        "logo_url": "",
        "primary_color": "#185FA5",
        "side_quote": "“Antes perdía cotizaciones en el chat. Ahora cierro 3x más rápido.”",
        "side_author": "— Piloto en producción: Aventúrate por Jalisco",
        "side_badge": "Para tour operadores",
        "welcome_title": "Bienvenido de vuelta",
        "welcome_subtitle": "Entra a tu panel de Routiq.",
    },
    "theme": {
        "preset": "corporate",
        "primary": "#185FA5",
    },
}


def merged_with_defaults(content: dict | None) -> dict:
    """Deep-merge stored content over defaults so new fields always have a value."""
    content = content or {}
    out = {}
    for section, fields in DEFAULT_SITE.items():
        merged = dict(fields)
        merged.update({k: v for k, v in (content.get(section) or {}).items() if v is not None})
        out[section] = merged
    # Reconcile the landing `sections` list so newly added default sections
    # (e.g. "affiliates") always appear even on previously-published content.
    default_sections = DEFAULT_SITE["landing"]["sections"]
    default_by_key = {s["key"]: s for s in default_sections}
    stored = out["landing"].get("sections") or []
    seen = set()
    reconciled = []
    for s in stored:
        if s.get("key") in default_by_key and s["key"] not in seen:
            reconciled.append({**default_by_key[s["key"]], **s})
            seen.add(s["key"])
    for s in default_sections:
        if s["key"] not in seen:
            reconciled.append(dict(s))
            seen.add(s["key"])
    # keep the final CTA last for a natural page flow
    reconciled.sort(key=lambda x: 1 if x["key"] == "final_cta" else 0)
    out["landing"]["sections"] = reconciled
    return out
