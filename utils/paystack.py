# utils/paystack.py
"""
Shared Paystack client (initialize, verify, webhook signature).

Every Paystack call in the platform goes through this module - the
AssessDesk credit purchases (assessdesk/service.py) and the customer
order checkout (orders/checkout_service.py). One client means one place
for the secret key, the timeout, the error translation and the HMAC
signature check.
"""

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app

from utils.exceptions import ServiceError

log = logging.getLogger(__name__)

PAYSTACK_API_BASE = "https://api.paystack.co"

_TIMEOUT = 10


def _secret():
    key = current_app.config.get("PAYSTACK_SECRET_KEY")
    if not key:
        raise ServiceError(
            "PAYMENTS_UNAVAILABLE",
            "Payments are not configured.",
            status_code=503,
        )
    return key


def _call(method, path, json_body=None):
    # NOTE: stdlib urllib on purpose - the project's local `requests/`
    # blueprint package shadows the third-party `requests` library.
    data = json.dumps(json_body).encode() if json_body is not None else None
    req = urllib.request.Request(
        f"{PAYSTACK_API_BASE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_secret()}",
            "Content-Type": "application/json",
        },
    )
    status, raw = 0, b""
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        log.exception("[paystack] network error on %s", path)
        raise ServiceError(
            "PAYMENT_GATEWAY_ERROR",
            "The payment service is unreachable. Please try again.",
            status_code=502,
        )
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        body = {}
    if status >= 400 or not body.get("status"):
        log.warning(
            "[paystack] %s %s -> %s %s", method, path, status, body.get("message")
        )
        raise ServiceError(
            "PAYMENT_GATEWAY_ERROR",
            "The payment service rejected the request.",
            status_code=502,
        )
    return body.get("data") or {}


def initialize_transaction(
    *, email, amount_minor, currency, reference, callback_url, metadata
):
    return _call(
        "POST",
        "/transaction/initialize",
        {
            "email": email,
            "amount": int(amount_minor),
            "currency": currency,
            "reference": reference,
            "callback_url": callback_url,
            "metadata": metadata,
        },
    )


def verify_transaction(reference):
    # The reference is quoted: it reaches us from a webhook body and a
    # URL path, so it must never be able to alter the request path.
    return _call(
        "GET",
        f"/transaction/verify/{urllib.parse.quote(str(reference), safe='')}",
    )


def valid_webhook_signature(raw_body: bytes, signature: str) -> bool:
    if not signature:
        return False
    expected = hmac.new(_secret().encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


def summarise_gateway_data(data):
    """
    The subset of Paystack's verify payload worth persisting. Excludes
    card and customer detail on purpose.
    """
    keys = (
        "id",
        "status",
        "amount",
        "currency",
        "channel",
        "paid_at",
        "gateway_response",
    )
    return {k: (data or {}).get(k) for k in keys}
