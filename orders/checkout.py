# orders/checkout.py
"""
One Paystack checkout attempt against an Order.

An Order can have several attempts (an abandoned card entry, a retry
next day); exactly one can end up `paid`. The unique `reference` is what
Paystack echoes back on the redirect and the webhook, and is the
idempotency key for fulfilment - see orders/checkout_service.py.

Amounts are stored in minor units (kobo/cents), the convention Paystack
and assessdesk_purchases already use, so the verify-time comparison is
an exact integer match rather than a decimal rounding question.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import JSONB, UUID

from extensions import db

CHECKOUT_PENDING = "pending"
CHECKOUT_PAID = "paid"
CHECKOUT_FAILED = "failed"
CHECKOUT_ABANDONED = "abandoned"
CHECKOUT_STATUSES = (
    CHECKOUT_PENDING,
    CHECKOUT_PAID,
    CHECKOUT_FAILED,
    CHECKOUT_ABANDONED,
)


def utcnow():
    return datetime.now(timezone.utc)


class OrderCheckout(db.Model):
    __tablename__ = "order_checkouts"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    order_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Snapshot of what was charged at initialisation time.
    amount_minor = db.Column(db.BigInteger, nullable=False)
    currency = db.Column(db.String(3), nullable=False)

    reference = db.Column(db.String(64), nullable=False, unique=True, index=True)
    status = db.Column(
        db.String(20), nullable=False, default=CHECKOUT_PENDING, index=True
    )

    authorization_url = db.Column(db.String(500), nullable=True)
    access_code = db.Column(db.String(100), nullable=True)

    # Trimmed verify payload (utils/paystack.py::summarise_gateway_data).
    gateway_response = db.Column(JSONB, nullable=True)

    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    # lazy="select": rows are locked with SELECT ... FOR UPDATE, which
    # Postgres rejects on outer-joined eager loads.
    order = db.relationship("Order", lazy="select")

    def __repr__(self):
        return f"<OrderCheckout ref={self.reference!r} status={self.status!r}>"
