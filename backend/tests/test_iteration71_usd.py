"""Iter 71 — presentación USD Mayorista internacional + TC sin inventar."""
import asyncio

import pytest

import currency
import fx_presentation as fx
from pricing import compute_custom_quotation
from pricing_breakdown import build_per_person_breakdown

CFG = {"margin_divisor": 0.80, "currency": "MXN",
       "commissions": {"directo": 0.0, "agencia": 0.10, "mayorista": 0.15, "operador": 0.15}}
PAX = {"adultos": 6, "menores": 0, "rooms": []}
ITEMS = [
    {"category": "hospedaje", "name": "Hotel", "price_type": "neto", "unit": "per_night", "nights": 5,
     "checkin": "2026-11-04", "checkout": "2026-11-09",
     "occupancy_rows": [{"ocupacion": "doble", "rooms": 1, "price": 700}, {"ocupacion": "cuadruple", "rooms": 1, "price": 560}]},
    {"category": "traslado", "name": "Vehículo", "price_type": "publico", "unit": "per_vehicle", "net_price": 6000, "qty": 1},
    {"category": "tour", "name": "Tour", "price_type": "publico", "unit": "per_person", "net_price": 450, "qty": 0},
    {"category": "extra", "name": "Cena", "price_type": "publico", "unit": "per_group", "net_price": 3000, "qty": 1},
]


def _q(channel="mayorista", rate=18.5, show=True):
    calc = compute_custom_quotation(ITEMS, PAX, 0, 0, channel, CFG, dates={"start": "2026-11-04", "end": "2026-11-09"})
    q = {**calc, "type": "personalizado", "pax": PAX, "custom_items": ITEMS, "show_per_person": show,
         "client_snapshot": {"channel": channel}}
    if rate:
        q["fx_rate_mxn_per_usd"] = rate
    return q


def test_case_c_usd():
    q = _q()
    assert q["total"] == 29282.50  # MXN intacto
    u = fx.build(q, build_per_person_breakdown(q))
    rows = {r["key"]: r for r in u["rows"]}
    assert rows["doble"]["price_per_person_mxn"] == 5376.25 and rows["doble"]["price_per_person_usd"] == 290.61
    assert rows["cuadruple"]["price_per_person_mxn"] == 4632.50 and rows["cuadruple"]["price_per_person_usd"] == 250.41
    assert u["total_usd"] == 1582.86  # Σ pp USD × personas (suma exacta del documento)
    assert u["direct_total_usd"] == round(29282.50 / 18.5, 2) == 1582.84
    assert u["rounding_diff_usd"] == 0.02
    assert "$18.50 MXN por USD" in u["note"] and "pesos mexicanos (MXN)" in u["note"]


def test_without_per_person_uses_total():
    q = _q(show=False)
    u = fx.build(q, None)
    assert u["rows"] == [] and u["total_usd"] == 1582.84


def test_missing_rate_warns_and_other_channels_none():
    assert fx.build(_q(rate=None), None) == {"available": False, "warning": "Captura el tipo de cambio en Ajustes"}
    for ch in ("directo", "agencia", "operador"):
        assert fx.build(_q(channel=ch), None) is None
    assert fx.snapshot_fields({"pricing_config": {"fx_mayorista_mxn_per_usd": 18.5}}, "agencia") == {}


def test_currency_no_invented_fallback(monkeypatch):
    class Boom:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            raise RuntimeError("sin red")

        async def __aexit__(self, *a):
            return False
    monkeypatch.setattr(currency.httpx, "AsyncClient", Boom)
    monkeypatch.setitem(currency._cache, "data", None)
    monkeypatch.setitem(currency._cache, "ts", 0.0)
    rates = asyncio.run(currency.get_rates())
    assert rates["mxn_per_usd"] is None and rates["source"] == "unavailable"
    assert currency.convert(1000, "MXN", "USD", rates) is None


def test_fx_validation():
    from models import PricingConfig
    assert PricingConfig(fx_mayorista_mxn_per_usd=18.1234).fx_mayorista_mxn_per_usd == 18.1234
    for bad in (0, -1, 18.12345):
        with pytest.raises(Exception):
            PricingConfig(fx_mayorista_mxn_per_usd=bad)
