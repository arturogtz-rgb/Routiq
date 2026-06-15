"""Iteration 12 — Fase D extra coverage:
 - affiliate logo upload + publish + public landing exposes it
 - theme publish persists into /site-settings/public
 - 'final_cta' remains last in published sections
"""
import os
import io
import httpx
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _api_url():
    with open(os.path.join(ROOT, "frontend", ".env")) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                return line.split("=", 1)[1].strip() + "/api"
    raise RuntimeError("no backend url")


API = _api_url()
MASTER = {"email": "owner@routiq.mx", "password": "Routiq2026!"}


@pytest.fixture(scope="module")
def master():
    c = httpx.Client(base_url=API, timeout=30)
    assert c.post("/auth/login", json=MASTER).status_code == 200
    yield c
    c.close()


# --- THEME ---------------------------------------------------------------
def test_theme_publish_round_trip(master):
    # set warm and publish
    assert master.patch("/site-settings", json={"theme": {"preset": "warm", "primary": "#C2410C"}}).status_code == 200
    pub_resp = master.post("/site-settings/publish")
    assert pub_resp.status_code == 200, pub_resp.text
    pub = httpx.get(f"{API}/site-settings/public", timeout=30).json()
    assert pub["theme"]["preset"] == "warm"
    assert pub["theme"]["primary"].lower() == "#c2410c"
    # restore corporate (per agent instructions) and publish
    assert master.patch("/site-settings", json={"theme": {"preset": "corporate", "primary": "#185FA5"}}).status_code == 200
    assert master.post("/site-settings/publish").status_code == 200
    pub2 = httpx.get(f"{API}/site-settings/public", timeout=30).json()
    assert pub2["theme"]["preset"] == "corporate"
    assert pub2["theme"]["primary"].lower() == "#185fa5"


# --- AFFILIATES ----------------------------------------------------------
def test_affiliate_logo_upload_and_publish(master):
    # 1x1 PNG
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c63f8cfc0f00f000301010025e8c0ad0000000049454e44ae426082"
    )
    files = {"file": ("test_logo.png", io.BytesIO(png), "image/png")}
    up = master.post("/site-settings/upload-image", files=files)
    assert up.status_code == 200, up.text
    url = up.json().get("url")
    assert url and "/uploads/" in url

    # add an affiliate logo entry via PATCH (landing.affiliate_logos)
    draft = master.get("/site-settings").json()["draft"]
    logos = list(draft.get("landing", {}).get("affiliate_logos", []))
    logos.append({"id": "TEST_logo_iter12", "name": "Aerolínea Test", "image": url, "visible": True})
    r = master.patch("/site-settings", json={"landing": {"affiliate_logos": logos}})
    assert r.status_code == 200, r.text

    # publish and verify public exposure
    assert master.post("/site-settings/publish").status_code == 200
    pub = httpx.get(f"{API}/site-settings/public", timeout=30).json()
    names = [a["name"] for a in pub["landing"].get("affiliate_logos", [])]
    assert "Aerolínea Test" in names
    section_keys = [s["key"] for s in pub["landing"]["sections"]]
    assert "affiliates" in section_keys
    assert section_keys[-1] == "final_cta"

    # cleanup: remove our test logo and re-publish
    draft2 = master.get("/site-settings").json()["draft"]
    logos2 = [l for l in draft2.get("landing", {}).get("affiliate_logos", []) if l.get("id") != "TEST_logo_iter12"]
    master.patch("/site-settings", json={"landing": {"affiliate_logos": logos2}})
    master.post("/site-settings/publish")
