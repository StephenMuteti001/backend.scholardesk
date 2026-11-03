# contact/contact_message.py
"""Messages sent through the public website's Contact form."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import UUID

from extensions import db

CONTACT_STATUSES = ("new", "in_progress", "resolved", "spam")
CONTACT_TOPICS = (
    "general",
    "order",
    "pricing",
    "expert_application",
    "partnership",
    "other",
)


class ContactMessage(db.Model):
    __tablename__ = "contact_messages"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference = db.Column(db.String(20), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, index=True)
    topic = db.Column(db.String(40), nullable=False, default="general")
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="new", index=True)
    source_page = db.Column(db.String(255), nullable=True)
    ip_address = db.Column(db.String(64), nullable=True, index=True)
    user_agent = db.Column(db.String(400), nullable=True)
    admin_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
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
            "reference": self.reference,
            "name": self.name,
            "email": self.email,
            "topic": self.topic,
            "subject": self.subject,
            "message": self.message,
            "status": self.status,
            "source_page": self.source_page,
            "admin_note": self.admin_note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
