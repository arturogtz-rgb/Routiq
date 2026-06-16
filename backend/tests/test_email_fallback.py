"""Verifica el fallback de correo: si el proveedor Resend de la empresa falla
(p. ej. dominio no verificado), send_email debe reintentar con la llave de
plataforma (PLATFORM_RESEND_API_KEY + PLATFORM_FROM_EMAIL)."""
import os
import asyncio
import notifications


def _setup(monkeypatch, company_ok, platform_ok, calls):
    async def fake_post(api_key, from_str, to_email, subject, html):
        calls.append((api_key, from_str))
        if api_key == "PLAT_KEY":
            return (platform_ok, 200 if platform_ok else 403, "" if platform_ok else "domain not verified")
        return (company_ok, 200 if company_ok else 403, "" if company_ok else "domain not verified")
    monkeypatch.setattr(notifications, "_resend_post", fake_post)
    monkeypatch.setenv("PLATFORM_RESEND_API_KEY", "PLAT_KEY")
    monkeypatch.setenv("PLATFORM_FROM_EMAIL", "no-reply@routiq.com.mx")


def test_company_resend_unverified_falls_back_to_platform(monkeypatch):
    calls = []
    _setup(monkeypatch, company_ok=False, platform_ok=True, calls=calls)
    company = {"name": "Service Tour", "email_provider": "resend",
               "resend": {"api_key": "COMPANY_KEY", "from_email": "no-reply@servicetourmexico.com"}}
    ok = asyncio.run(notifications.send_email(company, "user@x.com", "Reset", "<p>hi</p>"))
    assert ok is True
    # primero intenta con la empresa, luego cae a la plataforma
    assert calls[0][0] == "COMPANY_KEY"
    assert calls[-1][0] == "PLAT_KEY"
    assert "no-reply@routiq.com.mx" in calls[-1][1]


def test_no_company_provider_uses_platform(monkeypatch):
    calls = []
    _setup(monkeypatch, company_ok=False, platform_ok=True, calls=calls)
    company = {"name": "Demo", "email_provider": "resend", "resend": {}}
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    ok = asyncio.run(notifications.send_email(company, "user@x.com", "Reset", "<p>hi</p>"))
    assert ok is True
    assert calls[0][0] == "PLAT_KEY"


def test_company_resend_success_no_fallback(monkeypatch):
    calls = []
    _setup(monkeypatch, company_ok=True, platform_ok=True, calls=calls)
    company = {"name": "OK Co", "email_provider": "resend",
               "resend": {"api_key": "COMPANY_KEY", "from_email": "ok@verified.com"}}
    ok = asyncio.run(notifications.send_email(company, "user@x.com", "Hi", "<p>hi</p>"))
    assert ok is True
    assert len(calls) == 1 and calls[0][0] == "COMPANY_KEY"
