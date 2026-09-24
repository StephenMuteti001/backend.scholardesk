import uuid
from datetime import datetime

from sqlalchemy.dialects.postgresql import UUID

from extensions import db


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    expert_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("experts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    period_start = db.Column(
        db.Date,
        nullable=False,
        index=True,
    )

    period_end = db.Column(
        db.Date,
        nullable=False,
        index=True,
    )

    jobs = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0,
    )

    currency = db.Column(
        db.String(3),
        nullable=False,
        default="USD",
    )

    payment_method = db.Column(
        db.String(50),
        nullable=False,
        default="bank_transfer",
    )

    due_at = db.Column(
        db.DateTime,
        nullable=True,
        index=True,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="scheduled",
        index=True,
    )

    processed_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    processed_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    paid_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    external_reference = db.Column(
        db.String(255),
        nullable=True,
        unique=True,
    )

    notes = db.Column(
        db.Text,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self):
        return (
            f"<Payment "
            f"id={self.id!r} "
            f"expert_id={self.expert_id!r} "
            f"status={self.status!r}>"
        )