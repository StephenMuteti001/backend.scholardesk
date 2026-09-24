# customer_orders/routes.py
"""
Customer-facing routes matching docs/API.md and
src/lib/portal-data.ts in the customer-portal frontend repo exactly:

    GET    /orders
    GET    /orders/{id}
    POST   /orders/quote-requests
    PATCH  /orders/{id}
    POST   /orders/{id}/quote/accept
    POST   /orders/{id}/quote/reject
    POST   /orders/{id}/quote/counter
    POST   /orders/{id}/payments
    POST   /orders/{id}/cancel
    POST   /orders/{id}/refund-requests
    GET    /orders/{id}/submissions
    POST   /orders/{id}/submissions/{submissionId}/revision-requests
    POST   /orders/{id}/submissions/{submissionId}/approve
    POST   /orders/{id}/submissions/{submissionId}/reject

All mounted under /api/v1 (API_BASE_URL in the frontend already
includes /api/v1, so these blueprints do NOT repeat "orders" as their
own prefix beyond that).
"""

from flask import Blueprint, request

from customer_orders.schemas import (
    validate_counter_quote,
    validate_list_orders,
    validate_pay_order,
    validate_quote_request,
    validate_reason_payload,
    validate_revision_request,
    validate_update_order,
)
from customer_orders.service import (
    accept_quote,
    approve_submission,
    cancel_order,
    counter_quote,
    create_quote_request,
    get_order,
    list_orders,
    list_submissions,
    pay_order,
    reject_quote,
    reject_submission,
    request_refund,
    request_revision,
    serialize_order,
    update_order,
)
from utils.authorization import get_current_user, require_roles
from utils.exceptions import ServiceError
from utils.response_formatter import error_response, success_response
from utils.roles import CUSTOMER_ROLES

customer_bp = Blueprint(
    "customer_orders",
    __name__,
    url_prefix="/api/v1/orders",
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


def _is_multipart():
    return bool(
        request.content_type and "multipart/form-data" in request.content_type
    )


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@customer_bp.get("")
@require_roles(*CUSTOMER_ROLES)
def list_orders_route():
    try:
        user = get_current_user()

        params = validate_list_orders(request.args)

        result = list_orders(user, **params)

        pagination = result["pagination"]

        return success_response(
            {
                "data": result["items"],
                "meta": {
                    "counts": result["counts"],
                    "current_page": pagination["page"],
                    "last_page": pagination["pages"],
                    "per_page": pagination["per_page"],
                    "total": pagination["total"],
                    "has_more": pagination["has_more"],
                },
            }
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# CREATE (quote request)
# ---------------------------------------------------------------------------

@customer_bp.post("/quote-requests")
@require_roles(*CUSTOMER_ROLES)
def create_quote_request_route():
    try:
        user = get_current_user()

        if _is_multipart():
            payload = request.form.to_dict()
            payload["fileNames"] = request.form.getlist("fileNames")
            uploaded_files = request.files.getlist("files")
        else:
            payload = request.get_json(silent=True) or {}
            uploaded_files = None

        fields = validate_quote_request(payload)

        order = create_quote_request(user, fields, uploaded_files)

        return success_response(
            {"data": serialize_order(order)},
            status=201,
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# GET / PATCH
# ---------------------------------------------------------------------------

@customer_bp.get("/<uuid:order_id>")
@require_roles(*CUSTOMER_ROLES)
def get_order_route(order_id):
    try:
        user = get_current_user()

        return success_response({"data": get_order(order_id, user)})

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@customer_bp.patch("/<uuid:order_id>")
@require_roles(*CUSTOMER_ROLES)
def update_order_route(order_id):
    try:
        user = get_current_user()

        payload = request.get_json(silent=True) or {}
        fields = validate_update_order(payload)

        order = update_order(order_id, user, fields)

        return success_response({"data": serialize_order(order)})

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# QUOTE ACCEPT
# ---------------------------------------------------------------------------

@customer_bp.post("/<uuid:order_id>/quote/accept")
@require_roles(*CUSTOMER_ROLES)
def accept_quote_route(order_id):
    try:
        user = get_current_user()

        order = accept_quote(order_id, user)

        return success_response({"data": serialize_order(order)})

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@customer_bp.post("/<uuid:order_id>/quote/reject")
@require_roles(*CUSTOMER_ROLES)
def reject_quote_route(order_id):
    try:
        user = get_current_user()

        order = reject_quote(order_id, user)

        return success_response({"data": serialize_order(order)})

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@customer_bp.post("/<uuid:order_id>/quote/counter")
@require_roles(*CUSTOMER_ROLES)
def counter_quote_route(order_id):
    try:
        user = get_current_user()

        payload = request.get_json(silent=True) or {}
        validated = validate_counter_quote(payload)

        order = counter_quote(
            order_id,
            user,
            validated["amount"],
            validated["notes"],
        )

        return success_response(
            {"data": serialize_order(order)},
            status=201,
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# PAYMENT
# ---------------------------------------------------------------------------

@customer_bp.post("/<uuid:order_id>/payments")
@require_roles(*CUSTOMER_ROLES)
def pay_order_route(order_id):
    try:
        user = get_current_user()

        payload = request.get_json(silent=True) or {}
        validated = validate_pay_order(payload)

        order = pay_order(
            order_id,
            user,
            validated["gateway"],
            validated["payment_reference"],
        )

        return success_response(
            {"data": serialize_order(order)},
            status=201,
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# CANCEL
# ---------------------------------------------------------------------------

@customer_bp.post("/<uuid:order_id>/cancel")
@require_roles(*CUSTOMER_ROLES)
def cancel_order_route(order_id):
    try:
        user = get_current_user()

        payload = request.get_json(silent=True) or {}
        validated = validate_reason_payload(payload)

        order = cancel_order(order_id, user, validated["reason"])

        return success_response({"data": serialize_order(order)})

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# REFUND REQUEST
# ---------------------------------------------------------------------------

@customer_bp.post("/<uuid:order_id>/refund-requests")
@require_roles(*CUSTOMER_ROLES)
def request_refund_route(order_id):
    try:
        user = get_current_user()

        payload = request.get_json(silent=True) or {}
        validated = validate_reason_payload(payload)

        order = request_refund(order_id, user, validated["reason"])

        return success_response(
            {"data": serialize_order(order)},
            status=201,
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# SUBMISSIONS
# ---------------------------------------------------------------------------

@customer_bp.get("/<uuid:order_id>/submissions")
@require_roles(*CUSTOMER_ROLES)
def list_submissions_route(order_id):
    try:
        user = get_current_user()

        return success_response(
            {"data": list_submissions(order_id, user)}
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@customer_bp.post(
    "/<uuid:order_id>/submissions/<uuid:submission_id>/revision-requests"
)
@require_roles(*CUSTOMER_ROLES)
def request_revision_route(order_id, submission_id):
    try:
        user = get_current_user()

        payload = request.get_json(silent=True) or {}
        validated = validate_revision_request(payload)

        order = request_revision(
            order_id, submission_id, user, validated["note"]
        )

        return success_response({"data": serialize_order(order)})

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@customer_bp.post(
    "/<uuid:order_id>/submissions/<uuid:submission_id>/approve"
)
@require_roles(*CUSTOMER_ROLES)
def approve_submission_route(order_id, submission_id):
    try:
        user = get_current_user()

        order = approve_submission(order_id, submission_id, user)

        return success_response({"data": serialize_order(order)})

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@customer_bp.post(
    "/<uuid:order_id>/submissions/<uuid:submission_id>/reject"
)
@require_roles(*CUSTOMER_ROLES)
def reject_submission_route(order_id, submission_id):
    try:
        user = get_current_user()

        payload = request.get_json(silent=True) or {}
        note = payload.get("note")

        if note is not None and not isinstance(note, str):
            return error_response(
                "VALIDATION_ERROR", "note must be a string.", status=400
            )

        order = reject_submission(
            order_id, submission_id, user, note
        )

        return success_response({"data": serialize_order(order)})

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)
