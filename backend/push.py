"""Web Push (VAPID) helpers — self-hosted, no third-party vendor.

VAPID keys are generated once and stored in `app_config`. Subscriptions live in
`push_subscriptions`. Sending uses pywebpush.
"""
from __future__ import annotations
import base64
import json
import logging

from py_vapid import Vapid01
from cryptography.hazmat.primitives import serialization
from pywebpush import webpush, WebPushException

log = logging.getLogger("routiq.push")
VAPID_SUBJECT = "mailto:soporte@routiq.mx"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate_vapid_keys() -> dict:
    v = Vapid01()
    v.generate_keys()
    pub_raw = v.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    priv_val = v.private_key.private_numbers().private_value
    priv_bytes = priv_val.to_bytes(32, "big")
    return {"public_key": _b64(pub_raw), "private_key": _b64(priv_bytes)}


def send_push(subscription: dict, payload: dict, vapid: dict) -> int:
    """Send a push. Returns HTTP-ish status: 201 ok, 404/410 expired, 0 other error."""
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=vapid["private_key"],
            vapid_claims={"sub": VAPID_SUBJECT},
        )
        return 201
    except WebPushException as e:
        status = getattr(getattr(e, "response", None), "status_code", 0) or 0
        if status not in (404, 410):
            log.warning("web push failed (%s): %s", status, e)
        return status
    except Exception as e:
        log.warning("web push error: %s", e)
        return 0
