"""Iter67 E2E API: per-person breakdown (cases A-E, personalizado & servicios), public link, PDF, PATCH recompute, paquete regression."""
import os
import io
import pytest
import requests

BASE = open('/app/frontend/.env').read().split('REACT_APP_BACKEND_URL=')[1].split()[0].rstrip('/')
API = f"{BASE}/api"

EXPECTED = {
    "A": ("directo", "publico", "per_night", 875, 700, {"doble": (6325, 12650), "cuadruple": (5450, 21800)}, 34450),
    "B": ("agencia", "neto", "per_night", 700, 560, {"doble": (6130, 12260), "cuadruple": (5255, 21020)}, 33280),
    "C": ("mayorista", "neto", "per_night", 700, 560, {"doble": (5376.25, 10752.5), "cuadruple": (4632.5, 18530)}, 29282.5),
    "D": ("operador", "neto", "per_night", 700, 560, {"doble": (5157.5, 10315), "cuadruple": (4457.5, 17830)}, 28145),
    "E": ("directo", "publico", "per_stay", 4375, 3500, {"doble": (6325, 12650), "cuadruple": (5450, 21800)}, 34450),
}


def items(ht, unit, d, c, rooms_d=1):
    return [{"category": "hospedaje", "name": "Hotel Test", "price_type": ht, "unit": unit, "checkin": "2026-11-04",
             "checkout": "2026-11-09", "nights": 5,
             "occupancy_rows": [{"ocupacion": "doble", "rooms": rooms_d, "price": d}, {"ocupacion": "cuadruple", "rooms": 1, "price": c}]},
            {"category": "traslado", "name": "Vehiculo", "price_type": "publico", "unit": "per_vehicle", "net_price": 6000, "qty": 1},
            {"category": "tour", "name": "Tour", "price_type": "publico", "unit": "per_person", "net_price": 450, "qty": 0},
            {"category": "extra", "name": "Cena", "price_type": "publico", "unit": "per_group", "net_price": 3000, "qty": 1}]


@pytest.fixture(scope="module")
def ctx():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@aventurate.mx", "password": "Demo2026!"})
    r.raise_for_status()
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    orig = s.get(f"{API}/companies/me").json()["pricing_config"]
    new = {**orig, "margin_divisor": 0.80, "commissions": {"directo": 0.0, "agencia": 0.10, "mayorista": 0.15, "operador": 0.15}}
    assert s.patch(f"{API}/companies/me", json={"pricing_config": new}).status_code == 200
    clients, qids = {}, []
    for ch in ("directo", "agencia", "mayorista", "operador"):
        r = s.post(f"{API}/clients", json={"name": f"TEST_iter67_{ch}", "channel": ch, "executives": [{"name": "TEST Exec"}]})
        assert r.status_code in (200, 201), r.text
        clients[ch] = r.json()
    yield {"s": s, "clients": clients, "qids": qids}
    for q in qids:
        s.delete(f"{API}/quotations/{q}")
    for c in clients.values():
        s.delete(f"{API}/clients/{c['id']}")
    r = s.patch(f"{API}/companies/me", json={"pricing_config": orig})
    print("restore", r.status_code)


def _create(ctx, typ, case, extra=None):
    ch, ht, unit, d, c, _, _ = EXPECTED[case]
    cl = ctx["clients"][ch]
    p = {"type": typ, "client_id": cl["id"], "custom_title": f"TEST_iter67 {case}",
         "dates": {"start": "2026-11-04", "end": "2026-11-09"},
         "pax": {"adultos": 6, "menores": 0, "rooms": []}, "custom_items": items(ht, unit, d, c), "services": [],
         "show_per_person": True, "executive_id": ((cl.get("executives") or [{}])[0].get("id"))}
    r = ctx["s"].post(f"{API}/quotations", json=p)
    assert r.status_code == 201, r.text
    ctx["qids"].append(r.json()["id"])
    return r.json()["id"]


@pytest.mark.parametrize("typ", ["personalizado", "servicios"])
@pytest.mark.parametrize("case", list(EXPECTED))
def test_case(ctx, typ, case):
    qid = _create(ctx, typ, case)
    q = ctx["s"].get(f"{API}/quotations/{qid}").json()
    bd = q["per_person_breakdown"]
    rows = {r["key"]: r for r in bd["rows"]}
    exp_rows, exp_total = EXPECTED[case][5], EXPECTED[case][6]
    got = {k: (r["price_per_person"], r["pax"], r["subtotal"]) for k, r in rows.items()}
    print(typ, case, q.get("total"), q.get("final_total"), got, bd.get("total"), bd["note"])
    assert set(rows) == {"doble", "cuadruple"}
    for k, (pp, sub) in exp_rows.items():
        assert rows[k]["price_per_person"] == pytest.approx(pp, abs=0.001), (k, rows[k])
        assert rows[k]["subtotal"] == pytest.approx(sub, abs=0.001), (k, rows[k])
    assert rows["doble"]["pax"] == 2 and rows["cuadruple"]["pax"] == 4
    assert q["total"] == pytest.approx(exp_total, abs=0.001)
    assert sum(r["subtotal"] for r in bd["rows"]) == pytest.approx(q.get("final_total") or q["total"], abs=0.001)
    assert "6 personas" in bd["note"]


def test_public_link_and_pdf(ctx):
    s = ctx["s"]
    qid = _create(ctx, "personalizado", "B")
    r = s.post(f"{API}/quotations/{qid}/public-link")
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    pub = requests.get(f"{API}/public/quotations/{tok}")
    assert pub.status_code == 200, pub.text
    j = pub.json()
    bd = j.get("per_person_breakdown") or (j.get("quotation") or {}).get("per_person_breakdown")
    assert bd and bd.get("rows") and bd.get("note"), list(j.keys())
    print("public bd", bd)
    pdf = s.get(f"{API}/quotations/{qid}/pdf")
    assert pdf.status_code == 200, pdf.text[:300]
    assert pdf.content[:4] == b"%PDF"
    from pypdf import PdfReader
    txt = "".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf.content)).pages)
    flat = " ".join(txt.split())
    print(flat[:3000])
    assert "Precio por persona en ocupación Doble" in flat
    assert "6 personas" in flat
    ppdf = requests.get(f"{API}/public/quotations/{tok}/pdf")
    assert ppdf.status_code == 200


def test_patch_recompute(ctx):
    s = ctx["s"]
    qid = _create(ctx, "personalizado", "A")
    q0 = s.get(f"{API}/quotations/{qid}").json()
    new_items = items("publico", "per_night", 875, 700, rooms_d=2)
    r = s.patch(f"{API}/quotations/{qid}", json={"custom_items": new_items, "pax": {"adultos": 8, "menores": 0, "rooms": []}})
    assert r.status_code == 200, r.text
    q = s.get(f"{API}/quotations/{qid}").json()
    rows = {x["key"]: x for x in q["per_person_breakdown"]["rows"]}
    print("patched", q["total"], rows)
    assert q["total"] != q0["total"]
    assert rows["doble"]["pax"] == 4
    assert sum(x["subtotal"] for x in rows.values()) == pytest.approx(q.get("final_total") or q["total"], abs=0.01)
    assert "8 personas" in q["per_person_breakdown"]["note"]


def test_paquete_regression(ctx):
    s = ctx["s"]
    pkgs = s.get(f"{API}/packages").json()
    pkgs = pkgs.get("items", pkgs) if isinstance(pkgs, dict) else pkgs
    pkg = next((p for p in pkgs if p.get("hotels")), None)
    if not pkg:
        pytest.skip("no package")
    cl = ctx["clients"]["directo"]
    totals = []
    for with_rows in (False, True):
        extra = [{"category": "hospedaje", "name": "Noche", "price_type": "neto", "unit": "per_night", "net_price": 800, "qty": 2, "nights": 3},
                 {"category": "extra", "name": "Cena", "price_type": "publico", "unit": "per_group", "net_price": 500, "qty": 2}]
        if with_rows:
            extra[0]["occupancy_rows"] = [{"ocupacion": "doble", "rooms": 1, "price": 999}]
        p = {"type": "paquete", "client_id": cl["id"], "package_id": pkg["id"], "hotel_name": pkg["hotels"][0]["name"],
             "pax": {"adultos": 2, "menores": 0, "rooms": [{"ocupacion": "doble", "count": 1}]},
             "dates": {"start": "2026-11-04", "end": "2026-11-07"}, "custom_items": extra,
             "executive_id": cl["executives"][0]["id"]}
        r = s.post(f"{API}/quotations", json=p)
        assert r.status_code == 201, r.text
        ctx["qids"].append(r.json()["id"])
        q = s.get(f"{API}/quotations/{r.json()['id']}").json()
        subs = [it["subtotal"] for it in q.get("items", []) if it.get("kind") == "custom"]
        print("paquete", with_rows, q["total"], subs)
        totals.append((q["total"], subs))
    assert totals[0] == totals[1]
    assert totals[0][1] == [round(800 / 0.8, 2) * 2 * 3, 1000.0]
