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

CUSTOM_UNIT_ES = {
    "per_person": "por persona",
    "per_night": "por noche",
    "per_room": "por habitación",
    "per_group": "por grupo",
    "per_day": "por día",
    "per_vehicle": "por vehículo",
}
CUSTOM_CATEGORY_ES = {
    "hospedaje": "Hospedaje",
    "traslado": "Traslado",
    "tour": "Tour",
    "acceso": "Acceso",
    "extra": "Extra",
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


def public_from_net(net: float, margin_divisor: float) -> float:
    """Precio público = tarifa neta / divisor de margen."""
    return round(net / margin_divisor, 2) if margin_divisor and margin_divisor > 0 else round(net, 2)


def channel_price(net: float, channel: str, margin_divisor: float, commissions: dict) -> float:
    """Precio que VE el cliente para un concepto NETO de paquete, según su canal:
      - directo / agencia  -> Precio Público (neto / divisor), sin comisión.
      - mayorista          -> Precio Público - comisión mayorista (configurable). No comisionable.
      - operador (Mayorista Preferencial) -> Tarifa Neta original. No comisionable.
    """
    pub = public_from_net(net, margin_divisor)
    if channel == "operador":
        return round(net, 2)
    if channel == "mayorista":
        rate = float((commissions or {}).get("mayorista", 0.0) or 0.0)
        return round(pub * (1 - rate), 2)
    return pub  # directo, agencia y cualquier otro


_OCC_LABEL = {"sencilla": "Sencilla", "doble": "Doble", "triple": "Triple", "cuadruple": "Cuádruple"}


def occupancy_rows_selected(items: list) -> list:
    """Filas de ocupación SELECCIONADAS (a partir de los items de la cotización):
    cada fila trae precio por persona y total. Solo conceptos de hospedaje."""
    rows = []
    for it in (items or []):
        if it.get("kind") != "hospedaje":
            continue
        occ = it.get("ocupacion")
        if occ:
            rc = int(it.get("rooms_count", 1) or 1)
            label = (f"{rc} hab " if rc > 1 else "") + _OCC_LABEL.get(occ, occ.capitalize())
        elif "Menor" in (it.get("label", "") or ""):
            label = "Menor"
        else:
            label = it.get("label", "")
        rows.append({"label": label, "per_person": it.get("unit_price", 0), "total": it.get("subtotal", 0)})
    return rows


def occupancy_rows_all(hotel: dict, channel: str, margin_divisor: float, commissions: dict) -> list:
    """Todas las ocupaciones DISPONIBLES del hotel (precio por persona según canal),
    para cotizaciones abiertas. Omite ocupaciones con precio 0 (no disponible)."""
    rows = []
    prices = (hotel or {}).get("prices_by_occupancy", {}) or {}
    for key, label in [("sencilla", "Sencilla"), ("doble", "Doble"), ("triple", "Triple"), ("cuadruple", "Cuádruple")]:
        net = float(prices.get(key, 0) or 0)
        if net <= 0:
            continue
        rows.append({"key": key, "label": label, "per_person": channel_price(net, channel, margin_divisor, commissions), "total": None})
    minor = float((hotel or {}).get("minor_price", 0) or 0)
    if minor > 0:
        rows.append({"key": "menor", "label": "Menor", "per_person": channel_price(minor, channel, margin_divisor, commissions), "total": None})
    return rows



def _price_custom_item(ci: dict, total_pax: int, nights_total: int, rooms: int,
                       client_channel: str, margin_divisor: float, commissions: dict,
                       custom_engine: bool = False) -> dict:
    """Cotiza un concepto libre (programa personalizado o extra de paquete).

    custom_engine=True (Programa Personalizado / Cotización a medida): el subtotal es
    `precio × multiplicador`, donde el multiplicador depende ÚNICAMENTE de la unidad de cobro:
      - per_night  -> número de noches (único caso donde las noches multiplican)
      - per_group  -> 1 (precio único)
      - per_room / per_person / per_day / per_vehicle -> la cantidad ingresada
    Check-in / check-out / noches son informativos y NO multiplican (salvo per_night).
    custom_engine=False (extras de Paquete Armado / Servicios): comportamiento histórico intacto.
    """
    entered = float(ci.get("net_price", 0) or 0)
    price_type = ci.get("price_type", "neto") or "neto"
    unit = ci.get("unit") or "per_group"
    category = ci.get("category", "extra")
    nights = int(ci.get("nights", 0) or 0)
    sel_qty = int(ci.get("qty", 0) or 0)
    name = (ci.get("name") or "").strip() or CUSTOM_CATEGORY_ES.get(category, "Concepto")
    if price_type == "publico":
        unit_price = round(entered, 2)
        public_ref = round(entered, 2)
    else:
        unit_price = channel_price(entered, client_channel, margin_divisor, commissions)
        public_ref = public_from_net(entered, margin_divisor)
    if custom_engine:
        # Multiplicador por unidad de cobro (las noches solo cuentan en per_night).
        if unit == "per_night":
            qty = nights
        elif unit == "per_group":
            qty = 1
        else:
            qty = sel_qty if sel_qty > 0 else _custom_default_qty(unit, total_pax, nights_total, rooms)
        subtotal = round(unit_price * qty, 2)
    else:
        if category == "hospedaje":
            qty = sel_qty if sel_qty > 0 else 1
        else:
            qty = sel_qty if sel_qty > 0 else _custom_default_qty(unit, total_pax, nights_total, rooms)
        if category == "hospedaje" and nights > 0:
            subtotal = round(unit_price * qty * nights, 2)
        else:
            subtotal = round(unit_price * qty, 2)
    return {
        "label": f"{name} · {CUSTOM_UNIT_ES.get(unit, '')}".strip(" ·"),
        "unit_price": unit_price, "qty": qty, "kind": "custom",
        "category": category, "unit": unit,
        "name": name, "description": ci.get("description", "") or "",
        "net_price": entered, "public_price": public_ref, "price_type": price_type,
        "subtotal": subtotal,
        "service_date": ci.get("service_date", "") or "",
        "start_time": ci.get("start_time", "") or "",
        "end_time": ci.get("end_time", "") or "",
        "checkin": ci.get("checkin", "") or "",
        "checkout": ci.get("checkout", "") or "",
        "nights": nights,
    }


def compute_quotation(pack: dict | None, hotel_name: str, pax: dict, nights: int,
                      client_channel: str, pricing_config: dict,
                      services_catalog: dict | None = None,
                      selected_services: list | None = None,
                      dates: dict | None = None,
                      extra_nights_cfg: dict | None = None,
                      custom_items: list | None = None) -> dict:
    """Returns items, subtotal, commission, total, plus nights_total / extra_nights.

    When `pack` is None the quotation is "servicios a la carta": there is no
    hospedaje nor extra nights; only the selected services are priced."""
    rooms: List[dict] = pax.get("rooms") or []
    menores = int(pax.get("menores", 0))
    items: List[dict] = []
    num_rooms = sum(int(r.get("count", 1)) for r in rooms) if rooms else 1
    season_name = None

    # --- Channel pricing (PAQUETES): catálogo guarda TARIFAS NETAS ---
    margin_divisor = float(pricing_config.get("margin_divisor", 0.76) or 0.76)
    commissions = pricing_config.get("commissions", {}) or {}

    def _chan(net: float) -> float:
        return channel_price(net, client_channel, margin_divisor, commissions)

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
                net_per_pax = float(eff_prices.get(ocupacion, 0) or 0)
                if net_per_pax <= 0:
                    continue  # precio 0 = no disponible -> se omite
                price_per_pax = _chan(net_per_pax)
                pax_in_rooms = occ_count * count
                items.append({
                    "label": f"{count} hab {ocupacion} × {occ_count} pax — {hotel['name']}",
                    "unit_price": price_per_pax, "qty": pax_in_rooms,
                    "net_price": net_per_pax, "public_price": public_from_net(net_per_pax, margin_divisor),
                    "rooms_count": count, "ocupacion": ocupacion, "kind": "hospedaje",
                    "subtotal": round(price_per_pax * pax_in_rooms, 2),
                })
        else:
            ocupacion = pax.get("ocupacion", "doble")
            adultos = int(pax.get("adultos", 2))
            net_adult = float(eff_prices.get(ocupacion, 0) or 0)
            if adultos > 0 and net_adult > 0:
                price_adult = _chan(net_adult)
                items.append({
                    "label": f"{pack['name']} - {hotel['name']} ({ocupacion}) - Adulto",
                    "unit_price": price_adult, "qty": adultos, "subtotal": round(price_adult * adultos, 2),
                    "net_price": net_adult, "public_price": public_from_net(net_adult, margin_divisor),
                    "kind": "hospedaje",
                })

        if menores > 0:
            net_minor = float(eff_minor or 0)
            if net_minor > 0:
                price_minor = _chan(net_minor)
                items.append({
                    "label": f"{hotel['name']} - Menor",
                    "unit_price": price_minor, "qty": menores, "subtotal": round(price_minor * menores, 2),
                    "net_price": net_minor, "public_price": public_from_net(net_minor, margin_divisor),
                    "kind": "hospedaje",
                })

        # ---- Extra nights (beyond package duration) ----
        extra_nights = max(0, nights_total - int(nights or 0))
        if extra_nights > 0 and extra_nights_cfg and float(extra_nights_cfg.get("cost_per_night", 0) or 0) > 0:
            cost_net = float(extra_nights_cfg["cost_per_night"])
            cost = _chan(cost_net)
            unit = extra_nights_cfg.get("unit", "per_reservation")
            mult = total_pax if unit == "per_person" else (num_rooms if unit == "per_room" else 1)
            qty = extra_nights * mult
            items.append({
                "label": f"Noche extra × {extra_nights} ({EXTRA_UNIT_ES.get(unit, unit)})",
                "unit_price": cost, "qty": qty, "subtotal": round(cost * qty, 2),
                "net_price": cost_net, "public_price": public_from_net(cost_net, margin_divisor),
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

    # ---- Conceptos adicionales libres (extras del paquete / a la carta) ----
    for ci in (custom_items or []):
        items.append(_price_custom_item(ci, total_pax, nights_total, num_rooms,
                                        client_channel, margin_divisor, commissions))

    # Comisión por canal SOLO sobre servicios a la carta (los paquetes ya traen
    # el precio por canal incorporado y son "neto no comisionable").
    package_subtotal = sum(it["subtotal"] for it in items if it.get("kind") in ("hospedaje", "noche_extra"))
    service_subtotal = sum(it["subtotal"] for it in items if it.get("kind") == "servicio")
    custom_publico = sum(it["subtotal"] for it in items if it.get("kind") == "custom" and it.get("price_type") == "publico")
    custom_neto = sum(it["subtotal"] for it in items if it.get("kind") == "custom" and it.get("price_type", "neto") != "publico")
    commission_rate = float(commissions.get(client_channel, 0.0) or 0.0)
    commission = round((service_subtotal + custom_publico) * commission_rate, 2)
    subtotal = round(package_subtotal + service_subtotal + custom_publico + custom_neto, 2)
    total = round(subtotal - commission, 2)

    has_package = pack is not None
    if has_package and client_channel == "agencia":
        price_note = "Precio comisionable"
    elif has_package and client_channel in ("mayorista", "operador"):
        price_note = "Precio neto no comisionable"
    else:
        price_note = ""

    return {
        "items": items,
        "subtotal": subtotal,
        "commission": commission,
        "commission_rate": commission_rate,
        "total": total,
        "currency": pricing_config.get("currency", "MXN"),
        "nights_total": nights_total,
        "extra_nights": extra_nights,
        "season_applied": season_name,
        "price_note": price_note,
    }


def _custom_default_qty(unit: str, total_pax: int, nights: int, rooms: int) -> int:
    if unit == "per_person":
        return max(1, total_pax)
    if unit in ("per_night", "per_day"):
        return max(1, nights)
    if unit == "per_room":
        return max(1, rooms)
    return 1  # per_group / per_vehicle


def compute_custom_quotation(custom_items: list, pax: dict, custom_nights: int,
                             custom_rooms: int, client_channel: str, pricing_config: dict,
                             dates: dict | None = None) -> dict:
    """Free-form "programa personalizado": cada concepto define un monto + unidad
    y un TIPO DE PRECIO:
      - 'neto'    -> lógica de paquetes: público = neto/divisor, luego precio por canal (no comisionable).
      - 'publico' -> lógica de servicios: el monto YA es público y se le descuenta la comisión por canal.
    Se pueden mezclar ambos tipos en la misma cotización."""
    margin_divisor = float(pricing_config.get("margin_divisor", 0.76) or 0.76)
    commissions = pricing_config.get("commissions", {}) or {}
    menores = int(pax.get("menores", 0) or 0)
    total_pax = int(pax.get("adultos", 0) or 0) + menores

    nights_total = nights_between(dates.get("start"), dates.get("end")) if dates else 0
    if nights_total <= 0:
        nights_total = int(custom_nights or 0)
    rooms = int(custom_rooms or 0)

    items: List[dict] = []
    for ci in (custom_items or []):
        items.append(_price_custom_item(ci, total_pax, nights_total, rooms,
                                        client_channel, margin_divisor, commissions,
                                        custom_engine=True))

    # Comisión por canal SOLO sobre conceptos de precio público (los netos ya traen el
    # precio por canal incorporado y son "no comisionables").
    publico_subtotal = sum(it["subtotal"] for it in items if it.get("price_type") == "publico")
    neto_subtotal = sum(it["subtotal"] for it in items if it.get("price_type", "neto") != "publico")
    commission_rate = float(commissions.get(client_channel, 0.0) or 0.0)
    commission = round(publico_subtotal * commission_rate, 2)
    subtotal = round(neto_subtotal + publico_subtotal, 2)
    total = round(subtotal - commission, 2)

    has_neto = any(it.get("price_type", "neto") != "publico" for it in items)
    has_publico = any(it.get("price_type") == "publico" for it in items)
    if has_neto and client_channel in ("mayorista", "operador"):
        price_note = "Precio neto no comisionable"
    elif client_channel == "agencia" and (has_neto or has_publico):
        price_note = "Precio comisionable"
    else:
        price_note = ""

    return {
        "items": items,
        "subtotal": subtotal,
        "commission": commission,
        "commission_rate": commission_rate,
        "total": total,
        "currency": pricing_config.get("currency", "MXN"),
        "nights_total": nights_total,
        "extra_nights": 0,
        "season_applied": None,
        "price_note": price_note,
    }
