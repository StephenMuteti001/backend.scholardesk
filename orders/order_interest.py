# orders/order_interest.py
"""
Expert "I'm interested" registrations against unassigned orders.

This is deliberately *advisory* only: registering interest never
reserves, locks or assigns an order. Support remains the only actor
that assigns work (see orders/service.py::OrderService.assign_expert),
and may still assign any active expert - interested or not.

One row per (order, expert). Withdrawing sets `withdrawn_at` rather
than deleting the row, so support keeps the full history of who put
their hand up and who later pulled it back; re-registering simply
clears the timestamp again.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy.dialects.postgresql import UUID

from extensions import db


class OrderInterest(db.Model):
    __tablename__ = "order_interests"

    __table_args__ = (
        db.UniqueConstraint(
            "order_id",
            "expert_id",
            name="uq_order_interests_order_expert",
        ),
        db.Index(
            "ix_order_interests_order_id_created_at",
            "order_id",
            "created_at",
        ),
    )

    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    order_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    expert_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("experts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional short pitch the expert may attach to their interest.
    note = db.Column(
        db.Text,
        nullable=True,
    )

    # Set when the expert withdraws; NULL means the interest stands.
    withdrawn_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    order = db.relationship(
        "Order",
        backref=db.backref(
            "interests",
            lazy="dynamic",
            cascade="all, delete-orphan",
            passive_deletes=True,
        ),
    )

    expert = db.relationship("Expert")

    @property
    def is_active(self):
        return self.withdrawn_at is None

    def __repr__(self):
        return (
            f"<OrderInterest "
            f"order_id={self.order_id} "
            f"expert_id={self.expert_id} "
            f"withdrawn={self.withdrawn_at is not None}>"
        )
