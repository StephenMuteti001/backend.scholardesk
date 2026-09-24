# expert_applications/service.py

from datetime import datetime, timezone

from sqlalchemy import or_

from expert_applications.constants import (
    DECIDED_STATUSES,
    UPLOAD_SUBDIR_CV,
    UPLOAD_SUBDIR_DEGREE_CERTIFICATES,
    UPLOAD_SUBDIR_ESSAY,
    UPLOAD_SUBDIR_WORK_SAMPLES,
)
from expert_applications.expert_application import (
    ExpertApplication,
    ExpertApplicationStatus,
)
from experts.service import ExpertService
from extensions import db
from utils.exceptions import ConflictError, NotFoundError, ValidationError
from utils.pagination import paginate_query
from utils.roles import ROLE_EXPERT
from utils.transaction import transaction
from utils.uploads import save_uploaded_file, save_uploaded_files


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_application_or_raise(application_id):
    application = db.session.get(ExpertApplication, application_id)

    if not application:
        raise NotFoundError(
            "Expert application not found.",
            {"application_id": str(application_id)},
        )

    return application


def _has_open_application(user_id):
    return (
        ExpertApplication.query
        .filter(ExpertApplication.user_id == user_id)
        .filter(
            ExpertApplication.status.notin_(
                [
                    ExpertApplicationStatus.REJECTED,
                    ExpertApplicationStatus.WITHDRAWN,
                ]
            )
        )
        .first()
    )


# ---------------------------------------------------------------------------
# APPLY (customer)
# ---------------------------------------------------------------------------

def apply_for_expert(user, fields, proficiency_answers, writing_samples, files):
    """
    Submit (or re-submit, after a prior rejection/withdrawal) an
    application to become an expert.

    `fields` is the dict returned by
    expert_applications.schemas.validate_apply_payload().
    `writing_samples` is the dict returned by
    expert_applications.schemas.validate_writing_samples().
    `files` is the request.files MultiDict - the auth-portal form
    (writer-onboarding/apply) doesn't attach any files at all today,
    so all of these are commonly empty; kept for any other caller
    (e.g. a future "attach your CV" step) that does upload some.
    """

    if getattr(user, "is_expert", False):
        raise ConflictError(
            "This account is already an expert."
        )

    existing = _has_open_application(user.id)

    if existing:
        raise ConflictError(
            "You already have an application in progress.",
            {"application_id": str(existing.id)},
        )

    essay_path = save_uploaded_file(
        files.get("essay_file") or files.get("essayFile"),
        UPLOAD_SUBDIR_ESSAY.format(user_id=user.id),
    )

    cv_path = save_uploaded_file(
        files.get("cv_file") or files.get("cvFile"),
        UPLOAD_SUBDIR_CV.format(user_id=user.id),
    )

    work_sample_files = files.getlist("work_samples") or files.getlist(
        "workSamples"
    )
    degree_certificate_files = files.getlist(
        "degree_certificates"
    ) or files.getlist("degreeCertificates")

    work_sample_paths = save_uploaded_files(
        work_sample_files,
        UPLOAD_SUBDIR_WORK_SAMPLES.format(user_id=user.id),
    )

    degree_certificate_paths = save_uploaded_files(
        degree_certificate_files,
        UPLOAD_SUBDIR_DEGREE_CERTIFICATES.format(user_id=user.id),
    )

    with transaction():
        application = ExpertApplication(
            user_id=user.id,
            country=fields.get("country") or user.country,
            city=fields.get("city"),
            phone_number=fields.get("phone_number") or user.phone_number,
            education=fields.get("education"),
            specialization=fields.get("specialization"),
            years_experience=fields.get("years_experience"),
            proficiency_answers=proficiency_answers or {},
            selected_prompt=fields.get("selected_prompt"),
            prompt_response=fields.get("prompt_response"),
            writing_samples=writing_samples or {},
            selected_essay_topic=fields.get("selected_essay_topic"),
            essay_text=fields.get("essay_text"),
            essay_file_path=essay_path,
            work_samples=work_sample_paths,
            degree_certificates=degree_certificate_paths,
            cv_file_path=cv_path,
            status=ExpertApplicationStatus.SUBMITTED,
        )

        db.session.add(application)

        user.application_status = "applied"

        db.session.flush()

        return application


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------

def get_application(application_id):
    return _get_application_or_raise(application_id)


def get_my_application(user):
    """
    Most recent application belonging to the requesting user, or None.
    """
    return (
        ExpertApplication.query
        .filter(ExpertApplication.user_id == user.id)
        .order_by(ExpertApplication.created_at.desc())
        .first()
    )


def list_applications(
    page=1,
    per_page=20,
    status=None,
    search=None,
    sort_by="created_at",
    direction="desc",
):
    query = ExpertApplication.query

    if status:
        query = query.filter(ExpertApplication.status == status)

    if search:
        term = f"%{search}%"

        from users.user import User

        query = query.join(ExpertApplication.user).filter(
            or_(
                ExpertApplication.country.ilike(term),
                ExpertApplication.specialization.ilike(term),
                User.first_name.ilike(term),
                User.last_name.ilike(term),
                User.email.ilike(term),
            )
        )

    sort_column = (
        getattr(ExpertApplication, sort_by, None)
        if sort_by in ExpertApplication.__table__.columns
        else None
    ) or ExpertApplication.created_at

    query = query.order_by(
        sort_column.asc() if direction == "asc" else sort_column.desc()
    )

    items, pagination = paginate_query(query, page, per_page)

    return {
        "items": [application.to_dict() for application in items],
        "pagination": pagination,
    }


def get_application_statistics():
    total = ExpertApplication.query.count()

    submitted = ExpertApplication.query.filter(
        ExpertApplication.status == ExpertApplicationStatus.SUBMITTED
    ).count()

    under_review = ExpertApplication.query.filter(
        ExpertApplication.status == ExpertApplicationStatus.UNDER_REVIEW
    ).count()

    approved = ExpertApplication.query.filter(
        ExpertApplication.status == ExpertApplicationStatus.APPROVED
    ).count()

    rejected = ExpertApplication.query.filter(
        ExpertApplication.status == ExpertApplicationStatus.REJECTED
    ).count()

    withdrawn = ExpertApplication.query.filter(
        ExpertApplication.status == ExpertApplicationStatus.WITHDRAWN
    ).count()

    return {
        "total": total,
        "submitted": submitted,
        "under_review": under_review,
        "approved": approved,
        "rejected": rejected,
        "withdrawn": withdrawn,
        "awaiting_review": submitted + under_review,
    }


# ---------------------------------------------------------------------------
# WITHDRAW (customer - own application)
# ---------------------------------------------------------------------------

def withdraw_application(application_id, user):
    application = _get_application_or_raise(application_id)

    if application.user_id != user.id:
        raise NotFoundError(
            "Expert application not found.",
            {"application_id": str(application_id)},
        )

    if application.status in DECIDED_STATUSES:
        raise ConflictError(
            "This application has already been processed."
        )

    with transaction():
        application.status = ExpertApplicationStatus.WITHDRAWN
        application.updated_at = datetime.now(timezone.utc)

        db.session.flush()

        return application


# ---------------------------------------------------------------------------
# REVIEW (admin)
# ---------------------------------------------------------------------------

def mark_under_review(application_id, reviewer):
    application = _get_application_or_raise(application_id)

    if application.status != ExpertApplicationStatus.SUBMITTED:
        raise ConflictError(
            "Only submitted applications can be moved to review."
        )

    with transaction():
        application.status = ExpertApplicationStatus.UNDER_REVIEW
        application.reviewed_by = reviewer.id
        application.updated_at = datetime.now(timezone.utc)

        db.session.flush()

        return application


def approve_application(application_id, reviewer, feedback=None):
    application = _get_application_or_raise(application_id)

    if application.status in DECIDED_STATUSES:
        raise ConflictError(
            "This application has already been processed."
        )

    with transaction():
        application.status = ExpertApplicationStatus.APPROVED
        application.admin_feedback = feedback
        application.reviewed_by = reviewer.id
        application.reviewed_at = datetime.now(timezone.utc)
        application.updated_at = datetime.now(timezone.utc)

        user = application.user
        user.application_status = "awaiting_initial_deposit"

        db.session.flush()

        return application


def reject_application(application_id, reviewer, feedback):
    if not feedback:
        raise ValidationError(
            "Feedback is required when rejecting an application.",
            {"field": "feedback"},
        )

    application = _get_application_or_raise(application_id)

    if application.status in DECIDED_STATUSES:
        raise ConflictError(
            "This application has already been processed."
        )

    with transaction():
        application.status = ExpertApplicationStatus.REJECTED
        application.admin_feedback = feedback
        application.reviewed_by = reviewer.id
        application.reviewed_at = datetime.now(timezone.utc)
        application.updated_at = datetime.now(timezone.utc)

        user = application.user
        user.application_status = "rejected"

        db.session.flush()

        return application


# ---------------------------------------------------------------------------
# ACTIVATION (admin) - confirm deposit -> promote to a fully fledged expert
# ---------------------------------------------------------------------------

def activate_expert(application_id, reviewer):
    """
    Confirm the applicant's initial deposit, flip their account role
    to "expert", and provision an Expert profile (experts/expert.py)
    seeded from the approved application - reusing ExpertService
    rather than re-implementing profile creation here.
    """

    application = _get_application_or_raise(application_id)

    if application.status != ExpertApplicationStatus.APPROVED:
        raise ConflictError(
            "The application must be approved before the deposit "
            "can be confirmed."
        )

    user = application.user

    if user.expert is not None:
        raise ConflictError(
            "An expert profile already exists for this user."
        )

    with transaction():
        user.role = ROLE_EXPERT
        user.application_status = "paid_initial_deposit"
        user.account_status = "paid_initial_deposit"

        expert = ExpertService.create_expert(
            {
                "user_id": user.id,
                "phone": application.phone_number,
                "highest_qualification": application.education,
                "specialities": (
                    [application.specialization]
                    if application.specialization
                    else []
                ),
                "years_of_experience": _years_experience_as_int(
                    application.years_experience
                ),
            }
        )

        db.session.flush()

        return application, expert


def _years_experience_as_int(value):
    if not value:
        return 0

    try:
        return int(str(value).split("-")[0].strip())
    except (TypeError, ValueError):
        return 0
