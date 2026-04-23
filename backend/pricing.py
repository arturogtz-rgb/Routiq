"""Pricing engine: calculates quotation totals based on a tenant's pricing config."""
from __future__ import annotations
from typing import Dict, Any


def compute_quotation(pack: dict, hotel_name: str, pax: dict, nights: int,
                      client_channel: str, pricing_config: dict) -> dict:
    """Given package, selected hotel, pax and channel, compute items, subtotal, commission, total."""
    hotel = next((h for h in pack.get("hotels", []) if h["name"] == hotel_name), None)
    if hotel is None:
        raise ValueError(f"Hotel '{hotel_name}' not found in package")

    ocupacion = pax.get("ocupacion", "doble")
    adultos = int(pax.get("adultos", 2))
    menores = int(pax.get("menores", 0))

    price_adult = float(hotel["prices_by_occupancy"].get(ocupacion, 0))
    price_minor = float(hotel.get("minor_price") or price_adult * (1 - pricing_config.get("minor_discount", 0.40)))

    items = []
    if adultos > 0:
        subtotal_adults = price_adult * adultos
        items.append({
            "label": f"{pack['name']} - {hotel['name']} ({ocupacion}) - Adulto",
            "unit_price": price_adult, "qty": adultos, "subtotal": subtotal_adults,
        })
    if menores > 0:
        subtotal_minors = price_minor * menores
        items.append({
            "label": f"{pack['name']} - {hotel['name']} - Menor",
            "unit_price": price_minor, "qty": menores, "subtotal": subtotal_minors,
        })

    subtotal = sum(it["subtotal"] for it in items)
    commission_rate = float(pricing_config.get("commissions", {}).get(client_channel, 0.0))
    commission = round(subtotal * commission_rate, 2)
    total = round(subtotal - commission, 2)

    return {
        "items": items,
        "subtotal": round(subtotal, 2),
        "commission": commission,
        "commission_rate": commission_rate,
        "total": total,
        "currency": pricing_config.get("currency", "MXN"),
    }
