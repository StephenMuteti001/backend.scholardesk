# requests/routes.py

from flask import Blueprint, request, Response
from utils.authorization import get_current_user, require_roles
from utils.roles import ADMIN_ROLES

from requests.schemas import (
    validate_bulk_delete_requests,
    validate_bulk_update_requests,
    validate_create_request,
    validate_issue_quote,
    validate_list_requests,
    validate_update_request,
)

from requests.service import (
    bulk_delete_requests,
    bulk_update_requests,
    create_request,
    delete_request,
    export_requests,
    get_request,
    get_request_statistics,
    issue_quote,
    list_requests,
    send_request_reminder,
    serialize_request,
    update_request,
)

from utils.exceptions import ServiceError
from utils.response_formatter import (
    error_response,
    success_response,
)


requests_bp = Blueprint(
    "requests",
    __name__,
    url_prefix="/api/v1/admin/requests",
)


def _handle_service_error(exc):
    if isinstance(exc, ServiceError):
        status = 400

        if exc.code == "NOT_FOUND":
            status = 404

        elif exc.code == "CONFLICT":
            status = 409

        return error_response(
            exc.code,
            exc.message,
            exc.details,
            status,
        )

    return error_response(
        "SERVICE_ERROR",
        str(exc),
        status=400,
    )


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@requests_bp.get("")
@require_roles(*ADMIN_ROLES)
def list_requests_route():
    try:
        params = validate_list_requests(
            request.args
        )

        result = list_requests(**params)

        return success_response(result)

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# STATISTICS
# ---------------------------------------------------------------------------

@requests_bp.get("/statistics")
@require_roles(*ADMIN_ROLES)
def request_statistics_route():
    try:
        raw_types = request.args.get("types")

        types = None

        if raw_types:
            types = [
                item.strip()
                for item in raw_types.split(",")
                if item.strip()
            ]

        statistics = get_request_statistics(
            types=types
        )

        return success_response(statistics)

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# EXPORT
# ---------------------------------------------------------------------------

@requests_bp.get("/export")
@require_roles(*ADMIN_ROLES)
def export_requests_route():
    try:
        params = validate_list_requests(
            request.args
        )

        csv_content = export_requests(**params)

        return Response(
            csv_content,
            mimetype="text/csv",
            headers={
                "Content-Disposition": (
                    "attachment; filename=requests.csv"
                )
            },
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

@requests_bp.post("")
@require_roles(*ADMIN_ROLES)
def create_request_route():
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

        payload = validate_create_request(
            payload
        )

        result = create_request(
            payload
        )

        return success_response(
            {
                "request": result
            },
            message="Request created successfully.",
            status=201,
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# GET ONE
# ---------------------------------------------------------------------------

@requests_bp.get("/<uuid:request_id>")
@require_roles(*ADMIN_ROLES)
def get_request_route(request_id):
    try:
        result = get_request(
            request_id
        )

        return success_response(
            {
                "request": result
            }
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

@requests_bp.patch("/<uuid:request_id>")
@require_roles(*ADMIN_ROLES)
def update_request_route(request_id):
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

        payload = validate_update_request(
            payload
        )

        result = update_request(
            request_id,
            payload,
        )

        return success_response(
            {
                "request": result
            },
            message="Request updated successfully.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@requests_bp.delete("/<uuid:request_id>")
@require_roles(*ADMIN_ROLES)
def delete_request_route(request_id):
    try:
        delete_request(
            request_id
        )

        return success_response(
            message="Request deleted successfully."
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# REMINDER
# ---------------------------------------------------------------------------

@requests_bp.post("/<uuid:request_id>/reminders")
@require_roles(*ADMIN_ROLES)
def request_reminder_route(request_id):
    try:
        send_request_reminder(
            request_id
        )

        return success_response(
            message="Reminder email sent successfully."
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# BULK UPDATE
# ---------------------------------------------------------------------------

@requests_bp.patch("/bulk")
@require_roles(*ADMIN_ROLES)
def bulk_update_requests_route():
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

        ids, update_payload = (
            validate_bulk_update_requests(
                payload
            )
        )

        result = bulk_update_requests(
            ids,
            update_payload,
        )

        return success_response(
            result,
            message="Requests updated successfully.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# BULK DELETE
# ---------------------------------------------------------------------------

@requests_bp.delete("/bulk")
@require_roles(*ADMIN_ROLES)
def bulk_delete_requests_route():
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

        ids = validate_bulk_delete_requests(
            payload
        )

        result = bulk_delete_requests(
            ids
        )

        return success_response(
            result,
            message="Requests deleted successfully.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)

# ---------------------------------------------------------------------------
# ISSUE QUOTE
#
# Counterpart to the customer portal's POST /orders/{id}/quote/accept
# (see customer_orders/routes.py) - without this, a request could
# never leave "reviewing".
# ---------------------------------------------------------------------------

@requests_bp.post("/<uuid:request_id>/quote")
@require_roles(*ADMIN_ROLES)
def issue_quote_route(request_id):
    try:
        admin_user = get_current_user()

        payload = request.get_json(silent=True)

        if payload is None:
            return error_response(
                "INVALID_JSON",
                "Request body must contain valid JSON.",
                status=400,
            )

        validated = validate_issue_quote(payload)

        updated = issue_quote(request_id, admin_user, **validated)

        return success_response(
            {"request": serialize_request(updated)},
            message="Quote sent to the customer.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# REFUND (admin portal RequestWorkspace -> "Refund")
# A request is only refundable once it has been converted to a paid
# order; the refund itself is recorded on that order.
# ---------------------------------------------------------------------------

@requests_bp.post("/<uuid:request_id>/refund")
@require_roles(*ADMIN_ROLES)
def refund_request_route(request_id):
    from extensions import db
    from orders.order import Order
    from orders.service import OrderService
    from requests.request import ServiceRequest
    from utils.exceptions import ConflictError, NotFoundError

    service_request = db.session.get(ServiceRequest, request_id)
    if not service_request:
        raise NotFoundError("Request not found.")
    if not service_request.order_id:
        raise ConflictError(
            "This request has not been paid yet, so there is nothing to refund."
        )
    payload = request.get_json(silent=True) or {}
    payload.setdefault("reason", "administrative")
    order = OrderService.refund_order(service_request.order_id, payload)
    order = db.session.get(Order, order.id) if not isinstance(order, Order) else order
    return success_response(
        {"order": {"id": str(order.id), "status": order.status,
                   "refunded_amount": float(order.refunded_amount or 0)}},
        message="Refund recorded.",
    )
