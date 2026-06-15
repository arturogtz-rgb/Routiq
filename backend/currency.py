"""Lightweight exchange-rate helper (USD/MXN) with in-memory caching.

Uses the free, no-key open.er-api.com endpoint. Falls back to a sane default
if the network call fails so the UI never breaks.
"""
from __future__ import annotations
import time
import httpx

_cache: dict = {"data": None, "ts": 0.0}
_TTL = 6 * 3600  # 6 hours
_FALLBACK_MXN_PER_USD = 17.0


async def get_rates() -> dict:
    now = time.time()
    if _cache["data"] and (now - _cache["ts"] < _TTL):
        return _cache["data"]
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get("https://open.er-api.com/v6/latest/USD")
            j = r.json()
            mxn_per_usd = float(j["rates"]["MXN"])
            data = {
                "mxn_per_usd": round(mxn_per_usd, 4),
                "usd_per_mxn": round(1.0 / mxn_per_usd, 6),
                "updated_at": j.get("time_last_update_utc", ""),
                "source": "open.er-api.com",
            }
            _cache["data"] = data
            _cache["ts"] = now
            return data
    except Exception:
        if _cache["data"]:
            return _cache["data"]
        return {
            "mxn_per_usd": _FALLBACK_MXN_PER_USD,
            "usd_per_mxn": round(1.0 / _FALLBACK_MXN_PER_USD, 6),
            "updated_at": "",
            "source": "fallback",
        }


def convert(amount: float, from_ccy: str, to_ccy: str, rates: dict) -> float:
    """Convert between MXN and USD using fetched rates."""
    from_ccy = (from_ccy or "MXN").upper()
    to_ccy = (to_ccy or "MXN").upper()
    if from_ccy == to_ccy:
        return round(amount, 2)
    if from_ccy == "MXN" and to_ccy == "USD":
        return round(amount * rates["usd_per_mxn"], 2)
    if from_ccy == "USD" and to_ccy == "MXN":
        return round(amount * rates["mxn_per_usd"], 2)
    return round(amount, 2)
