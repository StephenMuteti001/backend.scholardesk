# orders/constants.py

ORDER_STATUSES = (
    "paid",
    "pending",
    "failed",
    "refunded",
    "disputed",
    # Added for the customer-portal payment flow (customer_orders/) -
    # additive only, existing admin flows never set these.
    "partially_paid",
    "refund_requested",
)

ORDER_GATEWAYS = (
    "Stripe",
    "PayPal",
    "Bank Transfer",
    "Wise",
    # Added for the customer-portal self-serve checkout
    # (customer_orders/) pending a real payment-gateway integration -
    # see customer_orders/service.py::pay_order().
    "Online Payment",
)

# Post-conversion fulfilment stages (Order.fulfillment_stage), as
# surfaced to the customer portal. Distinct from ORDER_STATUSES, which
# is the *payment* state.
ORDER_FULFILLMENT_STAGES = (
    "matching_writer",
    "in_progress",
    "quality_review",
    "delivered",
    "revision_in_progress",
    "completed",
    "cancelled",
)

ORDER_SOURCE_TYPES = (
    "request",
    "material",
)

ORDER_SORT_FIELDS = {
    "ref": "reference",
    "createdAt": "created_at",
    "amount": "amount",
    "gateway": "gateway",
    "status": "status",
}

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100

REFUND_REASONS = (
    "customer-request",
    "duplicate-payment",
    "service-not-delivered",
    "material-not-delivered",
    "administrative",
    "other",
)
# Expert's acceptance state for an assignment - see
# orders/order.py::Order.assignment_status.
ASSIGNMENT_STATUS_PENDING = "pending"
ASSIGNMENT_STATUS_ACCEPTED = "accepted"
ASSIGNMENT_STATUS_DECLINED = "declined"

ASSIGNMENT_STATUSES = (
    ASSIGNMENT_STATUS_PENDING,
    ASSIGNMENT_STATUS_ACCEPTED,
    ASSIGNMENT_STATUS_DECLINED,
)
