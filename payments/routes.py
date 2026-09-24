from flask import Blueprint, request
from utils.authorization import require_roles
from utils.roles import ADMIN_ROLES
from flask_jwt_extended import get_jwt_identity

from utils.exceptions import ServiceError

from utils.response_formatter import (
    success_response,
    error_response,
)

from payments.schemas import (
    validate_list_payments,
    validate_update_payment,
    validate_bulk_update_payments,
    validate_bulk_delete_payments,
)

from payments.service import (
    list_payments,
    get_payment,
    get_payment_statistics,
    update_payment,
    delete_payment,
    bulk_update_payments,
    bulk_delete_payments,
    get_balance_for_expert,
    list_transactions_for_expert,
)
from utils.authorization import get_current_user
from utils.roles import EXPERT_ROLES


payments_bp = Blueprint(
    "payments",
    __name__,
    url_prefix="/api/v1/admin/payouts",
)

# Self-service: the expert's own earnings. Mounted directly at
# /api/v1 (not nested under /admin/payouts) to match the expert
# portal frontend's actual calls (GET /balance, GET /transactions).
expert_bp = Blueprint(
    "payments_expert",
    __name__,
    url_prefix="/api/v1",
)


def _current_expert_profile():
    from experts.service import ExpertService

    user = get_current_user()
    expert = ExpertService.get_by_user_id(user.id)

    if not expert:
        return None

    return expert


@expert_bp.get("/balance")
@require_roles(*EXPERT_ROLES)
def get_my_balance():
    expert = _current_expert_profile()

    if not expert:
        return success_response(
            {"available": 0, "pending": 0, "total_earned": 0, "on_hold": 0}
        )

    return success_response(get_balance_for_expert(expert.id))


@expert_bp.get("/transactions")
@require_roles(*EXPERT_ROLES)
def list_my_transactions():
    expert = _current_expert_profile()

    if not expert:
        return success_response({"transactions": [], "data": {"transactions": []}})

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("limit", 50, type=int), 100)

    transactions = list_transactions_for_expert(expert.id, page, per_page)

    return success_response(
        {"transactions": transactions, "data": {"transactions": transactions}}
    )


def _get_current_user_id():
    return get_jwt_identity()


def _handle_service_error(exc):
    if isinstance(exc, ServiceError):
        status = 400

        if exc.code == "NOT_FOUND":
            status = 404

        elif exc.code == "CONFLICT":
            status = 409

        elif exc.code == "AUTHENTICATION_REQUIRED":
            status = 401

        return error_response(
            exc.code,
            exc.message,
            exc.details,
            status,
        )

    return error_response(
        "SERVICE_ERROR",
        str(exc),
        status=500,
    )


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@payments_bp.get("")
@require_roles(*ADMIN_ROLES)
def list_payments_route():
    try:
        params = validate_list_payments(
            request.args
        )

        result = list_payments(
            **params
        )

        return success_response(
            result
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# STATISTICS
# ---------------------------------------------------------------------------

@payments_bp.get("/statistics")
@require_roles(*ADMIN_ROLES)
def payment_statistics():
    try:
        statistics = (
            get_payment_statistics()
        )

        return success_response(
            statistics
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# GET ONE
# ---------------------------------------------------------------------------

@payments_bp.get(
    "/<uuid:payment_id>"
)
@require_roles(*ADMIN_ROLES)
def get_payment_route(payment_id):
    try:
        payment = get_payment(
            payment_id
        )

        return success_response(
            {
                "payment": payment
            }
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

@payments_bp.patch(
    "/<uuid:payment_id>"
)
@require_roles(*ADMIN_ROLES)
def update_payment_route(payment_id):
    try:
        payload = request.get_json(
            silent=True
        )

        if payload is None:
            return error_response(
                "INVALID_JSON",
                "Request body must contain valid JSON.",
                status=400,
            )

        payload = validate_update_payment(
            payload
        )

        actor_id = _get_current_user_id()

        if not actor_id:
            return error_response(
                "AUTHENTICATION_REQUIRED",
                "An authenticated user is required.",
                status=401,
            )

        payment = update_payment(
            payment_id,
            payload,
            str(actor_id),
        )

        return success_response(
            {
                "payment": payment
            },
            message="Payment updated successfully.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@payments_bp.delete(
    "/<uuid:payment_id>"
)
@require_roles(*ADMIN_ROLES)
def delete_payment_route(payment_id):
    try:
        delete_payment(
            payment_id
        )

        return success_response(
            message="Payment deleted successfully."
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# BULK UPDATE
# ---------------------------------------------------------------------------

@payments_bp.patch("/bulk")
@require_roles(*ADMIN_ROLES)
def bulk_update_payment_route():
    try:
        payload = request.get_json(
            silent=True
        )

        if payload is None:
            return error_response(
                "INVALID_JSON",
                "Request body must contain valid JSON.",
                status=400,
            )

        validated = (
            validate_bulk_update_payments(
                payload
            )
        )

        actor_id = _get_current_user_id()

        if not actor_id:
            return error_response(
                "AUTHENTICATION_REQUIRED",
                "An authenticated user is required.",
                status=401,
            )

        payments = bulk_update_payments(
            validated["ids"],
            validated["update"],
            str(actor_id),
        )

        return success_response(
            {
                "items": payments,
                "count": len(payments),
            },
            message="Payments updated successfully.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# BULK DELETE
# ---------------------------------------------------------------------------

@payments_bp.delete("/bulk")
@require_roles(*ADMIN_ROLES)
def bulk_delete_payment_route():
    try:
        payload = request.get_json(
            silent=True
        )

        if payload is None:
            return error_response(
                "INVALID_JSON",
                "Request body must contain valid JSON.",
                status=400,
            )

        ids = validate_bulk_delete_payments(
            payload
        )

        count = bulk_delete_payments(
            ids
        )

        return success_response(
            {
                "count": count
            },
            message=(
                f"{count} payment(s) "
                "deleted successfully."
            ),
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)