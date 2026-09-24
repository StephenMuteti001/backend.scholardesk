# users/user.py

from datetime import datetime

from sqlalchemy.ext.hybrid import hybrid_property

from extensions import db

from users.constants import (
    DEFAULT_ACCOUNT_STATUS,
    DEFAULT_EMAIL_VERIFICATION_STATUS,
    DEFAULT_USER_STATUS,
)


class User(db.Model):
    __tablename__ = "users"

    # =========================================================
    # Identity
    # =========================================================

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    first_name = db.Column(
        db.String(100),
        nullable=False,
    )

    last_name = db.Column(
        db.String(100),
        nullable=False,
    )

    email = db.Column(
        db.String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False,
    )

    country = db.Column(
        db.String(100),
        nullable=True,
    )

    phone_number = db.Column(
        db.String(50),
        nullable=True,
    )

    profile_image = db.Column(
        db.String(1024),
        nullable=True,
    )

    # =========================================================
    # Writer / Expert Profile
    # =========================================================

    bio = db.Column(
        db.Text,
        nullable=True,
    )

    rating = db.Column(
        db.Float,
        nullable=False,
        default=0.0,
    )

    completed_orders = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    total_earned = db.Column(
        db.Float,
        nullable=False,
        default=0.0,
    )

    # =========================================================
    # Authorization
    # =========================================================

    role = db.Column(
        db.String(30),
        nullable=False,
        default="customer",
        index=True,
    )

    # Supported roles:
    #
    #   client
    #   expert
    #   admin
    #   super_admin
    #
    # "expert" is the canonical replacement for the old
    # v1 "writer" role.

    # =========================================================
    # Account State
    # =========================================================

    status = db.Column(
        db.String(30),
        nullable=False,
        default=DEFAULT_USER_STATUS,
        index=True,
    )

    account_status = db.Column(
        db.String(50),
        nullable=False,
        default=DEFAULT_ACCOUNT_STATUS,
    )

    application_status = db.Column(
        db.String(50),
        nullable=False,
        default="not_applied",
        index=True,
    )

    # =========================================================
    # Email Verification
    # =========================================================

    email_verification_status = db.Column(
        db.String(30),
        nullable=False,
        default=DEFAULT_EMAIL_VERIFICATION_STATUS,
        index=True,
    )

    email_verification_sent_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    # =========================================================
    # Activity / Authentication
    # =========================================================

    last_active_at = db.Column(
        db.DateTime,
        nullable=True,
        index=True,
    )

    last_login_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    # =========================================================
    # Login OTP
    # =========================================================

    login_otp_hash = db.Column(
        db.String(255),
        nullable=True,
    )

    login_otp_expires_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    login_otp_attempts = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    # =========================================================
    # Suspension
    # =========================================================

    suspension_type = db.Column(
        db.String(30),
        nullable=True,
    )

    suspension_reason = db.Column(
        db.Text,
        nullable=True,
    )

    suspended_until = db.Column(
        db.DateTime,
        nullable=True,
    )

    # =========================================================
    # Audit / Lifecycle
    # =========================================================

    joined_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
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

    # =========================================================
    # Relationships
    # =========================================================

    # One user can have at most one writer/expert application.
    #
    # WriterApplication defines the actual application-specific
    # fields such as:
    #
    #   city
    #   education
    #   specialization
    #   years_experience
    #   proficiency_answers
    #   work_samples
    #   degree_certificates
    #   CV
    #   essay
    #
    # The relationship is intentionally defined here only if the
    # WriterApplication model imports this model indirectly and
    # therefore does not create a circular import problem.
    #
    # writer_application = db.relationship(
    #     "WriterApplication",
    #     back_populates="user",
    #     uselist=False,
    # )



    expert = db.relationship(
        "Expert",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    expert_applications = db.relationship(
        "ExpertApplication",
        back_populates="user",
        foreign_keys="ExpertApplication.user_id",
        lazy="select",
        order_by="ExpertApplication.created_at.desc()",
    )

    # =========================================================
    # Computed Properties
    # =========================================================

    @hybrid_property
    def full_name(self):
        """
        Return the user's display name.

        first_name/last_name remain the canonical stored identity
        fields (needed for search/sort granularity), but every
        caller across the codebase - and every frontend - reads
        the combined name as `full_name`, so this is the single
        canonical accessor for it.

        Defined as a hybrid_property so it also works inside
        SQLAlchemy query expressions (User.full_name), not just on
        already-loaded instances - see customers/service.py.
        """
        return f"{self.first_name} {self.last_name}".strip()

    @full_name.expression
    def full_name(cls):
        return db.func.trim(
            db.func.concat(cls.first_name, " ", cls.last_name)
        )

    @property
    def name(self):
        """
        Backward-compatible alias for full_name.
        """
        return self.full_name

    @property
    def is_active(self):
        """
        Whether the account is currently active.

        Note:
        A suspended user should never be considered active even
        if some other account state is valid.
        """
        return self.status == "active"

    @property
    def is_admin(self):
        """
        True for both admin and super_admin accounts.
        """
        return self.role in {"admin", "super_admin"}

    @property
    def is_super_admin(self):
        """
        True only for super administrators.
        """
        return self.role == "super_admin"

    @property
    def is_expert(self):
        """
        Canonical expert/writer check.

        v1 used the role name "writer". v2 standardizes this
        domain role as "expert".
        """
        return self.role == "expert"

    @property
    def is_customer(self):
        """
        Canonical customer/client check.

        v1 used the role name "client". v2 standardizes this
        domain role as "customer" - same migration already done
        for expert/writer above.
        """
        return self.role == "customer"

    @property
    def is_client(self):
        """
        Backward-compatible alias for is_customer.
        """
        return self.is_customer

    @property
    def is_email_verified(self):
        """
        Whether the user's email address has been verified.
        """
        return self.email_verification_status == "verified"

    @property
    def is_suspended(self):
        """
        Whether the account is currently marked suspended.
        """
        return self.status == "suspended"

    # =========================================================
    # Account State Helpers
    # =========================================================

    def mark_active(self):
        """
        Activate the account and clear suspension state.
        """
        self.status = "active"
        self.suspension_type = None
        self.suspension_reason = None
        self.suspended_until = None

    def mark_suspended(
        self,
        suspension_type,
        reason=None,
        suspended_until=None,
    ):
        """
        Suspend the account.

        suspension_type may be:
            - temporary
            - permanent

        suspended_until should normally be supplied for a
        temporary suspension.
        """
        self.status = "suspended"
        self.suspension_type = suspension_type
        self.suspension_reason = reason
        self.suspended_until = suspended_until

    def clear_suspension(self):
        """
        Remove suspension information and reactivate the account.
        """
        self.status = "active"
        self.suspension_type = None
        self.suspension_reason = None
        self.suspended_until = None

    # =========================================================
    # Email Verification Helpers
    # =========================================================

    def mark_email_verified(self):
        """
        Mark the user's email address as verified.
        """
        self.email_verification_status = "verified"

    # =========================================================
    # Authentication / Login Helpers
    # =========================================================

    def record_login(self):
        """
        Record a successful login and clear any outstanding
        login OTP state.
        """
        now = datetime.utcnow()

        self.last_login_at = now
        self.last_active_at = now

        self.login_otp_hash = None
        self.login_otp_expires_at = None
        self.login_otp_attempts = 0

    def record_activity(self):
        """
        Update the user's last activity timestamp.
        """
        self.last_active_at = datetime.utcnow()

    # =========================================================
    # OTP Helpers
    # =========================================================

    def set_login_otp(self, otp_hash, expires_at):
        """
        Store a hashed login OTP and its expiry time.
        """
        self.login_otp_hash = otp_hash
        self.login_otp_expires_at = expires_at
        self.login_otp_attempts = 0

    def clear_login_otp(self):
        """
        Remove all login OTP state.
        """
        self.login_otp_hash = None
        self.login_otp_expires_at = None
        self.login_otp_attempts = 0

    def increment_login_otp_attempts(self):
        """
        Increment failed OTP verification attempts.
        """
        self.login_otp_attempts += 1

    # =========================================================
    # Writer / Expert Statistics
    # =========================================================

    def increment_completed_orders(self):
        """
        Increment the number of successfully completed orders.
        """
        self.completed_orders += 1

    def add_earnings(self, amount):
        """
        Add an amount to the user's lifetime earnings.

        This should be called only for amounts that actually
        qualify as writer/expert earnings.
        """
        if amount is None:
            return

        self.total_earned += float(amount)

    def set_full_name(self, full_name):
        """
        Split a single "full name" string (as sent by every
        frontend's registration/edit forms) into first_name /
        last_name for storage.
        """
        full_name = (full_name or "").strip()

        if not full_name:
            return

        parts = full_name.split(" ", 1)

        self.first_name = parts[0]
        self.last_name = parts[1] if len(parts) > 1 else ""

    def update_rating(self, rating):
        """
        Set the user's current aggregate rating.

        Rating calculation itself should live in the relevant
        service, rather than inside the model.
        """
        if rating is None:
            return

        self.rating = float(rating)

    # =========================================================
    # Serialization
    # =========================================================

    def to_dict(self):
        """
        General-purpose user representation.

        Sensitive authentication fields such as password_hash,
        login OTP data, and suspension internals are intentionally
        excluded.
        """
        return {
            "id": self.id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "name": self.full_name,
            "full_name": self.full_name,
            "email": self.email,
            "phone_number": self.phone_number,
            "country": self.country,
            "profile_image": self.profile_image,

            "role": self.role,
            "status": self.status,
            "account_status": self.account_status,
            "application_status": self.application_status,

            "email_verification_status": (
                self.email_verification_status
            ),
            "is_email_verified": self.is_email_verified,

            "bio": self.bio,
            "rating": float(self.rating or 0),
            "completed_orders": self.completed_orders or 0,
            "total_earned": float(self.total_earned or 0),

            "joined_at": (
                self.joined_at.isoformat() + "Z"
                if self.joined_at
                else None
            ),

            "created_at": (
                self.created_at.isoformat() + "Z"
                if self.created_at
                else None
            ),

            "updated_at": (
                self.updated_at.isoformat() + "Z"
                if self.updated_at
                else None
            ),

            "last_login_at": (
                self.last_login_at.isoformat() + "Z"
                if self.last_login_at
                else None
            ),

            "last_active_at": (
                self.last_active_at.isoformat() + "Z"
                if self.last_active_at
                else None
            ),
        }

    # =========================================================
    # Representation
    # =========================================================

    def __repr__(self):
        return f"<User {self.id} {self.email}>"