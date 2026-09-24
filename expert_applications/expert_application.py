# expert_applications/expert_application.py

import uuid

from sqlalchemy.dialects.postgresql import UUID

from extensions import db


class ExpertApplicationStatus:
    """
    Lifecycle of an expert application.

    SUBMITTED:
        Application has been submitted and awaits review.

    UNDER_REVIEW:
        Admin has started reviewing the application.

    APPROVED:
        Application passed review. The applicant may proceed
        through the activation/onboarding process.

    REJECTED:
        Application was rejected.

    WITHDRAWN:
        Applicant withdrew the application.
    """

    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"

    CHOICES = (
        SUBMITTED,
        UNDER_REVIEW,
        APPROVED,
        REJECTED,
        WITHDRAWN,
    )


class ExpertApplication(db.Model):
    __tablename__ = "expert_applications"

    # ---------------------------------------------------------
    # Identity
    # ---------------------------------------------------------

    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # A User can submit multiple applications over time.
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------

    user = db.relationship(
        "User",
        back_populates="expert_applications",
        foreign_keys="ExpertApplication.user_id",
        lazy="joined",
    )

    # ---------------------------------------------------------
    # Application contact/location
    # ---------------------------------------------------------
    #
    # country is technically available on User, but we retain
    # the application value because it represents what the
    # applicant submitted at the time of application.
    #
    # This is useful for historical/audit purposes.
    #

    country = db.Column(
        db.String(100),
        nullable=True,
    )

    city = db.Column(
        db.String(100),
        nullable=True,
    )

    phone_number = db.Column(
        db.String(40),
        nullable=True,
    )

    # ---------------------------------------------------------
    # Academic / professional information
    # ---------------------------------------------------------

    education = db.Column(
        db.String(255),
        nullable=True,
    )

    specialization = db.Column(
        db.String(255),
        nullable=True,
    )

    years_experience = db.Column(
        db.String(50),
        nullable=True,
    )

    # ---------------------------------------------------------
    # Proficiency assessment
    # ---------------------------------------------------------

    proficiency_answers = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    # ---------------------------------------------------------
    # Written assessment
    # ---------------------------------------------------------

    selected_prompt = db.Column(
        db.String(255),
        nullable=True,
    )

    prompt_response = db.Column(
        db.Text,
        nullable=True,
    )

    # The actual auth-portal application form (writer-onboarding/apply)
    # doesn't ask the applicant to pick one prompt - it has a small,
    # fixed set of writing prompts (see writer-data.ts::WRITING_PROMPTS)
    # and requires an essay response to each. selected_prompt/
    # prompt_response above are kept for any other caller that does
    # use a single-prompt flow; this is the one actually populated by
    # that form: {prompt_id: essay_text, ...}.
    writing_samples = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    selected_essay_topic = db.Column(
        db.String(255),
        nullable=True,
    )

    # The auth-portal form collects the essay as inline text (`essay`
    # field), not a file upload - essay_file_path below is kept for
    # any caller that does upload a file instead.
    essay_text = db.Column(
        db.Text,
        nullable=True,
    )

    essay_file_path = db.Column(
        db.String(1024),
        nullable=True,
    )

    # ---------------------------------------------------------
    # Supporting documents
    # ---------------------------------------------------------

    work_samples = db.Column(
        db.JSON,
        nullable=False,
        default=list,
    )

    degree_certificates = db.Column(
        db.JSON,
        nullable=False,
        default=list,
    )

    cv_file_path = db.Column(
        db.String(1024),
        nullable=True,
    )

    # ---------------------------------------------------------
    # Review state
    # ---------------------------------------------------------

    status = db.Column(
        db.String(40),
        nullable=False,
        default=ExpertApplicationStatus.SUBMITTED,
        index=True,
    )

    admin_feedback = db.Column(
        db.Text,
        nullable=True,
    )

    reviewed_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    reviewed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
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
    # Relationships
    # ---------------------------------------------------------
    reviewed_by_user = db.relationship(
        "User",
        foreign_keys=[reviewed_by],
    )

    # ---------------------------------------------------------
    # Convenience properties
    # ---------------------------------------------------------

    @property
    def applicant_name(self):
        return self.user.full_name if self.user else None

    @property
    def applicant_email(self):
        return self.user.email if self.user else None

    # ---------------------------------------------------------
    # Serialization
    # ---------------------------------------------------------

    def to_dict(self):
        return {
            "id": str(self.id),

            "user_id": self.user_id,

            "applicant": {
                "id": self.user.id if self.user else None,
                "name": self.applicant_name,
                "email": self.applicant_email,
            },

            "country": self.country,
            "city": self.city,
            "phone_number": self.phone_number,

            "education": self.education,
            "specialization": self.specialization,
            "years_experience": self.years_experience,

            "proficiency_answers": (
                self.proficiency_answers
                if self.proficiency_answers is not None
                else []
            ),

            "selected_prompt": self.selected_prompt,
            "prompt_response": self.prompt_response,
            "writing_samples": self.writing_samples or {},

            "selected_essay_topic": self.selected_essay_topic,
            "essay_text": self.essay_text,
            "essay_file_path": self.essay_file_path,

            "work_samples": self.work_samples or [],
            "degree_certificates": (
                self.degree_certificates or []
            ),

            "cv_file_path": self.cv_file_path,

            "status": self.status,
            "admin_feedback": self.admin_feedback,

            "reviewed_by": self.reviewed_by,
            "reviewed_at": (
                self.reviewed_at.isoformat()
                if self.reviewed_at
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
        return (
            f"<ExpertApplication "
            f"{self.id} user_id={self.user_id} "
            f"status={self.status}>"
        )