# v2/experts/expert.py

import uuid

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.hybrid import hybrid_property

from extensions import db


class ExpertStatus:
    """
    Lifecycle states for an activated expert profile.

    ONBOARDING:
        Expert account/profile is being prepared.

    ACTIVE:
        Expert is fully active and can participate in the
        expert workflow.

    PAUSED:
        Expert is temporarily unavailable but has not been
        removed from the platform.

    OFFBOARDED:
        Expert has permanently/indefinitely left the platform.
    """

    ACTIVE = "active"
    ONBOARDING = "onboarding"
    PAUSED = "paused"
    OFFBOARDED = "offboarded"

    CHOICES = (
        ACTIVE,
        ONBOARDING,
        PAUSED,
        OFFBOARDED,
    )


class Expert(db.Model):
    __tablename__ = "experts"

    # ---------------------------------------------------------
    # Primary identity
    # ---------------------------------------------------------

    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # One User can have at most one Expert profile.
    #
    # User remains the source of truth for:
    #   - first_name
    #   - last_name
    #   - email
    #   - country
    #   - authentication
    #   - account status
    #   - authorization
    #
    # Expert contains only expert-specific information.
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------

    user = db.relationship(
        "User",
        back_populates="expert",
        lazy="joined",
    )

    exam_materials = db.relationship(
        "ExamMaterial",
        back_populates="expert",
        lazy="select",
    )

    # Future relationships:
    #
    # assignments = db.relationship(...)
    # reviews = db.relationship(...)
    # payouts = db.relationship(...)
    # availability = db.relationship(...)
    # specializations = db.relationship(...)

    # ---------------------------------------------------------
    # Contact / profile
    # ---------------------------------------------------------

    phone = db.Column(
        db.String(40),
        nullable=True,
    )

    profile_image = db.Column(
        db.String(1024),
        nullable=True,
    )

    bio = db.Column(
        db.Text,
        nullable=True,
    )

    # ---------------------------------------------------------
    # Academic profile
    # ---------------------------------------------------------

    title = db.Column(
        db.String(100),
        nullable=True,
    )

    highest_qualification = db.Column(
        db.String(255),
        nullable=True,
    )

    years_of_experience = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    timezone = db.Column(
        db.String(100),
        nullable=True,
    )

    # JSON is deliberately retained for now.
    #
    # Example:
    # ["English", "French"]
    languages = db.Column(
        db.JSON,
        nullable=False,
        default=list,
    )

    # Example:
    # ["Computer Science", "Artificial Intelligence"]
    specialities = db.Column(
        db.JSON,
        nullable=False,
        default=list,
    )

    # Example:
    # ["AWS Certified Developer", "CCNA"]
    certifications = db.Column(
        db.JSON,
        nullable=False,
        default=list,
    )

    # ---------------------------------------------------------
    # Commercial profile
    # ---------------------------------------------------------

    hourly_rate = db.Column(
        db.Numeric(10, 2),
        nullable=True,
    )

    # ---------------------------------------------------------
    # Expert availability / lifecycle
    # ---------------------------------------------------------

    status = db.Column(
        db.String(30),
        nullable=False,
        default=ExpertStatus.ONBOARDING,
        index=True,
    )

    is_verified = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    is_available = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    # ---------------------------------------------------------
    # Performance / leaderboard statistics
    # ---------------------------------------------------------
    #
    # These fields preserve functionality from v1.
    #
    # They are expert-specific and therefore belong here rather
    # than on User.
    #
    # They may later be replaced or supplemented by an
    # expert_statistics / reviews / orders aggregation layer.
    #

    rating = db.Column(
        db.Numeric(3, 2),
        nullable=False,
        default=0.0,
    )

    completed_orders = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    total_earned = db.Column(
        db.Numeric(14, 2),
        nullable=False,
        default=0,
    )

    # ---------------------------------------------------------
    # Audit
    # ---------------------------------------------------------

    created_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        nullable=False,
        index=True,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False,
    )

    # ---------------------------------------------------------
    # Computed properties
    # ---------------------------------------------------------

    @hybrid_property
    def name(self):
        """
        Full name comes from the associated User.

        Expert deliberately does not duplicate first_name /
        last_name.
        """
        if not self.user:
            return ""

        return self.user.full_name

    @hybrid_property
    def email(self):
        """
        Convenience property so existing code can continue
        to access expert.email without duplicating email data.
        """
        return self.user.email if self.user else None

    @hybrid_property
    def first_name(self):
        return self.user.first_name if self.user else None

    @hybrid_property
    def last_name(self):
        return self.user.last_name if self.user else None

    @hybrid_property
    def country(self):
        """
        Country is a User-level identity/profile attribute.
        """
        return self.user.country if self.user else None

    @hybrid_property
    def active_jobs(self):
        """
        Number of active assignments.

        This should eventually be calculated from Orders /
        Assignments rather than stored redundantly.
        """
        return 0

    @hybrid_property
    def payout_due(self):
        """
        Outstanding expert payout.

        This should eventually be calculated from the
        payments/payouts subsystem.
        """
        return 0

    @hybrid_property
    def success_rate(self):
        """
        Current simple success-rate implementation.

        This preserves the semantics of the v1 leaderboard,
        where an expert with completed orders is considered
        successful.

        This should eventually be calculated from completed,
        cancelled and failed assignments.
        """
        return 100.0 if self.completed_orders > 0 else 0.0

    # ---------------------------------------------------------
    # Lifecycle helpers
    # ---------------------------------------------------------

    def activate(self):
        self.status = ExpertStatus.ACTIVE
        self.is_available = True

    def start_onboarding(self):
        self.status = ExpertStatus.ONBOARDING
        self.is_available = False

    def pause(self):
        self.status = ExpertStatus.PAUSED
        self.is_available = False

    def offboard(self):
        self.status = ExpertStatus.OFFBOARDED
        self.is_available = False

    def verify(self):
        self.is_verified = True

    # ---------------------------------------------------------
    # Serialization
    # ---------------------------------------------------------

    def to_dict(self):
        return {
            "id": str(self.id),

            # Identity comes from User.
            "user_id": self.user_id,
            "name": self.name,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "country": self.country,

            # Expert profile.
            "phone": self.phone,
            "profile_image": self.profile_image,
            "avatar": self.profile_image,
            "bio": self.bio,

            # Academic information.
            "title": self.title,
            "highest_qualification": self.highest_qualification,
            "years_of_experience": self.years_of_experience,
            "timezone": self.timezone,
            "languages": self.languages or [],
            "specialities": self.specialities or [],
            "certifications": self.certifications or [],

            # Commercial information.
            "hourly_rate": (
                float(self.hourly_rate)
                if self.hourly_rate is not None
                else None
            ),

            # Lifecycle.
            "status": self.status,
            "is_verified": self.is_verified,
            "is_available": self.is_available,

            # Performance.
            "rating": float(self.rating or 0),
            "active_jobs": self.active_jobs,
            "completed": self.completed_orders,
            "completed_orders": self.completed_orders,
            "total_earned": float(self.total_earned or 0),
            "payout_due": self.payout_due,
            "success_rate": self.success_rate,

            # Audit.
            "joined_at": (
                self.created_at.isoformat()
                if self.created_at
                else None
            ),
            "created_at": (
                self.created_at.isoformat()
                if self.created_at
                else None
            ),
            "updated_at": (
                self.updated_at.isoformat()
                if self.updated_at
                else None
            ),
        }

    def __repr__(self):
        return f"<Expert {self.id} user_id={self.user_id}>"