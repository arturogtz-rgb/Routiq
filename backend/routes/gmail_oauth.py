"""Per-tenant Gmail OAuth2.

Each company registers its OWN Google OAuth client (Client ID + Secret) in
Settings → Correo. This module runs the authorization-code flow using those
per-tenant credentials, stores the refresh token on the company, and lets the
app send email through the Gmail API.

Scope: gmail.send (send only) + userinfo.email (to show the connected address).
"""
import os
import time
import logging
from urllib.parse import urlencode

import jwt
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from database import get_db
from auth import require_roles, _secret, JWT_ALGORITHM

log = logging.getLogger("routiq.gmail")
router = APIRouter()

# Public base of the BACKEND (where Google redirects). Configurable per deploy.
OAUTH_REDIRECT_BASE = os.environ.get("OAUTH_REDIRECT_BASE", "https://routiq.com.mx").rstrip("/")
REDIRECT_URI = f"{OAUTH_REDIRECT_BASE}/api/oauth/gmail/callback"
# Where to send the browser back after the flow (frontend settings page).
APP_SETTINGS_URL = os.environ.get("APP_SETTINGS_URL", f"{OAUTH_REDIRECT_BASE}/app/settings")

SCOPES = "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/userinfo.email openid"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"


def _sign_state(tenant_id: str) -> str:
    payload = {"t": tenant_id, "scope": "gmail_oauth", "exp": int(time.time()) + 600}
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def _verify_state(state: str) -> str:
    try:
        data = jwt.decode(state, _secret(), algorithms=[JWT_ALGORITHM])
        if data.get("scope") != "gmail_oauth":
            raise ValueError("bad scope")
        return data["t"]
    except Exception:
        raise HTTPException(status_code=400, detail="Estado OAuth inválido o expirado.")


@router.get("/oauth/gmail/authorize")
async def gmail_authorize(user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0, "gmail": 1})
    gmail = (company or {}).get("gmail") or {}
    if not gmail.get("client_id") or not gmail.get("client_secret"):
        raise HTTPException(status_code=400, detail="Primero guarda tu Client ID y Client Secret de Google.")
    params = {
        "client_id": gmail["client_id"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": _sign_state(user["tenant_id"]),
    }
    return {"url": f"{AUTH_ENDPOINT}?{urlencode(params)}", "redirect_uri": REDIRECT_URI}


@router.get("/oauth/gmail/callback")
async def gmail_callback(state: str = Query(...), code: str | None = Query(default=None),
                         error: str | None = Query(default=None)):
    # Browser redirect from Google — no auth header; trust the signed state.
    if error:
        return RedirectResponse(f"{APP_SETTINGS_URL}?gmail=error")
    try:
        tenant_id = _verify_state(state)
    except HTTPException:
        return RedirectResponse(f"{APP_SETTINGS_URL}?gmail=error")
    if not code:
        return RedirectResponse(f"{APP_SETTINGS_URL}?gmail=error")
    db = get_db()
    company = await db.companies.find_one({"id": tenant_id}, {"_id": 0, "gmail": 1})
    gmail = (company or {}).get("gmail") or {}
    if not gmail.get("client_id"):
        return RedirectResponse(f"{APP_SETTINGS_URL}?gmail=error")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            tok = await client.post(TOKEN_ENDPOINT, data={
                "code": code,
                "client_id": gmail["client_id"],
                "client_secret": gmail["client_secret"],
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            })
            tok.raise_for_status()
            tj = tok.json()
            refresh_token = tj.get("refresh_token")
            access_token = tj.get("access_token")
            email = ""
            if access_token:
                ui = await client.get(USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {access_token}"})
                if ui.status_code == 200:
                    email = ui.json().get("email", "")
    except Exception:
        log.exception("gmail token exchange failed")
        return RedirectResponse(f"{APP_SETTINGS_URL}?gmail=error")

    if not refresh_token:
        # Happens if the user previously consented; force consent gave us one, but guard anyway.
        return RedirectResponse(f"{APP_SETTINGS_URL}?gmail=norefresh")

    await db.companies.update_one({"id": tenant_id}, {"$set": {
        "gmail.refresh_token": refresh_token,
        "gmail.email": email,
        "email_provider": "gmail",
    }})
    return RedirectResponse(f"{APP_SETTINGS_URL}?gmail=connected")


@router.post("/oauth/gmail/disconnect")
async def gmail_disconnect(user: dict = Depends(require_roles("company_admin"))):
    db = get_db()
    await db.companies.update_one({"id": user["tenant_id"]}, {
        "$unset": {"gmail.refresh_token": "", "gmail.email": ""},
    })
    company = await db.companies.find_one({"id": user["tenant_id"]}, {"_id": 0})
    from deps import _integrations_view
    return _integrations_view(company)
