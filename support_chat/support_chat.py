# support_chat/support_chat.py
"""
Customer <-> support-team chat. Writers/experts are never participants
(see docs/API.md in the customer-portal frontend repo: "Chats belong
to the customer <-> support team. Experts are never participants.").
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import JSONB, UUID

from extensions import db


class ChatStatus:
    OPEN = "open"
    PENDING = "pending"
    RESOLVED = "resolved"
    ARCHIVED = "archived"

    CHOICES = (OPEN, PENDING, RESOLVED, ARCHIVED)


class ChatAuthor:
    CUSTOMER = "customer"
    EXPERT = "expert"
    SUPPORT = "support"

    CHOICES = (CUSTOMER, EXPERT, SUPPORT)


class SupportThread(db.Model):
    __tablename__ = "support_threads"

    __table_args__ = (
        db.Index("ix_support_threads_customer_id", "customer_id"),
        db.Index("ix_support_threads_status", "status"),
        db.Index("ix_support_threads_updated_at", "updated_at"),
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

    subject = db.Column(
        db.String(255),
        nullable=False,
    )

    # Free-text display reference to an order/request (e.g. "AH-1041"),
    # deliberately NOT a foreign key - a thread can reference an order,
    # a request still awaiting a quote, or nothing at all (a general
    # support question), and the customer refers to it by its human
    # reference either way.
    order_reference = db.Column(
        db.String(50),
        nullable=True,
        index=True,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default=ChatStatus.OPEN,
    )

    # Assigned support agent. Nullable until support picks up the
    # thread; the customer portal shows a generic "Support Team" name
    # until then (see support_chat/service.py::_agent_name).
    agent_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    agent = db.relationship(
        "User",
        foreign_keys=[agent_id],
        lazy="joined",
    )

    # Unread count *for the customer* - increments when support posts,
    # resets to 0 when the customer fetches the thread's messages.
    client_unread_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
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

    messages = db.relationship(
        "SupportMessage",
        back_populates="thread",
        order_by="SupportMessage.sent_at",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<SupportThread {self.id} {self.subject!r}>"


class SupportMessage(db.Model):
    __tablename__ = "support_messages"

    __table_args__ = (
        db.Index("ix_support_messages_thread_id", "thread_id"),
    )

    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    thread_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("support_threads.id", ondelete="CASCADE"),
        nullable=False,
    )

    thread = db.relationship(
        "SupportThread",
        back_populates="messages",
        foreign_keys=[thread_id],
    )

    author = db.Column(
        db.String(20),
        nullable=False,
    )

    # Display name captured at send time (e.g. "Naomi K., Client
    # Support" or the customer's own name) so historical messages
    # still read correctly if an agent's display name later changes.
    author_name = db.Column(
        db.String(255),
        nullable=False,
    )

    # Only populated for author == "support" - which agent sent it.
    author_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    body = db.Column(
        db.Text,
        nullable=False,
    )

    # [{"id": "...", "name": "...", "size": 0, "url": "..."}]
    attachments = db.Column(
        JSONB,
        nullable=False,
        default=list,
    )

    sent_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "chatId": str(self.thread_id),
            "author": self.author,
            "authorName": self.author_name,
            "body": self.body,
            "sentAt": self.sent_at.isoformat(),
        }

    def __repr__(self):
        return f"<SupportMessage thread_id={self.thread_id!r}>"
