"""Iter 73 UI data: `setup` creates mayorista unlocked + locked(paid) quotations; `cleanup` deletes them."""
import json
import os
import sys
import requests

BASE = open('/app/frontend/.env').read().split('REACT_APP_BACKEND_URL=')[1].split()[0].rstrip('/')
API = f"{BASE}/api"
F = "/tmp/it73ui.json"
ITEMS = [{"category": "hospedaje", "name": "Hotel", "price_type": "neto", "unit": "per_night", "checkin": "2026-11-04", "checkout": "2026-11-09", "nights": 5,
          "occupancy_rows": [{"ocupacion": "doble", "rooms": 1, "price": 700}, {"ocupacion": "cuadruple", "rooms": 1, "price": 560}]},
         {"category": "traslado", "name": "Vehículo", "price_type": "publico", "unit": "per_vehicle", "net_price": 6000, "qty": 1},
         {"category": "tour", "name": "Tour", "price_type": "publico", "unit": "per_person", "net_price": 450, "qty": 0},
         {"category": "extra", "name": "Cena", "price_type": "publico", "unit": "per_group", "net_price": 3000, "qty": 1}]

s = requests.Session()
s.post(f"{API}/auth/login", json={"email": "admin@aventurate.mx", "password": "Demo2026!"}).raise_for_status()
if sys.argv[1] == "setup":
    orig = s.get(f"{API}/companies/me").json()["pricing_config"]
    out = {"orig": orig, "clients": [], "quotes": {}}
    s.patch(f"{API}/companies/me/pricing", json={**orig, "fx_mayorista_mxn_per_usd": 18.5}).raise_for_status()
    cl = s.post(f"{API}/clients", json={"name": "TEST73UI Mayorista", "channel": "mayorista"}).json()
    out["clients"].append(cl["id"])
    for k in ("open", "locked"):
        r = s.post(f"{API}/quotations", json={"type": "personalizado", "client_id": cl["id"], "custom_title": f"TEST73UI {k}",
                                             "dates": {"start": "2026-11-04", "end": "2026-11-09"},
                                             "pax": {"adultos": 6, "menores": 0, "rooms": []}, "custom_items": ITEMS, "show_per_person": True})
        r.raise_for_status()
        out["quotes"][k] = r.json()["id"]
    s.patch(f"{API}/quotations/{out['quotes']['locked']}/mark-paid", json={"amount": 1000, "method": "transfer"}).raise_for_status()
    json.dump(out, open(F, "w"))
    print(json.dumps(out["quotes"]))
else:
    d = json.load(open(F))
    for q in d["quotes"].values():
        s.delete(f"{API}/quotations/{q}")
    for c in d["clients"]:
        s.delete(f"{API}/clients/{c}")
    s.patch(f"{API}/companies/me/pricing", json=d["orig"])
    print("cleaned", s.get(f"{API}/companies/me").json()["pricing_config"].get("fx_mayorista_mxn_per_usd"))
