"""Iter68: quotations list search (text/accents, executive/agent/final client), trip_start, date search, trip range, sort."""
import pytest
import requests

BASE = open('/app/frontend/.env').read().split('REACT_APP_BACKEND_URL=')[1].split()[0].rstrip('/')
API = f"{BASE}/api"
TAG = "TEST_it68"


@pytest.fixture(scope="module")
def ctx():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@aventurate.mx", "password": "Demo2026!"})
    r.raise_for_status()
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    me = s.get(f"{API}/auth/me").json()
    c = s.post(f"{API}/clients", json={"name": f"{TAG} Agencia Zafiro", "channel": "agencia",
                                       "executives": [{"name": "Ángela Núñez"}]})
    assert c.status_code in (200, 201), c.text
    cl = c.json()
    exid = cl["executives"][0]["id"]
    qids = {}

    def mk(key, typ, dates=None, items=None, traveler=""):
        p = {"type": typ, "client_id": cl["id"], "custom_title": f"{TAG} {key}", "executive_id": exid,
             "dates": dates or {}, "pax": {"adultos": 2, "menores": 0, "rooms": []},
             "custom_items": items or [{"category": "extra", "name": "Cena", "price_type": "publico", "unit": "per_group", "net_price": 3000, "qty": 1}], "services": [],
             "contacts": {"agency": {}, "traveler": {"name": traveler}}}
        r = s.post(f"{API}/quotations", json=p)
        assert r.status_code == 201, r.text
        qids[key] = r.json()
        return r.json()

    hotel = lambda ci: [{"category": "hospedaje", "name": "Hotel", "price_type": "publico", "unit": "per_night",
                         "checkin": ci, "checkout": "2026-12-30", "nights": 2,
                         "occupancy_rows": [{"ocupacion": "doble", "rooms": 1, "price": 1000}]}]
    mk("nov", "personalizado", {"start": "2026-11-04", "end": "2026-11-09"}, hotel("2026-11-04"), "José Pérez")
    mk("items", "servicios", {}, hotel("2026-12-20") + [{"category": "hospedaje", "name": "H2", "price_type": "publico",
                                                         "unit": "per_night", "checkin": "2026-12-15", "checkout": "2026-12-17",
                                                         "nights": 2, "occupancy_rows": [{"ocupacion": "doble", "rooms": 1, "price": 1000}]}])
    mk("nodate", "personalizado", {}, [], "Mariana Ortiz")
    mk("mar", "personalizado", {"start": "2027-03-10", "end": "2027-03-12"}, [], "")
    yield {"s": s, "client": cl, "exid": exid, "q": qids, "me": me}
    for v in qids.values():
        s.delete(f"{API}/quotations/{v['id']}")
    s.delete(f"{API}/clients/{cl['id']}")


def search(ctx, **params):
    r = ctx["s"].get(f"{API}/quotations", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def codes(lst):
    return {x["code"] for x in lst}


def tagged(lst):
    return [x for x in lst if (x.get("client_snapshot") or {}).get("name", "").startswith(TAG)]


# Response fields
def test_fields(ctx):
    data = search(ctx, q=ctx["q"]["nov"]["code"])
    it = [x for x in data if x["id"] == ctx["q"]["nov"]["id"]][0]
    assert it["trip_start"] == "2026-11-04"
    assert it["executive_name"] == "Ángela Núñez"
    assert it["final_client_names"] == ["José Pérez"]
    assert isinstance(it["agent_name"], str) and it["agent_name"]
    assert "_hay" not in it


def test_trip_start_derivation(ctx):
    data = {x["id"]: x for x in search(ctx, q="agencia zafiro")}
    assert data[ctx["q"]["items"]["id"]]["trip_start"] == "2026-12-15"
    assert data[ctx["q"]["nodate"]["id"]]["trip_start"] == ""
    assert data[ctx["q"]["mar"]["id"]]["trip_start"] == "2027-03-10"


@pytest.mark.parametrize("term", ["jose", "JOSÉ", "pérez", "perez"])
def test_traveler_accent(ctx, term):
    assert ctx["q"]["nov"]["code"] in codes(search(ctx, q=term))


@pytest.mark.parametrize("term", ["angela", "nunez", "ÁNGELA NÚÑEZ"])
def test_executive_accent(ctx, term):
    got = codes(search(ctx, q=term))
    assert all(ctx["q"][k]["code"] in got for k in ctx["q"])


def test_client_name_and_title(ctx):
    assert len(tagged(search(ctx, q="agencia zafiro"))) == 4
    assert ctx["q"]["mar"]["code"] in codes(search(ctx, q=f"{TAG} mar"))


def test_agent_name(ctx):
    name = search(ctx, q=ctx["q"]["nov"]["code"])[0]["agent_name"]
    assert ctx["q"]["nov"]["code"] in codes(search(ctx, q=name.upper()))


@pytest.mark.parametrize("term", ["nov", "noviembre", "11/2026", "04/Nov", "04/11/2026", "04/nov/26", "04-11"])
def test_date_search(ctx, term):
    got = tagged(search(ctx, q=term))
    ids = {x["id"] for x in got}
    assert ctx["q"]["nov"]["id"] in ids, term
    assert ctx["q"]["items"]["id"] not in ids and ctx["q"]["mar"]["id"] not in ids and ctx["q"]["nodate"]["id"] not in ids


def test_date_nonmatching(ctx):
    ids = {x["id"] for x in tagged(search(ctx, q="05/Nov"))}
    assert ctx["q"]["nov"]["id"] not in ids
    ids = {x["id"] for x in tagged(search(ctx, q="mar/2027"))}
    assert ids == {ctx["q"]["mar"]["id"]}


def test_trip_range(ctx):
    got = {x["id"] for x in tagged(search(ctx, trip_from="2026-11-04", trip_to="2026-12-15"))}
    assert got == {ctx["q"]["nov"]["id"], ctx["q"]["items"]["id"]}
    got = {x["id"] for x in tagged(search(ctx, trip_from="2027-01-01"))}
    assert got == {ctx["q"]["mar"]["id"]}


def test_month_ignored_when_searching(ctx):
    # month filter in the far past -> nothing, but with q it is ignored
    assert tagged(search(ctx, date_from="2020-01-01", date_to="2020-01-31")) == []
    assert len(tagged(search(ctx, date_from="2020-01-01", date_to="2020-01-31", q="agencia zafiro"))) == 4
    assert len(tagged(search(ctx, date_from="2020-01-01", date_to="2020-01-31", trip_from="2026-01-01"))) == 3


@pytest.mark.parametrize("sort", ["trip_asc", "trip_desc"])
def test_sort(ctx, sort):
    data = search(ctx, sort=sort)
    ts = [x["trip_start"] for x in data]
    dated = [t for t in ts if t]
    assert dated == sorted(dated, reverse=sort == "trip_desc")
    first_empty = next((i for i, t in enumerate(ts) if not t), len(ts))
    assert all(not t for t in ts[first_empty:])


def test_guest_name_from_booking_confirmation(ctx):
    s, q = ctx["s"], ctx["q"]["nodate"]
    r = s.patch(f"{API}/quotations/{q['id']}/state", json={"state": "ganada"})
    assert r.status_code == 200, r.text
    r = s.post(f"{API}/quotations/{q['id']}/booking-confirmation",
               json={"lodging": [{"guest_name": "Ñoño Ibáñez"}]})
    assert r.status_code == 200, r.text
    got = search(ctx, q="nono ibanez")
    it = [x for x in got if x["id"] == q["id"]]
    assert it, "guest_name not searchable"
    assert "Ñoño Ibáñez" in it[0]["final_client_names"] and "Mariana Ortiz" in it[0]["final_client_names"]
