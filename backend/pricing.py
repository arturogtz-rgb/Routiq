"""Pricing engine: multi-room hospedaje + a la carte services (by billing unit)
+ extra nights beyond the package duration."""
from __future__ import annotations
from datetime import date
from typing import List

OCCUPANCY_COUNT = {"sencilla": 1, "doble": 2, "triple": 3, "cuadruple": 4}

SERVICE_UNIT_ES = {
    "per_person": "por persona",
    "per_group": "por grupo",
    "per_day": "por día",
    "per_access": "por acceso",
}
EXTRA_UNIT_ES = {
    "per_person": "por persona",
    "per_room": "por habitación",
    "per_reservation": "por reservación",
}


def nights_between(start: str, end: str) -> int:
    try:
        s = date.fromisoformat((start or "")[:10])
        e = date.fromisoformat((end or "")[:10])
        return max(0, (e - s).days)
    except Exception:
        return 0


def _service_default_qty(unit: str, total_pax: int, pack_nights: int) -> int:
    if unit == "per_person":
        return max(1, total_pax)
    if unit == "per_access":
        return max(1, total_pax)
    if unit == "per_day":
        return max(1, pack_nights)
    return 1  # per_group


def resolve_hotel_prices(pack: dict, hotel: dict, checkin: str | None):
    """Return (prices_by_occupancy, minor_price, season_name) effective for the
    given check-in date. Applies a season override when the date falls inside one
    of the package's season ranges; otherwise uses the hotel's base prices."""
    base_prices = hotel.get("prices_by_occupancy", {})
    base_minor = float(hotel.get("minor_price", 0) or 0)
    seasons = pack.get("seasons") or []
    season_id = None
    season_name = None
    if checkin and seasons:
        ci = str(checkin)[:10]
        for s in seasons:
            for r in (s.get("ranges") or []):
                st = str(r.get("start") or "")[:10]
                en = str(r.get("end") or "")[:10]
                if st and en and st <= ci <= en:
                    season_id = s.get("id")
                    season_name = s.get("name")
                    break
            if season_id:
                break
    if season_id:
        sp = (hotel.get("season_prices") or {}).get(season_id)
        if sp:
            occ = {k: float(sp.get(k, base_prices.get(k, 0)) or 0) for k in ("sencilla", "doble", "triple", "cuadruple")}
            minor = float(sp.get("minor_price", base_minor) or 0)
            return occ, minor, season_name
    return base_prices, base_minor, season_name


def compute_quotation(pack: dict | None, hotel_name: str, pax: dict, nights: int,
                      client_channel: str, pricing_config: dict,
                      services_catalog: dict | None = None,
                      selected_services: list | None = None,
                      dates: dict | None = None,
                      extra_nights_cfg: dict | None = None) -> dict:
    """Returns items, subtotal, commission, total, plus nights_total / extra_nights.

    When `pack` is None the quotation is "servicios a la carta": there is no
    hospedaje nor extra nights; only the selected services are priced."""
    rooms: List[dict] = pax.get("rooms") or []
    menores = int(pax.get("menores", 0))
    items: List[dict] = []
    num_rooms = sum(int(r.get("count", 1)) for r in rooms) if rooms else 1
    season_name = None

    total_pax = (sum(OCCUPANCY_COUNT[r["ocupacion"]] * int(r.get("count", 1)) for r in rooms)
                 if rooms else int(pax.get("adultos", 0))) + menores

    nights_total = nights_between(dates.get("start"), dates.get("end")) if dates else int(nights or 0)
    if nights_total <= 0:
        nights_total = int(nights or 0)
    extra_nights = 0

    if pack is not None:
        hotel = next((h for h in pack.get("hotels", []) if h["name"] == hotel_name), None)
        if hotel is None:
            raise ValueError(f"Hotel '{hotel_name}' not found in package")

        checkin = dates.get("start") if dates else None
        eff_prices, eff_minor, season_name = resolve_hotel_prices(pack, hotel, checkin)

        if rooms:
            for room in rooms:
                ocupacion = room["ocupacion"]
                count = int(room.get("count", 1))
                occ_count = OCCUPANCY_COUNT[ocupacion]
                price_per_pax = float(eff_prices.get(ocupacion, 0))
                pax_in_rooms = occ_count * count
                items.append({
                    "label": f"{count} hab {ocupacion} × {occ_count} pax — {hotel['name']}",
                    "unit_price": price_per_pax, "qty": pax_in_rooms,
                    "rooms_count": count, "ocupacion": ocupacion, "kind": "hospedaje",
                    "subtotal": price_per_pax * pax_in_rooms,
                })
        else:
            ocupacion = pax.get("ocupacion", "doble")
            adultos = int(pax.get("adultos", 2))
            price_adult = float(eff_prices.get(ocupacion, 0))
            if adultos > 0:
                items.append({
                    "label": f"{pack['name']} - {hotel['name']} ({ocupacion}) - Adulto",
                    "unit_price": price_adult, "qty": adultos, "subtotal": price_adult * adultos,
                    "kind": "hospedaje",
                })

        if menores > 0:
            price_minor = float(eff_minor or 0)
            items.append({
                "label": f"{hotel['name']} - Menor",
                "unit_price": price_minor, "qty": menores, "subtotal": price_minor * menores,
                "kind": "hospedaje",
            })

        # ---- Extra nights (beyond package duration) ----
        extra_nights = max(0, nights_total - int(nights or 0))
        if extra_nights > 0 and extra_nights_cfg and float(extra_nights_cfg.get("cost_per_night", 0) or 0) > 0:
            cost = float(extra_nights_cfg["cost_per_night"])
            unit = extra_nights_cfg.get("unit", "per_reservation")
            mult = total_pax if unit == "per_person" else (num_rooms if unit == "per_room" else 1)
            qty = extra_nights * mult
            items.append({
                "label": f"Noche extra × {extra_nights} ({EXTRA_UNIT_ES.get(unit, unit)})",
                "unit_price": cost, "qty": qty, "subtotal": round(cost * qty, 2),
                "kind": "noche_extra", "extra_nights": extra_nights, "unit": unit,
            })

    # ---- A la carte services (by billing unit) ----
    services_catalog = services_catalog or {}
    for sel in (selected_services or []):
        svc = services_catalog.get(sel.get("service_id"))
        if not svc:
            continue
        unit = svc.get("unit") or ("per_person" if svc.get("per_person") else "per_group")
        sel_qty = int(sel.get("qty", 0) or 0)
        qty = sel_qty if sel_qty > 0 else _service_default_qty(unit, total_pax, int(nights or 0))
        price = float(svc.get("public_price") or 0)
        if qty <= 0:
            continue
        items.append({
            "label": f"{svc['name']} · {SERVICE_UNIT_ES.get(unit, '')}".strip(" ·"),
            "unit_price": price, "qty": qty, "kind": "servicio",
            "category": svc.get("category", "extra"), "unit": unit,
            "service_id": svc["id"], "subtotal": round(price * qty, 2),
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
        "nights_total": nights_total,
        "extra_nights": extra_nights,
        "season_applied": season_name,
    }
