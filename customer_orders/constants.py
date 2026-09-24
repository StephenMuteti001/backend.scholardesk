# customer_orders/constants.py
"""
The customer portal sees one resource - "Order" - that spans two
backend tables across its lifecycle:

    requests.request.ServiceRequest   pre-conversion (no accepted,
                                       paid quote yet)
    orders.order.Order                post-conversion (quote accepted
                                       and paid)

The *id* the client uses for the whole lifetime of an order is always
the ServiceRequest.id (see customer_orders/service.py::serialize_order
for how the two are merged). This module holds the stage/status
vocabulary and the mapping between them and the two tables' own
native status columns.
"""

from requests.constants import (
    REQUEST_STATUS_CANCELLED,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_DELIVERED,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_NEW,
    REQUEST_STATUS_QUOTED,
    REQUEST_STATUS_REVIEWING,
)
from orders.constants import ORDER_FULFILLMENT_STAGES

# ---------------------------------------------------------------------------
# Client-facing order stage (OrderStage in the frontend)
# ---------------------------------------------------------------------------

STAGE_QUOTE_REQUESTED = "quote_requested"
STAGE_QUOTE_SENT = "quote_sent"
STAGE_AWAITING_PAYMENT = "awaiting_payment"
STAGE_MATCHING_WRITER = "matching_writer"
STAGE_IN_PROGRESS = "in_progress"
STAGE_QUALITY_REVIEW = "quality_review"
STAGE_DELIVERED = "delivered"
STAGE_REVISION_IN_PROGRESS = "revision_in_progress"
STAGE_COMPLETED = "completed"
STAGE_CANCELLED = "cancelled"

ORDER_STAGES = (
    STAGE_QUOTE_REQUESTED,
    STAGE_QUOTE_SENT,
    STAGE_AWAITING_PAYMENT,
    STAGE_MATCHING_WRITER,
    STAGE_IN_PROGRESS,
    STAGE_QUALITY_REVIEW,
    STAGE_DELIVERED,
    STAGE_REVISION_IN_PROGRESS,
    STAGE_COMPLETED,
    STAGE_CANCELLED,
)

# Pre-conversion ServiceRequest.status -> client-facing stage, for the
# statuses that map one-to-one. "quoted" is handled specially in
# customer_orders/service.py (it splits into quote_sent/awaiting_payment
# depending on whether the latest quote has been accepted yet).
REQUEST_STATUS_TO_STAGE = {
    REQUEST_STATUS_NEW: STAGE_QUOTE_REQUESTED,
    REQUEST_STATUS_REVIEWING: STAGE_QUOTE_REQUESTED,
    REQUEST_STATUS_CANCELLED: STAGE_CANCELLED,
    # Defensive fallbacks in case a request is manually pushed past
    # "quoted" by an admin without ever being converted to an Order.
    REQUEST_STATUS_IN_PROGRESS: STAGE_IN_PROGRESS,
    REQUEST_STATUS_DELIVERED: STAGE_DELIVERED,
    REQUEST_STATUS_COMPLETED: STAGE_COMPLETED,
}

# Post-conversion Order.fulfillment_stage values are already exactly
# the client-facing stage names (see orders/constants.py).
assert set(ORDER_FULFILLMENT_STAGES) <= set(ORDER_STAGES)


# ---------------------------------------------------------------------------
# Client-facing payment status (PaymentStatus in the frontend)
# ---------------------------------------------------------------------------

PAYMENT_UNPAID = "unpaid"
PAYMENT_PARTIALLY_PAID = "partially_paid"
PAYMENT_PAID = "paid"
PAYMENT_REFUND_REQUESTED = "refund_requested"
PAYMENT_REFUNDED = "refunded"

PAYMENT_STATUSES = (
    PAYMENT_UNPAID,
    PAYMENT_PARTIALLY_PAID,
    PAYMENT_PAID,
    PAYMENT_REFUND_REQUESTED,
    PAYMENT_REFUNDED,
)

# Order.status (payment state, admin-owned column) -> client-facing
# PaymentStatus.
ORDER_STATUS_TO_PAYMENT_STATUS = {
    "pending": PAYMENT_UNPAID,
    "failed": PAYMENT_UNPAID,
    "paid": PAYMENT_PAID,
    "disputed": PAYMENT_PAID,
    "partially_paid": PAYMENT_PARTIALLY_PAID,
    "refund_requested": PAYMENT_REFUND_REQUESTED,
    "refunded": PAYMENT_REFUNDED,
}


# ---------------------------------------------------------------------------
# Client-facing list tabs (?status= on GET /orders)
#
# The customer portal groups the stage vocabulary above into four
# tabs (src/lib/portal-data.ts::OrderListStatus). Quote requests that
# have not been accepted and paid for deliberately belong to none of
# them - they live on the portal's quotes surface, not the order tabs.
# ---------------------------------------------------------------------------

STATUS_ACTIVE = "active"
STATUS_DELIVERED = "delivered"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

ORDER_LIST_STATUSES = (
    STATUS_ACTIVE,
    STATUS_DELIVERED,
    STATUS_COMPLETED,
    STATUS_CANCELLED,
)

STATUS_TO_STAGES = {
    STATUS_ACTIVE: (
        STAGE_MATCHING_WRITER,
        STAGE_IN_PROGRESS,
        STAGE_QUALITY_REVIEW,
        STAGE_REVISION_IN_PROGRESS,
    ),
    STATUS_DELIVERED: (STAGE_DELIVERED,),
    STATUS_COMPLETED: (STAGE_COMPLETED,),
    STATUS_CANCELLED: (STAGE_CANCELLED,),
}


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

# Default request "type" bucket (requests/constants.py::REQUEST_TYPES)
# for quote-requests submitted through the customer portal, which does
# not currently send a type - see customer_orders/schemas.py.
DEFAULT_REQUEST_TYPE = "assignment"

DEFAULT_CURRENCY = "USD"

# Stages at which the client may still edit their own brief without it
# being flagged for a scope-creep review.
FREELY_EDITABLE_STAGES = (STAGE_QUOTE_REQUESTED, STAGE_QUOTE_SENT)

# Stages at which cancellation is no longer possible.
NON_CANCELLABLE_STAGES = (STAGE_COMPLETED, STAGE_CANCELLED)

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100

UPLOAD_SUBDIR = "orders/{user_id}/{request_id}"
