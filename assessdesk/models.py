# assessdesk/models.py

import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import JSONB, UUID

from extensions import db

from assessdesk.constants import GRANT_ACTIVE, PURCHASE_PENDING


def utcnow():
    """Timezone-aware UTC now. The only clock this module trusts."""
    return datetime.now(timezone.utc)


class AssessDeskAccount(db.Model):
    """
    AssessDesk entitlement for any platform user (customer, expert,
    admin). Not a role: one user row, one optional AssessDesk account.
    """

    __tablename__ = "assessdesk_accounts"

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    starter_granted = db.Column(db.Boolean, nullable=False, default=False)
    # Lowest low-balance threshold already notified; reset on new credit.
    last_low_balance_notified = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    user = db.relationship("User", lazy="select")


class AssessDeskPackage(db.Model):
    __tablename__ = "assessdesk_packages"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    questions = db.Column(db.Integer, nullable=False)
    validity_days = db.Column(db.Integer, nullable=False)
    # Minor units avoid float rounding (e.g. 150000 = KES 1,500.00).
    price_minor = db.Column(db.BigInteger, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="KES")
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        db.CheckConstraint("questions > 0", name="ck_ad_pkg_questions_pos"),
        db.CheckConstraint("validity_days > 0", name="ck_ad_pkg_validity_pos"),
        db.CheckConstraint("price_minor >= 0", name="ck_ad_pkg_price_nonneg"),
    )


class AssessDeskPurchase(db.Model):
    __tablename__ = "assessdesk_purchases"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    package_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("assessdesk_packages.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Snapshot of the package at checkout time: later package edits
    # never change what a customer paid for.
    questions = db.Column(db.Integer, nullable=False)
    validity_days = db.Column(db.Integer, nullable=False)
    amount_minor = db.Column(db.BigInteger, nullable=False)
    currency = db.Column(db.String(3), nullable=False)

    reference = db.Column(db.String(64), nullable=False, unique=True, index=True)
    status = db.Column(db.String(20), nullable=False, default=PURCHASE_PENDING, index=True)
    gateway = db.Column(db.String(20), nullable=False, default="paystack")
    gateway_response = db.Column(JSONB, nullable=True)
    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    user = db.relationship("User", lazy="select")
    package = db.relationship("AssessDeskPackage", lazy="select")


class AssessDeskGrant(db.Model):
    """A batch of questions with its own expiry. Consumed FIFO by expiry.

    Relationships are lazy="select" on purpose: rows are locked with
    SELECT ... FOR UPDATE, which Postgres rejects on outer-joined eager loads.
    List endpoints use selectinload() to avoid N+1.
    """

    __tablename__ = "assessdesk_grants"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source = db.Column(db.String(20), nullable=False)
    package_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("assessdesk_packages.id", ondelete="SET NULL"), nullable=True
    )
    purchase_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("assessdesk_purchases.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,  # one grant per paid purchase, ever
    )
    questions_granted = db.Column(db.Integer, nullable=False)
    questions_remaining = db.Column(db.Integer, nullable=False)
    granted_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=GRANT_ACTIVE)
    granted_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note = db.Column(db.String(255), nullable=True)

    # Notification bookkeeping (send-once markers).
    expiry_warned_hours = db.Column(db.Integer, nullable=True)  # smallest window warned
    grace_notified_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    user = db.relationship("User", foreign_keys=[user_id], lazy="select")
    package = db.relationship("AssessDeskPackage", lazy="select")

    __table_args__ = (
        db.Index("ix_ad_grants_user_status_expiry", "user_id", "status", "expires_at"),
        db.CheckConstraint("questions_remaining >= 0", name="ck_ad_grant_remaining_nonneg"),
        db.CheckConstraint(
            "questions_remaining <= questions_granted", name="ck_ad_grant_remaining_le_granted"
        ),
    )


class AssessDeskLedgerEntry(db.Model):
    """Immutable audit trail. Never updated or deleted."""

    __tablename__ = "assessdesk_ledger"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    grant_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("assessdesk_grants.id", ondelete="CASCADE"), nullable=True
    )
    delta = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(20), nullable=False)
    idempotency_key = db.Column(db.String(64), nullable=True)
    device_id = db.Column(UUID(as_uuid=True), nullable=True)
    meta = db.Column(JSONB, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)


class AssessDeskConsumeRequest(db.Model):
    """
    One row per consume idempotency key. The unique constraint is what
    makes a retried consume a no-op, even across concurrent requests.
    """

    __tablename__ = "assessdesk_consume_requests"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    idempotency_key = db.Column(db.String(64), primary_key=True)
    amount = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class AssessDeskDevice(db.Model):
    """
    A signed-in desktop installation. Holds the hash of its rotating
    refresh token; revoking the row signs that device out.
    """

    __tablename__ = "assessdesk_devices"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_device_id = db.Column(db.String(64), nullable=False)
    device_name = db.Column(db.String(120), nullable=True)
    client_version = db.Column(db.String(40), nullable=True)
    refresh_token_hash = db.Column(db.String(128), nullable=False, unique=True)
    refresh_expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        db.Index("ix_ad_devices_user_client", "user_id", "client_device_id"),
    )
