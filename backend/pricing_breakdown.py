"""Presentation-only helper: "precio por persona según ocupación" (Iter 67).

No modifica el motor (pricing.py): CONSUME los items ya calculados y construye el precio
DESDE LA PERSONA HACIA EL TOTAL:
  1. Precio de canal por concepto: los conceptos comisionables (servicios de catálogo y
     conceptos de precio público) llevan la comisión del canal línea por línea; los netos ya
     traen su precio de canal. La suma de comisiones por línea se cuadra con la del motor
     (residuo de centavos -> concepto de mayor monto, reportado en `commission_adjustment`).
  2. Hospedaje por ocupación: monto de la fila ÷ personas de esa ocupación.
  3. Resto de conceptos (grupo, vehículo, por persona, noche extra…): ÷ total de personas.
  4. Descuento global: proporcional al precio por persona (factor final_total / total).
  5. Residuo de redondeo -> fila de mayor subtotal (`rounding_adjustment`).
"""

OCC_LABEL = {"sencilla": "Sencilla", "doble": "Doble", "triple": "Triple", "cuadruple": "Cuádruple"}
OCC_COUNT = {"sencilla": 1, "doble": 2, "triple": 3, "cuadruple": 4}
OCC_ORDER = ["sencilla", "doble", "triple", "cuadruple"]


def _pax_total_from_pax(pax: dict) -> int:
    pax = pax or {}
    rooms = pax.get("rooms") or []
    if rooms:
        return sum(OCC_COUNT.get(r.get("ocupacion"), 1) * int(r.get("count", 1) or 1) for r in rooms) + int(pax.get("menores", 0) or 0)
    return int(pax.get("adultos", 0) or 0) + int(pax.get("menores", 0) or 0)


def _channel_lines(q: dict) -> tuple[list, float]:
    """Monto de canal por línea (comisión aplicada concepto por concepto)."""
    rate = float(q.get("commission_rate", 0) or 0)
    lines = []
    for it in (q.get("items") or []):
        sub = float(it.get("subtotal", 0) or 0)
        commissionable = it.get("kind") == "servicio" or (it.get("kind") == "custom" and it.get("price_type") == "publico")
        com = round(sub * rate, 2) if commissionable else 0.0
        lines.append({"it": it, "sub": sub, "com": com, "commissionable": commissionable})
    engine_com = round(float(q.get("commission", 0) or 0), 2)
    diff = round(engine_com - sum(ln["com"] for ln in lines), 2)
    comm_lines = [ln for ln in lines if ln["commissionable"]]
    if abs(diff) >= 0.01 and comm_lines:
        max(comm_lines, key=lambda ln: ln["sub"])["com"] += diff
    else:
        diff = 0.0
    for ln in lines:
        ln["amt"] = round(ln["sub"] - ln["com"], 2)
    return lines, diff


def _lodging_occ(it: dict, ci: dict, pax: dict):
    """(concept_key, ocupacion|'menor', personas) para una línea de hospedaje, o None si va al pool."""
    if it.get("kind") == "hospedaje":
        if it.get("ocupacion"):
            return "pkg", it["ocupacion"], int(it.get("qty", 0) or 0)
        if "menor" in (it.get("label") or "").lower():
            return "pkg", "menor", int(it.get("qty", 0) or 0)
        return "pkg", pax.get("ocupacion", "doble"), int(it.get("qty", 0) or 0)
    if it.get("kind") == "custom" and it.get("category") == "hospedaje":
        key = f"ci{it.get('ci_index', '')}"
        if it.get("occ_row") and it.get("ocupacion") in OCC_COUNT:
            return key, it["ocupacion"], int(it.get("qty", 0) or 0)
        occ = (ci or {}).get("ocupacion")
        if occ in OCC_COUNT:  # dato previo a la tabla de ocupación
            rooms = max(1, int(it.get("qty", 1) or 1)) if it.get("unit") == "per_room" else 1
            return key, occ, OCC_COUNT[occ] * rooms
    return None


def _short(it: dict) -> str:
    return (it.get("name") or it.get("label") or "Concepto").split(" · ")[0]


def build_per_person_breakdown(q: dict) -> dict | None:
    """{rows, total, total_pax, currency, note, commission_adjustment, rounding_adjustment}.
    Cada fila: {key, label, title, pax, price_per_person, subtotal, components}.
    La suma de subtotales == total de la cotización (final_total o total) al centavo."""
    if not q:
        return None
    engine_total = round(float(q.get("total", 0) or 0), 2)
    target = q.get("final_total")
    target = round(float(engine_total if target is None else target or 0), 2)
    if target <= 0 or engine_total <= 0:
        return None
    pax = q.get("pax") or {}
    custom_inputs = q.get("custom_items") or []
    lines, commission_adj = _channel_lines(q)

    lodging: dict = {}   # occ -> {concept_key: {"pax": n, "amt": x, "name": str}}
    shared = []          # (nombre, monto)
    seq = 0
    for ln in lines:
        it = ln["it"]
        ci = {}
        if it.get("kind") == "custom":
            idx = it.get("ci_index", seq)
            ci = custom_inputs[idx] if isinstance(idx, int) and idx < len(custom_inputs) else {}
            seq += 1
        res = _lodging_occ(it, ci, pax)
        if res and res[2] > 0:
            key, occ, persons = res
            g = lodging.setdefault(occ, {}).setdefault(key, {"pax": 0, "amt": 0.0, "name": _short(it) if key != "pkg" else "Hospedaje"})
            g["pax"] += persons
            g["amt"] += ln["amt"]
        else:
            shared.append((_short(it), ln["amt"]))

    groups = {}
    for occ, concepts in lodging.items():
        groups[occ] = {
            "pax": max(c["pax"] for c in concepts.values()),
            "components": [{"label": c["name"], "amount": c["amt"] / c["pax"]} for c in concepts.values()],
        }
    if groups:
        total_pax = sum(g["pax"] for g in groups.values())
        if "menor" not in groups and q.get("type", "paquete") == "paquete":
            total_pax += int(pax.get("menores", 0) or 0)
    else:
        total_pax = _pax_total_from_pax(pax)
    if total_pax <= 0:
        return None

    shared_comp = [{"label": n, "amount": a / total_pax} for n, a in shared if abs(a) >= 0.005]
    if not groups:
        groups["persona"] = {"pax": total_pax, "components": []}
    elif q.get("type", "paquete") == "paquete" and "menor" not in groups and int(pax.get("menores", 0) or 0) > 0:
        groups["menor"] = {"pax": int(pax.get("menores", 0) or 0), "components": []}

    factor = target / engine_total
    rows = []
    for key in OCC_ORDER + ["menor", "persona"]:
        g = groups.get(key)
        if not g or g["pax"] <= 0:
            continue
        comps = g["components"] + shared_comp
        pp = round(sum(c["amount"] for c in comps) * factor, 2)
        if key in OCC_LABEL:
            label, title = OCC_LABEL[key], f"Precio por persona en ocupación {OCC_LABEL[key]}"
        elif key == "menor":
            label, title = "Menor", "Precio por menor"
        else:
            label, title = "Por persona", "Precio por persona"
        rows.append({"key": key, "label": label, "title": title, "pax": g["pax"],
                     "price_per_person": pp, "subtotal": round(pp * g["pax"], 2),
                     "components": [{"label": c["label"], "amount": round(c["amount"], 2)} for c in comps]})
    if not rows:
        return None

    rounding_adj = round(target - sum(r["subtotal"] for r in rows), 2)
    if abs(rounding_adj) >= 0.01:
        big = max(rows, key=lambda r: r["subtotal"])
        big["subtotal"] = round(big["subtotal"] + rounding_adj, 2)
        big["price_per_person"] = round(big["subtotal"] / big["pax"], 2)
    else:
        rounding_adj = 0.0

    return {"rows": rows, "total": target, "total_pax": total_pax,
            "currency": q.get("currency", "MXN"),
            "note": f"Precios por persona en base a {total_pax} personas; si varía, se recotiza.",
            "discount_factor": round(factor, 6),
            "commission_adjustment": round(commission_adj, 2),
            "rounding_adjustment": rounding_adj}
