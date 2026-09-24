# expert_applications/routes.py

import os

from flask import Blueprint, current_app, request, send_file

from expert_applications.schemas import (
    validate_apply_payload,
    validate_file_counts,
    validate_list_applications,
    validate_proficiency_answers,
    validate_review_payload,
    validate_writing_samples,
)
from expert_applications.service import (
    activate_expert,
    approve_application,
    get_application,
    get_application_statistics,
    get_my_application,
    list_applications,
    mark_under_review,
    reject_application,
    withdraw_application,
)
from expert_applications import service as expert_application_service
from users.mailer_service import (
    send_application_approved_email,
    send_application_received_email,
    send_application_rejected_email,
    send_deposit_approved_email,
)
from utils.authorization import get_current_user, require_roles
from utils.exceptions import ServiceError, ValidationError
from utils.response_formatter import error_response, success_response
from utils.roles import ADMIN_ROLES, CUSTOMER_ROLES
from utils.uploads import resolve_upload_path


# ---------------------------------------------------------------------------
# Blueprints
#
# Two blueprints, sharing one service/schema layer, split by user type
# per the module convention documented in README-ish comments across
# this codebase: <role>_bp for each role that touches the resource,
# both living in the same routes.py for a module this size. See
# dashboard/routes.py and analytics/routes.py for the same pattern
# applied to a three-way (admin/customer/expert) split.
# ---------------------------------------------------------------------------

customer_bp = Blueprint(
    "expert_applications_customer",
    __name__,
    url_prefix="/api/v1/expert-applications",
)

admin_bp = Blueprint(
    "expert_applications_admin",
    __name__,
    url_prefix="/api/v1/admin/expert-applications",
)


def _handle_service_error(exc):
    if isinstance(exc, ServiceError):
        return error_response(
            exc.code,
            exc.message,
            exc.details,
            exc.status_code,
        )

    return error_response("SERVICE_ERROR", str(exc), status=400)


# ---------------------------------------------------------------------------
# CUSTOMER: apply to become an expert
# ---------------------------------------------------------------------------

@customer_bp.post("/apply")
@require_roles(*CUSTOMER_ROLES)
def apply_route():
    try:
        from platform_settings.service import get_settings

        settings = get_settings()

        if not settings.writer_hiring_open:
            return error_response(
                "HIRING_CLOSED",
                settings.hiring_notice
                or "We are not currently accepting new expert applications.",
                status=403,
            )

        user = get_current_user()

        fields = validate_apply_payload(request.form)
        proficiency_answers = validate_proficiency_answers(
            request.form.get("proficiency_answers")
            or request.form.get("proficiencyAnswers")
        )
        writing_samples = validate_writing_samples(request.form)
        validate_file_counts(request.files)

        application = expert_application_service.apply_for_expert(
            user,
            fields,
            proficiency_answers,
            writing_samples,
            request.files,
        )

        send_application_received_email(user)

        return success_response(
            {"application": application.to_dict()},
            message="Application submitted successfully.",
            status=201,
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# CUSTOMER: view my own (most recent) application
# ---------------------------------------------------------------------------

@customer_bp.get("/me")
@require_roles(*CUSTOMER_ROLES)
def my_application_route():
    try:
        user = get_current_user()

        application = get_my_application(user)

        return success_response(
            {
                "application": (
                    application.to_dict() if application else None
                )
            }
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# CUSTOMER: withdraw my own application
# ---------------------------------------------------------------------------

@customer_bp.post("/<uuid:application_id>/withdraw")
@require_roles(*CUSTOMER_ROLES)
def withdraw_application_route(application_id):
    try:
        user = get_current_user()

        application = withdraw_application(application_id, user)

        return success_response(
            {"application": application.to_dict()},
            message="Application withdrawn.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# ADMIN: list applications
# ---------------------------------------------------------------------------

@admin_bp.get("")
@require_roles(*ADMIN_ROLES)
def list_applications_route():
    try:
        params = validate_list_applications(request.args)

        result = list_applications(**params)

        return success_response(result)

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# ADMIN: statistics (also reused by the dashboard/analytics modules)
# ---------------------------------------------------------------------------

@admin_bp.get("/statistics")
@require_roles(*ADMIN_ROLES)
def application_statistics_route():
    try:
        return success_response(get_application_statistics())

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# ADMIN: application detail
# ---------------------------------------------------------------------------

@admin_bp.get("/<uuid:application_id>")
@require_roles(*ADMIN_ROLES)
def get_application_route(application_id):
    try:
        application = get_application(application_id)

        return success_response({"application": application.to_dict()})

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# ADMIN: move to "under review"
# ---------------------------------------------------------------------------

@admin_bp.post("/<uuid:application_id>/review")
@require_roles(*ADMIN_ROLES)
def mark_under_review_route(application_id):
    try:
        reviewer = get_current_user()

        application = mark_under_review(application_id, reviewer)

        return success_response(
            {"application": application.to_dict()},
            message="Application marked as under review.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# ADMIN: approve
# ---------------------------------------------------------------------------

@admin_bp.post("/<uuid:application_id>/approve")
@require_roles(*ADMIN_ROLES)
def approve_application_route(application_id):
    try:
        reviewer = get_current_user()

        payload = request.get_json(silent=True) or {}
        validated = validate_review_payload(payload)

        application = approve_application(
            application_id,
            reviewer,
            validated["feedback"],
        )

        send_application_approved_email(
            application.user,
            validated["feedback"],
        )

        return success_response(
            {"application": application.to_dict()},
            message="Application approved successfully.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# ADMIN: reject
# ---------------------------------------------------------------------------

@admin_bp.post("/<uuid:application_id>/reject")
@require_roles(*ADMIN_ROLES)
def reject_application_route(application_id):
    try:
        reviewer = get_current_user()

        payload = request.get_json(silent=True) or {}
        validated = validate_review_payload(
            payload,
            feedback_required=True,
        )

        application = reject_application(
            application_id,
            reviewer,
            validated["feedback"],
        )

        send_application_rejected_email(
            application.user,
            validated["feedback"],
        )

        return success_response(
            {"application": application.to_dict()},
            message="Application rejected.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# ADMIN: confirm initial deposit -> activate expert
# ---------------------------------------------------------------------------

@admin_bp.post("/<uuid:application_id>/confirm-deposit")
@require_roles(*ADMIN_ROLES)
def confirm_deposit_route(application_id):
    try:
        reviewer = get_current_user()

        application, expert = activate_expert(application_id, reviewer)

        send_deposit_approved_email(application.user)

        return success_response(
            {
                "application": application.to_dict(),
                "expert_id": str(expert.id),
            },
            message="Deposit confirmed. Expert account activated.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# ADMIN: serve an uploaded application file (essay / CV / samples / certs)
# ---------------------------------------------------------------------------

@admin_bp.get("/files/<path:relative_path>")
@require_roles(*ADMIN_ROLES)
def serve_application_file_route(relative_path):
    try:
        safe_path = resolve_upload_path(relative_path)

        if not os.path.exists(safe_path):
            return error_response("NOT_FOUND", "File not found.", status=404)

        return send_file(safe_path, as_attachment=False)

    except ValidationError as exc:
        return _handle_service_error(exc)
    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# Path alias: the auth-portal frontend (auth.scholardesk.pro) calls
# POST /applications/apply-writer for this same action - a naming
# mismatch from when this blueprint was built at /expert-applications.
# Rather than rename the blueprint (risking any other unnoticed
# caller of /expert-applications/apply), register the same view under
# the path the frontend actually uses.
#
# NOTE: this only fixes the URL. The auth frontend's application form
# (src/lib/writer-data.ts) sends a much richer, quiz-style payload
# (proficiency questions, writing prompts, essay topics) that hasn't
# been checked field-by-field against validate_apply_payload() /
# validate_proficiency_answers() here - that's a separate, larger
# reconciliation this pass did not cover.
# ---------------------------------------------------------------------------

applications_alias_bp = Blueprint(
    "applications_alias",
    __name__,
    url_prefix="/api/v1/applications",
)

applications_alias_bp.add_url_rule(
    "/apply-writer",
    view_func=apply_route,
    methods=["POST"],
)
