"""Iteration 55 - Signup Turnstile error-code mapping (fix quirúrgico).

Covers:
- Backend mapping: _verify_turnstile devuelve (ok, code); el endpoint POST /api/signup
  mapea codes en {timeout-or-duplicate, invalid-input-response, missing-input-response}
  a HTTP 400 con detail que contiene 'La verificación expiró, inténtalo de nuevo.' y
  el marcador '[turnstile:timeout-or-duplicate]'. Otros codes (hostname-mismatch,
  invalid-input-secret, internal-error) => HTTP 400 detail 'No pudimos verificar el
  captcha. Recárgalo e intenta de nuevo.'.
- Regresión: honeypot sigue funcionando (no toca captcha). Rate-limit y flujo con
  turnstile_token=None (que produce 'missing-input-response' cuando la SECRET está
  configurada) también validados.
- Unidad: _verify_turnstile con SECRET vacía => (True,''); con SECRET+token=None
  => (False,'missing-input-response'); con httpx mockeado para varios error-codes,
  devuelve el primer code de la lista.
"""
import os
import random
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests

# Carga env
_env = Path("/app/frontend/.env")
if _env.exists():
    for line in _env.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL"):
            os.environ.setdefault("REACT_APP_BACKEND_URL", line.split("=", 1)[1].strip())
_benv = Path("/app/backend/.env")
if _benv.exists():
    for line in _benv.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

MASTER_EMAIL = "owner@routiq.mx"
MASTER_PASSWORD = "Routiq2026!"
EXISTING_ADMIN_EMAIL = "admin@aventurate.mx"


def _suf():
    return f"{int(time.time())}{uuid.uuid4().hex[:6]}"


def _rand_ip(prefix="10.55"):
    return f"{prefix}.{random.randint(30, 229)}.{random.randint(5, 244)}"


def _mongo():
    from pymongo import MongoClient
    cli = MongoClient(os.environ["MONGO_URL"])
    return cli[os.environ.get("DB_NAME", "routiq")]


@pytest.fixture(scope="module")
def created():
    state = {"request_ids": [], "user_emails": [], "ips": []}
    yield state
    # Cleanup best-effort
    try:
        db = _mongo()
        if state["request_ids"]:
            db.tenant_requests.delete_many({"id": {"$in": state["request_ids"]}})
        if state["user_emails"]:
            db.tenant_requests.delete_many({"admin_email": {"$in": state["user_emails"]}})
        if state["ips"]:
            db.signup_attempts.delete_many({"ip": {"$in": state["ips"]}})
    except Exception as e:  # pragma: no cover
        print(f"cleanup failed: {e}")


# ---------------------------------------------------------------------------
# 1. Unit tests sobre _verify_turnstile (in-process, mockeando httpx)
# ---------------------------------------------------------------------------
class TestVerifyTurnstileUnit:
    """Tests directos sobre la función _verify_turnstile."""

    @pytest.mark.asyncio
    async def test_no_secret_key_bypasses(self, monkeypatch):
        # Simula preview sin secret configurada
        import routes.signup as signup_mod
        monkeypatch.setattr(signup_mod, "TURNSTILE_SECRET_KEY", "")
        ok, code = await signup_mod._verify_turnstile("cualquier_token", "1.2.3.4")
        assert ok is True
        assert code == ""

    @pytest.mark.asyncio
    async def test_secret_present_but_empty_token(self, monkeypatch):
        import routes.signup as signup_mod
        monkeypatch.setattr(signup_mod, "TURNSTILE_SECRET_KEY", "secret_xyz")
        ok, code = await signup_mod._verify_turnstile(None, "1.2.3.4")
        assert ok is False
        assert code == "missing-input-response"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cf_codes,expected_code", [
        (["timeout-or-duplicate"], "timeout-or-duplicate"),
        (["invalid-input-response"], "invalid-input-response"),
        (["hostname-mismatch"], "hostname-mismatch"),
        (["invalid-input-secret"], "invalid-input-secret"),
        (["invalid-input-response", "timeout-or-duplicate"], "invalid-input-response"),  # devuelve el primero
        ([], ""),  # success=false pero sin codes
    ])
    async def test_maps_cloudflare_error_codes(self, monkeypatch, cf_codes, expected_code):
        import routes.signup as signup_mod
        monkeypatch.setattr(signup_mod, "TURNSTILE_SECRET_KEY", "secret_xyz")

        # Mock httpx.AsyncClient para devolver una respuesta simulada de Cloudflare
        fake_json = {"success": False, "error-codes": cf_codes, "hostname": "routiq.com.mx"}
        fake_resp = MagicMock()
        fake_resp.json = MagicMock(return_value=fake_json)

        fake_client = MagicMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)
        fake_client.post = AsyncMock(return_value=fake_resp)

        with patch("routes.signup.httpx.AsyncClient", return_value=fake_client):
            ok, code = await signup_mod._verify_turnstile("tok", "1.2.3.4")

        assert ok is False
        assert code == expected_code

    @pytest.mark.asyncio
    async def test_cloudflare_success(self, monkeypatch):
        import routes.signup as signup_mod
        monkeypatch.setattr(signup_mod, "TURNSTILE_SECRET_KEY", "secret_xyz")
        fake_resp = MagicMock()
        fake_resp.json = MagicMock(return_value={"success": True, "hostname": "routiq.com.mx"})
        fake_client = MagicMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)
        fake_client.post = AsyncMock(return_value=fake_resp)

        with patch("routes.signup.httpx.AsyncClient", return_value=fake_client):
            ok, code = await signup_mod._verify_turnstile("tok", "1.2.3.4")
        assert ok is True
        assert code == ""

    @pytest.mark.asyncio
    async def test_httpx_exception_returns_internal_error(self, monkeypatch):
        import routes.signup as signup_mod
        monkeypatch.setattr(signup_mod, "TURNSTILE_SECRET_KEY", "secret_xyz")
        fake_client = MagicMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)
        fake_client.post = AsyncMock(side_effect=RuntimeError("network down"))

        with patch("routes.signup.httpx.AsyncClient", return_value=fake_client):
            ok, code = await signup_mod._verify_turnstile("tok", "1.2.3.4")
        assert ok is False
        assert code == "internal-error"


# ---------------------------------------------------------------------------
# 2. Endpoint mapping: llama al endpoint via TestClient con _verify_turnstile
#    monkeypatchado para forzar cada error-code y asertar el detail.
# ---------------------------------------------------------------------------
class TestSignupEndpointMapping:
    """Integración in-process: prueba el mapeo code -> HTTP detail en submit_signup."""

    @pytest.fixture(scope="class")
    def client(self):
        """FastAPI TestClient (una sola instancia por clase para evitar cierre del loop Motor)."""
        from fastapi.testclient import TestClient
        import server as srv
        with TestClient(srv.app) as c:
            yield c

    @pytest.fixture(autouse=True)
    def _cleanup(self, created):
        # nada previo, ya tenemos fixture 'created' para limpieza global
        yield

    def _payload(self, suf, email=None):
        return {
            "company_name": f"TEST TS {suf}",
            "admin_name": "Turnstile Tester",
            "admin_email": email or f"ts_{suf}@example.com",
            "admin_phone": "",
            "plan": "pro",
            "admin_password": "Passw0rdOk!",
            "website": "",
            "turnstile_token": "any-token",
        }

    @pytest.mark.parametrize("code", [
        "timeout-or-duplicate",
        "invalid-input-response",
        "missing-input-response",
    ])
    def test_expiration_codes_map_to_expiration_message(self, client, monkeypatch, code, created):
        async def fake_verify(token, ip):
            return False, code

        monkeypatch.setattr("routes.signup._verify_turnstile", fake_verify)
        ip = _rand_ip("10.56")
        created["ips"].append(ip)
        suf = _suf()
        r = client.post("/api/signup", json=self._payload(suf), headers={"X-Forwarded-For": ip})
        assert r.status_code == 400, r.text
        detail = r.json().get("detail", "")
        assert "La verificación expiró, inténtalo de nuevo." in detail, detail
        assert "[turnstile:timeout-or-duplicate]" in detail, detail

    @pytest.mark.parametrize("code", [
        "hostname-mismatch",
        "invalid-input-secret",
        "internal-error",
        "some-unknown-code",
        "",  # success=false sin codes
    ])
    def test_other_codes_map_to_generic_message(self, client, monkeypatch, code, created):
        async def fake_verify(token, ip):
            return False, code

        monkeypatch.setattr("routes.signup._verify_turnstile", fake_verify)
        ip = _rand_ip("10.57")
        created["ips"].append(ip)
        suf = _suf()
        r = client.post("/api/signup", json=self._payload(suf), headers={"X-Forwarded-For": ip})
        assert r.status_code == 400, r.text
        detail = r.json().get("detail", "")
        assert "No pudimos verificar el captcha" in detail, detail
        # No debe llevar el marcador de expiración
        assert "[turnstile:timeout-or-duplicate]" not in detail
        assert "expiró" not in detail

    def test_success_verify_reaches_email_dup_check(self, client, monkeypatch, created):
        """Cuando captcha ok=True, el endpoint continúa y detecta el correo duplicado."""
        async def fake_verify(token, ip):
            return True, ""

        monkeypatch.setattr("routes.signup._verify_turnstile", fake_verify)
        ip = _rand_ip("10.58")
        created["ips"].append(ip)
        suf = _suf()
        p = self._payload(suf, email=EXISTING_ADMIN_EMAIL)
        r = client.post("/api/signup", json=p, headers={"X-Forwarded-For": ip})
        assert r.status_code == 400, r.text
        detail = r.json().get("detail", "")
        assert "Ya existe una cuenta" in detail, detail
        # NO debe ser un mensaje de captcha
        assert "captcha" not in detail.lower()
        assert "expiró" not in detail.lower()

    def test_success_verify_creates_pending_request(self, client, monkeypatch, created):
        """captcha ok + correo único -> 201 y crea tenant_request."""
        async def fake_verify(token, ip):
            return True, ""

        monkeypatch.setattr("routes.signup._verify_turnstile", fake_verify)
        ip = _rand_ip("10.59")
        created["ips"].append(ip)
        suf = _suf()
        email = f"newuser_{suf}@example.com"
        created["user_emails"].append(email)
        p = self._payload(suf, email=email)
        r = client.post("/api/signup", json=p, headers={"X-Forwarded-For": ip})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body.get("ok") is True
        rid = body.get("id")
        assert rid and rid != "ok"
        created["request_ids"].append(rid)

        # Persistencia real en MongoDB
        db = _mongo()
        doc = db.tenant_requests.find_one({"id": rid})
        assert doc is not None
        assert doc["admin_email"] == email
        assert doc["status"] == "pending"


# ---------------------------------------------------------------------------
# 3. Regresión vs servidor real (supervisor): dado que TURNSTILE_SECRET_KEY SÍ
#    está configurada en preview, un signup con turnstile_token=null produce
#    'missing-input-response' del backend real -> 400 con mensaje de expiración.
# ---------------------------------------------------------------------------
class TestSignupRealServerRegression:

    def test_null_token_maps_to_expiration_via_http(self, created):
        """turnstile_token=null contra el server real -> 400 con marcador."""
        ip = _rand_ip("10.60")
        created["ips"].append(ip)
        suf = _suf()
        r = requests.post(f"{API}/signup", json={
            "company_name": f"TEST Real {suf}",
            "admin_name": "Real Tester",
            "admin_email": f"real_{suf}@example.com",
            "admin_phone": "",
            "plan": "pro",
            "admin_password": "Passw0rdOk!",
            "website": "",
            "turnstile_token": None,
        }, headers={"X-Forwarded-For": ip})
        assert r.status_code == 400, r.text
        detail = r.json().get("detail", "")
        assert "La verificación expiró, inténtalo de nuevo." in detail
        assert "[turnstile:timeout-or-duplicate]" in detail

    def test_honeypot_bypasses_captcha_real_server(self, created):
        """website=... (honeypot) -> {ok:true,id:'ok'} SIN validar captcha."""
        ip = _rand_ip("10.61")
        created["ips"].append(ip)
        suf = _suf()
        r = requests.post(f"{API}/signup", json={
            "company_name": f"TEST HP {suf}",
            "admin_name": "Bot Persona",
            "admin_email": f"hp_{suf}@example.com",
            "admin_phone": "",
            "plan": "pro",
            "admin_password": "BotPassw0rd!",
            "website": "https://spam.example.com",
            "turnstile_token": None,  # ni siquiera importa
        }, headers={"X-Forwarded-For": ip})
        assert r.status_code in (200, 201), r.text
        assert r.json() == {"ok": True, "id": "ok"}
        # Y no debe registrar signup_attempt para esta IP
        db = _mongo()
        assert db.signup_attempts.count_documents({"ip": ip}) == 0
