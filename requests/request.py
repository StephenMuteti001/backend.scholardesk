# requests/request.py

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from extensions import db


class ServiceRequest(db.Model):
    __tablename__ = "service_requests"

    __table_args__ = (
        Index("ix_service_requests_customer_id", "customer_id"),
        Index("ix_service_requests_type", "type"),
        Index("ix_service_requests_status", "status"),
        Index("ix_service_requests_priority", "priority"),
        Index("ix_service_requests_assigned_to", "assigned_to"),
        Index("ix_service_requests_deadline", "deadline"),
        Index("ix_service_requests_updated_at", "updated_at"),
        Index("ix_service_requests_created_at", "created_at"),
    )

    # -----------------------------------------------------------------------
    # Identity
    # -----------------------------------------------------------------------

    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    ref = db.Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    # -----------------------------------------------------------------------
    # Core request information
    # -----------------------------------------------------------------------

    title = db.Column(
        String(255),
        nullable=False,
    )

    subject = db.Column(
        String(255),
        nullable=True,
    )

    description = db.Column(
        Text,
        nullable=True,
    )

    type = db.Column(
        String(50),
        nullable=False,
    )

    status = db.Column(
        String(50),
        nullable=False,
        default="new",
    )

    priority = db.Column(
        String(50),
        nullable=False,
        default="normal",
    )

    # -----------------------------------------------------------------------
    # Customer
    # -----------------------------------------------------------------------

    customer_id = db.Column(
        db.Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    customer = relationship(
        "User",
        foreign_keys=[customer_id],
        lazy="joined",
    )

    # -----------------------------------------------------------------------
    # Assignment
    # -----------------------------------------------------------------------

    assigned_to = db.Column(
        db.Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    assigned_user = relationship(
        "User",
        foreign_keys=[assigned_to],
        lazy="joined",
    )

    # -----------------------------------------------------------------------
    # Commercial information
    # -----------------------------------------------------------------------

    budget = db.Column(
        Numeric(14, 2),
        nullable=True,
    )

    currency = db.Column(
        String(10),
        nullable=False,
        default="USD",
    )

    # Quotes made during the request lifecycle.
    #
    # Example:
    #
    # [
    #   {
    #       "amount": 150,
    #       "currency": "USD",
    #       "deadline": "2026-09-01T12:00:00Z",
    #       "notes": "Includes two revisions",
    #       "created_at": "...",
    #       "created_by": "..."
    #   }
    # ]
    quotes = db.Column(
        JSONB,
        nullable=False,
        default=list,
    )

    # Files attached to the brief by the customer:
    # [{"id": "...", "name": "...", "size": 0, "url": "..."}]
    files = db.Column(
        JSONB,
        nullable=False,
        default=list,
    )

    # Append-only customer-visible activity log, same shape as
    # orders.order.Order.activity_log - the two are concatenated by
    # customer_orders/service.py when a request has converted to an
    # order, so the client portal sees one continuous timeline.
    activity_log = db.Column(
        JSONB,
        nullable=False,
        default=list,
    )

    # -----------------------------------------------------------------------
    # Request-specific information
    # -----------------------------------------------------------------------

    tags = db.Column(
        JSONB,
        nullable=False,
        default=list,
    )

    metadata_json = db.Column(
        JSONB,
        nullable=False,
        default=dict,
    )

    # -----------------------------------------------------------------------
    # Deadline
    # -----------------------------------------------------------------------

    deadline = db.Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # -----------------------------------------------------------------------
    # Order conversion
    #
    # A request becomes an order when the commercial agreement is reached.
    # Keep this relationship separate from request status.
    # -----------------------------------------------------------------------

    order_id = db.Column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="SET NULL", use_alter=True, name="fk_service_requests_order_id"),
        nullable=True,
        index=True,
    )

    converted_at = db.Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    created_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    completed_at = db.Column(
        DateTime(timezone=True),
        nullable=True,
    )

    cancelled_at = db.Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # -----------------------------------------------------------------------
    # Reminder
    # -----------------------------------------------------------------------

    last_reminder_at = db.Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # -----------------------------------------------------------------------
    # Convenience methods
    # -----------------------------------------------------------------------

    def __repr__(self):
        return (
            f"<ServiceRequest "
            f"id={self.id!r} "
            f"ref={self.ref!r} "
            f"type={self.type!r} "
            f"status={self.status!r}>"
        )