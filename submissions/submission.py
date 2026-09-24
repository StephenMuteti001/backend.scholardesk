# submissions/submission.py
"""
A Submission is a versioned deliverable released to the customer for
a given Order, once it has cleared the internal integrity review (see
docs/API.md in the customer-portal frontend repo: "Writer submissions
must not be exposed to the customer until the internal integrity review
passes"). Nothing in this module creates a Submission automatically -
that is an internal/admin action outside the scope of the customer
portal this module serves; see submissions/service.py::create_submission
for the entry point a future admin/expert workflow would call.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import JSONB, UUID

from extensions import db


class SubmissionStatus:
    DELIVERED = "delivered"
    REVISION_REQUESTED = "revision_requested"
    APPROVED = "approved"
    REJECTED = "rejected"

    # Internal-only: an expert has uploaded work but it has not yet
    # cleared integrity review (see the module docstring above /
    # docs/API.md in the customer-portal frontend repo: "Writer
    # submissions must not be exposed to the customer until the
    # internal integrity review passes"). Deliberately excluded from
    # CHOICES, which is the customer-facing vocabulary -
    # customer_orders/service.py filters this status out of anything
    # a customer can see.
    PENDING_REVIEW = "pending_review"

    CHOICES = (DELIVERED, REVISION_REQUESTED, APPROVED, REJECTED)


class Submission(db.Model):
    __tablename__ = "order_submissions"

    __table_args__ = (
        db.Index("ix_order_submissions_order_id", "order_id"),
        db.Index("ix_order_submissions_status", "status"),
    )

    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    order_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    order = db.relationship(
        "Order",
        foreign_keys=[order_id],
        lazy="joined",
    )

    # 1, 2, 3, ... per order - the customer-visible revision counter.
    version = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    title = db.Column(
        db.String(255),
        nullable=False,
    )

    summary = db.Column(
        db.Text,
        nullable=True,
    )

    # [{"id": "...", "name": "...", "size": 0, "url": "..."}]
    files = db.Column(
        JSONB,
        nullable=False,
        default=list,
    )

    # Integrity-review results (0-100). Populated by whatever runs the
    # scan - see integrity_reports/ for the standalone scanning
    # feature; a submission's scores are a snapshot taken at release
    # time and are independent of that module's own records.
    ai_score = db.Column(
        db.Numeric(5, 2),
        nullable=True,
    )

    plagiarism_score = db.Column(
        db.Numeric(5, 2),
        nullable=True,
    )

    status = db.Column(
        db.String(30),
        nullable=False,
        default=SubmissionStatus.DELIVERED,
    )

    revision_note = db.Column(
        db.Text,
        nullable=True,
    )

    submitted_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "version": self.version,
            "title": self.title,
            "submittedAt": self.submitted_at.isoformat(),
            "summary": self.summary or "",
            "files": self.files or [],
            "aiScore": (
                float(self.ai_score) if self.ai_score is not None else 0
            ),
            "plagiarismScore": (
                float(self.plagiarism_score)
                if self.plagiarism_score is not None
                else 0
            ),
            "status": self.status,
            "revisionNote": self.revision_note,
        }

    def __repr__(self):
        return f"<Submission order_id={self.order_id!r} v{self.version}>"
