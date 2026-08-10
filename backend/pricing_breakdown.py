"""Presentation-only helper: "precio por persona según ocupación".

IMPORTANT: this does NOT touch the pricing engine (pricing.py). It only CONSUMES
the already-computed quotation results (items + total) and reorganizes them into a
per-person view. The grand total is guaranteed to match the quotation total exactly
(rounding residual is absorbed in the largest row).

Business logic (per the spec):
- Lodging is the only component that differs per person by occupancy: the engine
  already stores hospedaje items with `ocupacion` and per-pax `unit_price`.
- Everything else (group/vehicle/room/night services, custom items, extra nights,
  commission and discount deltas) is uniform per person: group costs split across all
  pax and per-person costs assigned per person both yield the SAME per-person amount,
  so we distribute the remaining pool evenly across all pax.
"""

OCC_LABEL = {"sencilla": "Sencilla", "doble": "Doble", "triple": "Triple", "cuadruple": "Cuádruple"}
OCC_COUNT = {"sencilla": 1, "doble": 2, "triple": 3, "cuadruple": 4}


def _pax_total_from_pax(pax: dict) -> int:
    pax = pax or {}
    rooms = pax.get("rooms") or []
    if rooms:
        return sum(OCC_COUNT.get(r.get("ocupacion"), 1) * int(r.get("count", 1) or 1) for r in rooms) + int(pax.get("menores", 0) or 0)
    return int(pax.get("adultos", 0) or 0) + int(pax.get("menores", 0) or 0)


def build_per_person_breakdown(q: dict) -> dict | None:
    """Return {rows, total, total_pax, currency} or None if not applicable.
    Each row: {key, label, pax, price_per_person, subtotal}. Sum of row subtotals
    == quotation total (final_total or total) to the cent."""
    if not q:
        return None
    items = q.get("items") or []
    total_target = q.get("final_total")
    if total_target is None:
        total_target = q.get("total", 0)
    total_target = round(float(total_target or 0), 2)
    if total_target <= 0:
        return None

    pax = q.get("pax") or {}
    menores_pax = int(pax.get("menores", 0) or 0)

    # Ocupación de conceptos custom de hospedaje (Programa personalizado / Servicios a la
    # carta): pricing.py no la incluye en el item, así que la tomamos del input crudo
    # `custom_items` (mismo orden que los items kind='custom'). Datos viejos sin ocupación
    # caen al fallback uniforme actual, sin romper cotizaciones existentes.
    custom_inputs = [ci for ci in (q.get("custom_items") or [])]
    _custom_idx = 0

    occ_groups: dict = {}  # occ -> {"pax": int, "lodging": float}
    menores_lodging = 0.0
    lodging_total = 0.0
    for it in items:
        kind = it.get("kind")
        if kind == "custom":
            ci = custom_inputs[_custom_idx] if _custom_idx < len(custom_inputs) else {}
            _custom_idx += 1
            if it.get("category") == "hospedaje":
                occ = ci.get("ocupacion")
                sub = float(it.get("subtotal", 0) or 0)
                if occ in OCC_COUNT:
                    rooms = int(it.get("qty", 1) or 1) if it.get("unit") == "per_room" else 1
                    rooms = max(1, rooms)
                    g = occ_groups.setdefault(occ, {"pax": 0, "lodging": 0.0})
                    g["pax"] += OCC_COUNT[occ] * rooms
                    g["lodging"] += sub
                    lodging_total += sub
                # sin ocupación: se queda en el pool compartido (fallback)
            continue
        if kind != "hospedaje":
            continue
        sub = float(it.get("subtotal", 0) or 0)
        if it.get("ocupacion"):
            occ = it["ocupacion"]
            g = occ_groups.setdefault(occ, {"pax": 0, "lodging": 0.0})
            g["pax"] += int(it.get("qty", 0) or 0)
            g["lodging"] += sub
            lodging_total += sub
        elif "menor" in (it.get("label") or "").lower():
            menores_lodging += sub
            lodging_total += sub
        else:
            # no-rooms adult fallback: group under pax.ocupacion
            occ = pax.get("ocupacion", "doble")
            g = occ_groups.setdefault(occ, {"pax": 0, "lodging": 0.0})
            g["pax"] += int(it.get("qty", 0) or 0)
            g["lodging"] += sub
            lodging_total += sub

    adults_pax = sum(g["pax"] for g in occ_groups.values())
    total_pax = adults_pax + menores_pax
    if total_pax <= 0:
        total_pax = _pax_total_from_pax(pax)
    if total_pax <= 0:
        return None

    # Remaining pool distributed uniformly across all pax (services, custom, extra,
    # commission and discount deltas). Guarantees the grand total matches.
    shared_pool = round(total_target - lodging_total, 2)
    shared_pp = shared_pool / total_pax

    rows = []
    if occ_groups:
        for occ, g in occ_groups.items():
            if g["pax"] <= 0:
                continue
            lodging_pp = g["lodging"] / g["pax"]
            pp = round(lodging_pp + shared_pp, 2)
            rows.append({"key": occ, "label": OCC_LABEL.get(occ, occ.capitalize()),
                         "pax": g["pax"], "price_per_person": pp, "subtotal": round(pp * g["pax"], 2)})
        if menores_pax > 0:
            lodging_pp = (menores_lodging / menores_pax) if menores_pax else 0.0
            pp = round(lodging_pp + shared_pp, 2)
            rows.append({"key": "menor", "label": "Menor", "pax": menores_pax,
                         "price_per_person": pp, "subtotal": round(pp * menores_pax, 2)})
    else:
        # No per-occupancy lodging (servicios a la carta / personalizado): single uniform row.
        pp = round(total_target / total_pax, 2)
        rows.append({"key": "persona", "label": "Por persona", "pax": total_pax,
                     "price_per_person": pp, "subtotal": round(pp * total_pax, 2)})

    if not rows:
        return None

    # Absorb rounding residual in the largest row so rows sum EXACTLY to the total.
    diff = round(total_target - sum(r["subtotal"] for r in rows), 2)
    if abs(diff) >= 0.01:
        big = max(rows, key=lambda r: r["pax"])
        big["subtotal"] = round(big["subtotal"] + diff, 2)
        if big["pax"]:
            big["price_per_person"] = round(big["subtotal"] / big["pax"], 2)

    return {"rows": rows, "total": total_target, "total_pax": total_pax,
            "currency": q.get("currency", "MXN")}
