# submissions/routes.py

import os

from flask import Blueprint, current_app, request, send_file

from submissions.schemas import validate_create_submission
from submissions.service import (
    create_submission,
    list_submissions_for_admin,
    release_submission,
)
from utils.authorization import get_current_user, require_roles
from utils.exceptions import ServiceError, ValidationError
from utils.response_formatter import error_response, success_response
from utils.roles import ADMIN_ROLES, CUSTOMER_ROLES, EXPERT_ROLES
from utils.uploads import resolve_upload_path

# Shares the /api/v1/orders prefix with customer_orders.customer_bp -
# that blueprint only registers GET on this path (customer listing
# submissions for their own order), this one only registers POST (an
# expert delivering work), so there's no route collision.
expert_bp = Blueprint(
    "submissions_expert",
    __name__,
    url_prefix="/api/v1/orders",
)

# Shares the /api/v1/admin/orders prefix with orders.routes.orders_bp
# for the same reason.
admin_bp = Blueprint(
    "submissions_admin",
    __name__,
    url_prefix="/api/v1/admin/orders",
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


@expert_bp.post("/<uuid:order_id>/submissions")
@require_roles(*EXPERT_ROLES, *ADMIN_ROLES)
def create_submission_route(order_id):
    try:
        actor = get_current_user()

        validated = validate_create_submission(
            request.form,
            request.files.getlist("files[]") or request.files.getlist("files"),
        )

        submission = create_submission(
            order_id,
            actor,
            validated["note"],
            validated["files"],
        )

        return success_response(
            {"data": submission.to_dict()},
            message="Work submitted for review.",
            status=201,
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@admin_bp.get("/<uuid:order_id>/submissions")
@require_roles(*ADMIN_ROLES)
def list_submissions_route(order_id):
    try:
        submissions = list_submissions_for_admin(order_id)

        return success_response({"data": submissions})

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@admin_bp.post("/<uuid:order_id>/submissions/<uuid:submission_id>/release")
@require_roles(*ADMIN_ROLES)
def release_submission_route(order_id, submission_id):
    try:
        actor = get_current_user()

        # multipart/form-data so support can optionally attach files
        # (and a note) at release time; both are optional, so this
        # still works for a plain release with nothing attached.
        note = request.form.get("note") if request.form else None
        files = (
            request.files.getlist("files[]") or request.files.getlist("files")
            if request.files
            else []
        )

        submission = release_submission(
            order_id, submission_id, actor, note, files
        )

        return success_response(
            {"data": submission.to_dict()},
            message="Submission released to the customer.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# Serve a submission file (an expert's deliverable, or a file support
# attached at release time). Both admin and customer need read access,
# scoped appropriately - see the two routes below.
# ---------------------------------------------------------------------------

def _safe_send(relative_path):
    try:
        safe_path = resolve_upload_path(relative_path)
    except ValidationError as exc:
        return error_response("VALIDATION_ERROR", str(exc), status=400)

    if not os.path.exists(safe_path):
        return error_response("NOT_FOUND", "File not found.", status=404)

    return send_file(safe_path, as_attachment=False)


@admin_bp.get("/<uuid:order_id>/submissions/files/<path:relative_path>")
@require_roles(*ADMIN_ROLES)
def serve_submission_file_admin(order_id, relative_path):
    return _safe_send(relative_path)


@expert_bp.get("/<uuid:order_id>/submissions/files/<path:relative_path>")
@require_roles(*CUSTOMER_ROLES, *EXPERT_ROLES)
def serve_submission_file_customer(order_id, relative_path):
    """
    Shares the customer_orders /api/v1/orders prefix (see expert_bp
    above) - both a customer viewing their own delivered work and the
    assigned expert viewing their own submission's files land here.
    """
    if not relative_path.startswith(f"submissions/{order_id}/"):
        return error_response("NOT_FOUND", "File not found.", status=404)

    from orders.order import Order

    user = get_current_user()
    order = Order.query.get(order_id)

    if not order:
        return error_response("NOT_FOUND", "File not found.", status=404)

    is_owner = order.customer_id == user.id
    is_assigned_expert = bool(
        order.request and order.request.assigned_to == user.id
    )

    if not is_owner and not is_assigned_expert:
        return error_response("NOT_FOUND", "File not found.", status=404)

    if is_owner and not is_assigned_expert:
        # A customer (not also the assigned expert) must never reach a
        # file belonging to a submission still awaiting integrity
        # review - see SubmissionStatus.PENDING_REVIEW.
        from submissions.submission import Submission, SubmissionStatus

        owns_a_visible_submission = any(
            any(f.get("url") == relative_path for f in (s.files or []))
            for s in Submission.query.filter(
                Submission.order_id == order.id,
                Submission.status != SubmissionStatus.PENDING_REVIEW,
            ).all()
        )

        if not owns_a_visible_submission:
            return error_response("NOT_FOUND", "File not found.", status=404)

    return _safe_send(relative_path)
