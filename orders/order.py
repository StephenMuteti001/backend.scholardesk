# orders/order.py

import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from extensions import db


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Human-readable public order reference.
    reference = db.Column(
        String(32),
        unique=True,
        nullable=False,
        index=True,
    )

    # Customer who purchased / commissioned the work.
    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # request | material
    source_type = db.Column(
        String(20),
        nullable=False,
        index=True,
    )

    # Populated when this order originated from a service request.
    request_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("service_requests.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    # Populated when this order originated from an exam-material purchase.
    material_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("exam_materials.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    # Snapshot of what was purchased/commissioned.
    #
    # This is deliberate.
    # If the original request/material title changes later,
    # historical orders should still display the original title.
    item_title = db.Column(
        String(500),
        nullable=False,
    )

    amount = db.Column(
        Numeric(14, 2),
        nullable=False,
    )

    currency = db.Column(
        String(3),
        nullable=False,
        default="USD",
    )

    gateway = db.Column(
        String(50),
        nullable=False,
        index=True,
    )

    status = db.Column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )

    # Post-conversion fulfilment workflow stage, as surfaced to the
    # customer portal (see customer_orders/constants.py::FULFILLMENT_STAGES).
    # Kept deliberately separate from `status`, which tracks the
    # *payment* state and is what the existing admin screens read/write.
    fulfillment_stage = db.Column(
        String(30),
        nullable=True,
        index=True,
    )

    # Append-only customer-visible activity log:
    # [{"id": "...", "at": "...", "actor": "client|support|writer|system",
    #   "title": "...", "detail": "..."}]
    activity_log = db.Column(
        JSONB,
        nullable=False,
        default=list,
    )

    # Optional payment/provider reference.
    payment_reference = db.Column(
        String(255),
        nullable=True,
        index=True,
    )

    # Optional notes maintained by administrators.
    notes = db.Column(
        Text,
        nullable=True,
    )

    # Refund information.
    refunded_amount = db.Column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    refund_reason = db.Column(
        String(100),
        nullable=True,
    )

    refunded_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    # -----------------------------------------------------------------------
    # Fulfilment: the expert assigned to do the work, and what the
    # platform pays them for it. Distinct from `amount` above, which is
    # what the *customer* pays. The assigned expert itself lives on
    # ServiceRequest.assigned_to (requests/request.py) rather than
    # being duplicated here - see orders/service.py::OrderService.assign_expert.
    # -----------------------------------------------------------------------

    expert_budget = db.Column(
        Numeric(14, 2),
        nullable=True,
    )

    # pending (assigned, awaiting the expert's accept/decline) |
    # accepted | declined. Distinct from fulfillment_stage: an order
    # only moves to fulfillment_stage "in_progress" once the expert
    # actually accepts - see orders/service.py::OrderService
    # .accept_assignment/.decline_assignment.
    assignment_status = db.Column(
        String(20),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
        index=True,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    customer = db.relationship(
        "User",
        foreign_keys=[customer_id],
        lazy="joined",
    )

    request = db.relationship(
        "ServiceRequest",
        foreign_keys=[request_id],
        lazy="joined",
    )

    material = db.relationship(
        "ExamMaterial",
        foreign_keys=[material_id],
        lazy="joined",
    )

    __table_args__ = (
        CheckConstraint(
            "amount >= 0",
            name="ck_orders_amount_non_negative",
        ),
        CheckConstraint(
            "refunded_amount >= 0",
            name="ck_orders_refunded_amount_non_negative",
        ),
        CheckConstraint(
            """
            (
                source_type = 'request'
                AND request_id IS NOT NULL
                AND material_id IS NULL
            )
            OR
            (
                source_type = 'material'
                AND material_id IS NOT NULL
                AND request_id IS NULL
            )
            """,
            name="ck_orders_valid_source",
        ),
        Index(
            "ix_orders_customer_created",
            "customer_id",
            "created_at",
        ),
        Index(
            "ix_orders_status_created",
            "status",
            "created_at",
        ),
    )

    def __repr__(self):
        return f"<Order {self.reference}>"