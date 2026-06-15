"""Pricing engine: supports single occupancy (legacy) and multi-room quotations."""
from __future__ import annotations
from typing import Dict, List

OCCUPANCY_COUNT = {"sencilla": 1, "doble": 2, "triple": 3, "cuadruple": 4}


def compute_quotation(pack: dict, hotel_name: str, pax: dict, nights: int,
                      client_channel: str, pricing_config: dict) -> dict:
    """Compute items, subtotal, commission, total.

    Supports two pax shapes:
      Legacy:  {adultos, menores, ocupacion}
      Multi-room:  {rooms: [{ocupacion, count}], menores}
    """
    hotel = next((h for h in pack.get("hotels", []) if h["name"] == hotel_name), None)
    if hotel is None:
        raise ValueError(f"Hotel '{hotel_name}' not found in package")

    rooms: List[dict] = pax.get("rooms") or []
    menores = int(pax.get("menores", 0))
    items: List[dict] = []

    if rooms:
        for room in rooms:
            ocupacion = room["ocupacion"]
            count = int(room.get("count", 1))
            occ_count = OCCUPANCY_COUNT[ocupacion]
            price_per_pax = float(hotel["prices_by_occupancy"].get(ocupacion, 0))
            pax_in_rooms = occ_count * count
            subtotal_room = price_per_pax * pax_in_rooms
            items.append({
                "label": f"{count} hab {ocupacion} × {occ_count} pax — {hotel['name']}",
                "unit_price": price_per_pax,
                "qty": pax_in_rooms,
                "rooms_count": count,
                "ocupacion": ocupacion,
                "subtotal": subtotal_room,
            })
    else:
        # legacy single-occupancy path
        ocupacion = pax.get("ocupacion", "doble")
        adultos = int(pax.get("adultos", 2))
        price_adult = float(hotel["prices_by_occupancy"].get(ocupacion, 0))
        if adultos > 0:
            items.append({
                "label": f"{pack['name']} - {hotel['name']} ({ocupacion}) - Adulto",
                "unit_price": price_adult, "qty": adultos, "subtotal": price_adult * adultos,
            })

    if menores > 0:
        price_minor = float(hotel.get("minor_price") or 0)
        items.append({
            "label": f"{hotel['name']} - Menor",
            "unit_price": price_minor, "qty": menores, "subtotal": price_minor * menores,
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
