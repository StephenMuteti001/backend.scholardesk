# assessdesk/paystack.py
"""
AssessDesk's view of the shared Paystack client.

The implementation lives in utils/paystack.py so the customer order
checkout (orders/checkout_service.py) uses exactly the same client,
timeout and signature check. This module stays as the import path the
AssessDesk package already uses.
"""

from utils.paystack import (  # noqa: F401
    PAYSTACK_API_BASE,
    initialize_transaction,
    summarise_gateway_data,
    valid_webhook_signature,
    verify_transaction,
)

__all__ = [
    "PAYSTACK_API_BASE",
    "initialize_transaction",
    "summarise_gateway_data",
    "valid_webhook_signature",
    "verify_transaction",
]
