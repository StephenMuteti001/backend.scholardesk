from datetime import datetime
from uuid import uuid4

from sqlalchemy.dialects.postgresql import UUID

from extensions import db


class ExamMaterial(db.Model):
    __tablename__ = "exam_materials"

    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    title = db.Column(
        db.String(255),
        nullable=False,
    )

    description = db.Column(
        db.Text,
        nullable=True,
    )

    exam = db.Column(
        db.String(100),
        nullable=False,
        index=True,
    )

    subject = db.Column(
        db.String(100),
        nullable=False,
        index=True,
    )

    expert_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("experts.id"),
        nullable=True,
        index=True,
    )

    status = db.Column(
        db.String(30),
        nullable=False,
        default="draft",
        index=True,
    )

    price = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0,
    )

    downloads = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    revenue = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0,
    )

    # File metadata
    file_url = db.Column(
        db.Text,
        nullable=True,
    )

    file_name = db.Column(
        db.String(255),
        nullable=True,
    )

    file_size = db.Column(
        db.BigInteger,
        nullable=True,
    )

    mime_type = db.Column(
        db.String(100),
        nullable=True,
    )

    storage_key = db.Column(
        db.Text,
        nullable=True,
    )

    page_count = db.Column(
        db.Integer,
        nullable=True,
    )

    # ---------------------------------------------------------------
    # Customer-portal display fields (additive - the original admin
    # model only tracked exam/subject/status/price). None of this is
    # read or written by the existing admin routes/schemas.
    # ---------------------------------------------------------------

    level = db.Column(
        db.String(30),
        nullable=True,
        default="Undergraduate",
    )

    category = db.Column(
        db.String(50),
        nullable=True,
        default="Study guides",
    )

    institution = db.Column(
        db.String(255),
        nullable=True,
    )

    year = db.Column(
        db.Integer,
        nullable=True,
    )

    format = db.Column(
        db.String(10),
        nullable=True,
        default="PDF",
    )

    currency = db.Column(
        db.String(3),
        nullable=False,
        default="USD",
    )

    rating = db.Column(
        db.Numeric(2, 1),
        nullable=False,
        default=0,
    )

    # Review information
    reviewed_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    reviewed_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    published_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    archived_at = db.Column(
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
        index=True,
    )

    # Relationships
    expert = db.relationship(
        "Expert",
        back_populates="exam_materials",
    )

    reviewer = db.relationship(
        "User",
        foreign_keys=[reviewed_by],
    )

    def __repr__(self):
        return (
            f"<ExamMaterial "
            f"id={self.id} "
            f"title={self.title!r} "
            f"status={self.status!r}>"
        )