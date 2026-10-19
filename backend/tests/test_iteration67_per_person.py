"""Iter 67 — escenario obligatorio del cliente (6 pax = 1 doble + 1 cuádruple)."""
import pytest
from pricing import compute_custom_quotation, compute_quotation
from pricing_breakdown import build_per_person_breakdown

CFG = {"margin_divisor": 0.80, "currency": "MXN",
       "commissions": {"directo": 0.0, "agencia": 0.10, "mayorista": 0.15, "operador": 0.15}}
PAX = {"adultos": 6, "menores": 0, "rooms": []}
DATES = {"start": "2026-11-04", "end": "2026-11-09"}


def _items(hotel_type, doble, cuad, unit="per_night"):
    return [
        {"category": "hospedaje", "name": "Hotel", "price_type": hotel_type, "unit": unit,
         "checkin": "2026-11-04", "checkout": "2026-11-09", "nights": 5,
         "occupancy_rows": [{"ocupacion": "doble", "rooms": 1, "price": doble},
                            {"ocupacion": "cuadruple", "rooms": 1, "price": cuad}]},
        {"category": "traslado", "name": "Vehículo", "price_type": "publico", "unit": "per_vehicle", "net_price": 6000, "qty": 1},
        {"category": "tour", "name": "Tour", "price_type": "publico", "unit": "per_person", "net_price": 450, "qty": 0},
        {"category": "extra", "name": "Cena", "price_type": "publico", "unit": "per_group", "net_price": 3000, "qty": 1},
    ]


CASES = [
    ("A", "directo", "publico", 875, 700, "per_night", 6325, 5450, 34450),
    ("B", "agencia", "neto", 700, 560, "per_night", 6130, 5255, 33280),
    ("C", "mayorista", "neto", 700, 560, "per_night", 5376.25, 4632.50, 29282.50),
    ("D", "operador", "neto", 700, 560, "per_night", 5157.50, 4457.50, 28145),
    ("E", "directo", "publico", 4375, 3500, "per_stay", 6325, 5450, 34450),
]


def _check(q, pp_d, pp_c, total):
    assert q["total"] == pytest.approx(total, abs=0.001)
    bd = build_per_person_breakdown(q)
    rows = {r["key"]: r for r in bd["rows"]}
    assert rows["doble"]["price_per_person"] == pytest.approx(pp_d, abs=0.001)
    assert rows["doble"]["pax"] == 2
    assert rows["cuadruple"]["price_per_person"] == pytest.approx(pp_c, abs=0.001)
    assert rows["cuadruple"]["pax"] == 4
    assert sum(r["subtotal"] for r in bd["rows"]) == pytest.approx(total, abs=0.001)
    assert bd["total"] == pytest.approx(total, abs=0.001)
    assert bd["total_pax"] == 6
    assert bd["rounding_adjustment"] == 0 and bd["commission_adjustment"] == 0
    assert "6 personas" in bd["note"]


@pytest.mark.parametrize("name,channel,htype,d,c,unit,pp_d,pp_c,total", CASES)
def test_personalizado(name, channel, htype, d, c, unit, pp_d, pp_c, total):
    calc = compute_custom_quotation(_items(htype, d, c, unit), PAX, 0, 0, channel, CFG, dates=DATES)
    q = {**calc, "type": "personalizado", "pax": PAX, "custom_items": _items(htype, d, c, unit)}
    _check(q, pp_d, pp_c, total)


@pytest.mark.parametrize("name,channel,htype,d,c,unit,pp_d,pp_c,total", CASES)
def test_a_la_carta(name, channel, htype, d, c, unit, pp_d, pp_c, total):
    calc = compute_quotation(None, "", PAX, 0, channel, CFG, {}, [], dates=DATES,
                             custom_items=_items(htype, d, c, unit))
    q = {**calc, "type": "servicios", "pax": PAX, "custom_items": _items(htype, d, c, unit)}
    _check(q, pp_d, pp_c, total)


def test_discount_proportional():
    calc = compute_custom_quotation(_items("publico", 875, 700), PAX, 0, 0, "directo", CFG, dates=DATES)
    q = {**calc, "type": "personalizado", "pax": PAX, "final_total": 31005.0}  # -10%
    bd = build_per_person_breakdown(q)
    rows = {r["key"]: r for r in bd["rows"]}
    assert rows["doble"]["price_per_person"] == pytest.approx(5692.5, abs=0.001)
    assert rows["cuadruple"]["price_per_person"] == pytest.approx(4905.0, abs=0.001)
    assert sum(r["subtotal"] for r in bd["rows"]) == pytest.approx(31005.0, abs=0.001)


def test_package_extras_unchanged():
    """Paquete armado conserva el motor histórico en sus extras (custom_engine=False)."""
    pack = {"name": "P", "nights": 3, "hotels": [{"name": "H", "prices_by_occupancy": {"doble": 1000}}]}
    extra = [{"category": "hospedaje", "name": "Noche", "price_type": "neto", "unit": "per_night", "net_price": 800, "qty": 2, "nights": 3,
              "occupancy_rows": [{"ocupacion": "doble", "rooms": 1, "price": 999}]},
             {"category": "extra", "name": "Cena", "price_type": "publico", "unit": "per_group", "net_price": 500, "qty": 2}]
    calc = compute_quotation(pack, "H", {"rooms": [{"ocupacion": "doble", "count": 1}], "menores": 0}, 3, "directo", CFG,
                             dates={"start": "2026-11-04", "end": "2026-11-07"}, custom_items=extra)
    subs = [it["subtotal"] for it in calc["items"] if it["kind"] == "custom"]
    assert subs == [round(800 / 0.8, 2) * 2 * 3, 1000.0]
