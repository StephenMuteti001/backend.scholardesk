# integrity_reports/integrity_report.py
"""
Standalone AI-content / plagiarism scanning that a customer can run
against their own document, independent of any order (see docs/API.md
in the customer-portal frontend repo, "Integrity reports").

NOTE: there is no real scanning engine wired in yet (no Turnitin /
Copyleaks / GPTZero integration exists anywhere in this codebase).
integrity_reports/service.py runs a clearly-labelled placeholder
scorer so the endpoint contract is correct end-to-end today; swap
`_run_scan()` there for a real provider call when one is procured.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import JSONB, UUID

from extensions import db


class IntegrityStatus:
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"

    CHOICES = (QUEUED, PROCESSING, READY, FAILED)


class IntegrityReport(db.Model):
    __tablename__ = "integrity_reports"

    __table_args__ = (
        db.Index("ix_integrity_reports_customer_id", "customer_id"),
        db.Index("ix_integrity_reports_status", "status"),
    )

    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    customer = db.relationship(
        "User",
        foreign_keys=[customer_id],
        lazy="joined",
    )

    file_name = db.Column(
        db.String(255),
        nullable=False,
    )

    word_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    # Where the uploaded document itself was written to, if a file was
    # submitted (see utils/uploads.py). Null for the JSON-only,
    # metadata-only submission path.
    file_path = db.Column(
        db.String(500),
        nullable=True,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default=IntegrityStatus.QUEUED,
    )

    check_ai = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    check_plagiarism = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    ai_score = db.Column(
        db.Numeric(5, 2),
        nullable=True,
    )

    plagiarism_score = db.Column(
        db.Numeric(5, 2),
        nullable=True,
    )

    # [{"source": "...", "overlap": 1.8}]
    top_matches = db.Column(
        JSONB,
        nullable=True,
    )

    report_url = db.Column(
        db.String(500),
        nullable=True,
    )

    submitted_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    completed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "fileName": self.file_name,
            "wordCount": self.word_count,
            "submittedAt": self.submitted_at.isoformat(),
            "status": self.status,
            "checks": {
                "ai": self.check_ai,
                "plagiarism": self.check_plagiarism,
            },
            "aiScore": (
                float(self.ai_score) if self.ai_score is not None else None
            ),
            "plagiarismScore": (
                float(self.plagiarism_score)
                if self.plagiarism_score is not None
                else None
            ),
            "topMatches": self.top_matches,
            "reportUrl": self.report_url,
        }

    def __repr__(self):
        return f"<IntegrityReport {self.id} {self.file_name!r}>"
