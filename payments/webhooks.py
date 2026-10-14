# payments/webhooks.py
"""
The single Paystack webhook for the whole platform.

Paystack delivers every event on an account to one webhook URL, so
customer order payments and AssessDesk credit purchases share this
dispatcher. It routes on the `product` key both flows write into the
transaction metadata:

    "scholardesk_order" -> orders/checkout_service.py::fulfil_checkout
    "assessdesk"        -> assessdesk/service.py::fulfil_purchase

Either URL works in the Paystack dashboard:
    POST /api/v1/payments/webhooks/paystack
    POST /api/v1/assessdesk/webhooks/paystack  (existing; delegates here)

Unauthenticated by necessity, so the HMAC-SHA512 signature over the raw
body is checked first - and even then the payload is not believed: each
fulfil function re-verifies the transaction with Paystack.
"""

import logging

from flask import Blueprint, request

from utils import paystack
from utils.exceptions import ServiceError
from utils.response_formatter import error_response, success_response

log = logging.getLogger(__name__)

webhooks_bp = Blueprint(
    "payment_webhooks",
    __name__,
    url_prefix="/api/v1/payments",
)


def _fulfilment_for(product):
    if product == "scholardesk_order":
        from orders.checkout_service import fulfil_checkout

        return fulfil_checkout

    if product == "assessdesk":
        from assessdesk.service import fulfil_purchase

        return fulfil_purchase

    return None


def handle_paystack_webhook():
    """Shared by every Paystack webhook route. Returns a Flask response."""
    raw = request.get_data()

    if not paystack.valid_webhook_signature(
        raw, request.headers.get("x-paystack-signature", "")
    ):
        return error_response("INVALID_SIGNATURE", "Invalid signature.", status=401)

    event = request.get_json(silent=True) or {}
    data = event.get("data") or {}
    reference = data.get("reference")
    fulfil = _fulfilment_for((data.get("metadata") or {}).get("product"))

    if event.get("event") == "charge.success" and fulfil and reference:
        try:
            fulfil(reference)
        except ServiceError as exc:
            log.warning(
                "[paystack] webhook fulfil failed for %s: %s", reference, exc.message
            )

    # Always 200 so Paystack stops retrying events we handled or ignore.
    return success_response(message="ok")


@webhooks_bp.post("/webhooks/paystack")
def paystack_webhook():
    return handle_paystack_webhook()
