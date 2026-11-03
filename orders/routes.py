# app/orders/routes.py

from flask import Blueprint, Response, request
from utils.authorization import require_roles
from utils.roles import ADMIN_ROLES

from orders.service import OrderService
from orders.interest_service import OrderInterestService
# Registers the order_checkouts table with SQLAlchemy/Alembic metadata.
from orders.checkout import OrderCheckout  # noqa: F401
from orders.schemas import (
    serialize_order,
    validate_assign_expert_payload,
    validate_interest_payload,
)
from utils.authorization import get_current_user
from utils.exceptions import ServiceError, ValidationError
from utils.response_formatter import (
    error_response,
    success_response,
)


orders_bp = Blueprint(
    "admin_orders",
    __name__,
    url_prefix="/api/v1/admin/orders",
)


def _handle_service_error(error):
    status_map = {
        "VALIDATION_ERROR": 400,
        "NOT_FOUND": 404,
        "CONFLICT": 409,
        "SERVICE_ERROR": 500,
    }

    return error_response(
        code=error.code,
        message=error.message,
        details=error.details,
        status=status_map.get(error.code, 500),
    )


@orders_bp.get("")
@require_roles(*ADMIN_ROLES)
def list_orders():
    try:
        result = OrderService.list_orders(
            page=request.args.get("page", 1),
            per_page=request.args.get("per_page", 20),
            search=request.args.get("search"),
            status=request.args.get("status"),
            gateway=request.args.get("gateway"),
            sort_by=request.args.get("sort_by", "createdAt"),
            direction=request.args.get("direction", "desc"),
        )

        return success_response(result)

    except ServiceError as exc:
        return _handle_service_error(exc)


@orders_bp.get("/statistics")
@require_roles(*ADMIN_ROLES)
def order_statistics():
    try:
        statistics = OrderService.statistics()

        return success_response(statistics)

    except ServiceError as exc:
        return _handle_service_error(exc)


@orders_bp.get("/export")
@require_roles(*ADMIN_ROLES)
def export_orders():
    try:
        csv_content = OrderService.export_orders(
            search=request.args.get("search"),
            status=request.args.get("status"),
            gateway=request.args.get("gateway"),
            sort_by=request.args.get("sort_by", "createdAt"),
            direction=request.args.get("direction", "desc"),
        )

        return Response(
            csv_content,
            mimetype="text/csv",
            headers={
                "Content-Disposition": (
                    "attachment; filename=orders.csv"
                )
            },
        )

    except ServiceError as exc:
        return _handle_service_error(exc)


@orders_bp.patch("/bulk")
@require_roles(*ADMIN_ROLES)
def bulk_update_orders():
    try:
        payload = request.get_json(silent=True) or {}

        result = OrderService.bulk_update(
            ids=payload.get("ids", []),
            payload=payload,
        )

        return success_response(result)

    except ServiceError as exc:
        return _handle_service_error(exc)


@orders_bp.post("/bulk/receipts")
@require_roles(*ADMIN_ROLES)
def bulk_resend_receipts():
    try:
        payload = request.get_json(silent=True) or {}

        result = OrderService.bulk_resend_receipts(
            payload.get("ids", [])
        )

        return success_response(result)

    except ServiceError as exc:
        return _handle_service_error(exc)


@orders_bp.get("/<uuid:order_id>")
@require_roles(*ADMIN_ROLES)
def get_order(order_id):
    try:
        order = OrderService.get_order(order_id)

        return success_response({
            "order": serialize_order(order),
        })

    except ServiceError as exc:
        return _handle_service_error(exc)


@orders_bp.patch("/<uuid:order_id>")
@require_roles(*ADMIN_ROLES)
def update_order(order_id):
    try:
        payload = request.get_json(silent=True) or {}

        order = OrderService.update_order(
            order_id,
            payload,
        )

        return success_response({
            "order": serialize_order(order),
        })

    except ServiceError as exc:
        return _handle_service_error(exc)


@orders_bp.delete("/<uuid:order_id>")
@require_roles(*ADMIN_ROLES)
def delete_order(order_id):
    try:
        OrderService.delete_order(order_id)

        return success_response(
            message="Order deleted."
        )

    except ServiceError as exc:
        return _handle_service_error(exc)


@orders_bp.post("/<uuid:order_id>/assign")
@require_roles(*ADMIN_ROLES)
def assign_expert(order_id):
    try:
        payload = request.get_json(silent=True) or {}

        validated = validate_assign_expert_payload(payload)

        admin_user = get_current_user()

        order = OrderService.assign_expert(
            order_id,
            validated["expert_id"],
            validated["budget"],
            admin_user,
        )

        return success_response({
            "order": serialize_order(order),
        }, message="Expert assigned.")

    except ValidationError as exc:
        return error_response("VALIDATION_ERROR", str(exc), status=400)

    except ValueError as exc:
        return error_response("VALIDATION_ERROR", str(exc), status=400)

    except ServiceError as exc:
        return _handle_service_error(exc)


@orders_bp.post("/<uuid:order_id>/refund")
@require_roles(*ADMIN_ROLES)
def refund_order(order_id):
    try:
        payload = request.get_json(silent=True) or {}

        order = OrderService.refund_order(
            order_id,
            payload,
        )

        return success_response({
            "order": serialize_order(order),
        })

    except ServiceError as exc:
        return _handle_service_error(exc)


@orders_bp.post("/<uuid:order_id>/receipt")
@require_roles(*ADMIN_ROLES)
def resend_receipt(order_id):
    try:
        OrderService.resend_receipt(order_id)

        return success_response(
            message="Receipt resent."
        )

    except ServiceError as exc:
        return _handle_service_error(exc)


@orders_bp.post("/<uuid:order_id>/download-link")
@require_roles(*ADMIN_ROLES)
def regenerate_download_link(order_id):
    try:
        result = OrderService.regenerate_download_link(
            order_id
        )

        return success_response(result)

    except ServiceError as exc:
        return _handle_service_error(exc)

@orders_bp.get("/<uuid:order_id>/interests")
@require_roles(*ADMIN_ROLES)
def list_order_interests(order_id):
    """
    Experts who have privately registered interest in this order.

    Advisory only - support still assigns through
    POST /admin/orders/<id>/assign and may pick any active expert.
    """
    try:
        include_withdrawn = (
            request.args.get("include_withdrawn", "true").lower()
            not in ("false", "0", "no")
        )

        result = OrderInterestService.list_for_order(
            order_id,
            include_withdrawn=include_withdrawn,
        )

        return success_response({"data": result})

    except ServiceError as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# Expert-facing: "my assignments"
#
# Shares the /api/v1/orders prefix with customer_orders.customer_bp and
# submissions.routes.expert_bp - each registers disjoint paths/methods,
# so there's no collision (see submissions/routes.py for the same
# pattern already in use).
# ---------------------------------------------------------------------------

from utils.roles import CUSTOMER_ROLES, EXPERT_ROLES

expert_bp = Blueprint(
    "orders_expert",
    __name__,
    url_prefix="/api/v1/orders",
)

VALID_BUCKETS = ("new", "active", "completed", "cancelled")


def _caller_is_customer():
    """GET /api/v1/orders[/<id>] is shared with the customer portal
    (customer_orders/routes.py). Flask dispatches to the first
    registered rule (this one), so customer callers are delegated."""
    from utils.authorization import get_current_user as _gcu
    from utils.roles import CUSTOMER_ROLES as _CR
    try:
        return getattr(_gcu(), "role", None) in _CR
    except Exception:
        return False


@expert_bp.get("")
@require_roles(*EXPERT_ROLES, *CUSTOMER_ROLES)
def list_my_assignments():
    if _caller_is_customer():
        from customer_orders.routes import list_orders_route
        return list_orders_route()
    try:
        expert_user = get_current_user()

        bucket = request.args.get("bucket") or request.args.get("status")

        # The expert portal's useAssignments hook sends its own
        # bucket->status vocabulary (assigned/in-progress/completed/
        # cancelled) via ?status=; accept both that and ?bucket=.
        bucket_map = {
            "assigned": "new",
            "in-progress": "active",
            "completed": "completed",
            "cancelled": "cancelled",
        }
        bucket = bucket_map.get(bucket, bucket) or "new"

        if bucket not in VALID_BUCKETS:
            return error_response(
                "VALIDATION_ERROR",
                f"bucket must be one of: {', '.join(VALID_BUCKETS)}",
                status=400,
            )

        page = request.args.get("page", 1, type=int)
        per_page = min(request.args.get("limit", 50, type=int), 100)

        orders = OrderService.list_for_expert(
            expert_user,
            bucket,
            search=request.args.get("search"),
            page=page,
            per_page=per_page,
        )

        return success_response({"orders": orders, "data": orders})

    except ServiceError as exc:
        return _handle_service_error(exc)


@expert_bp.get("/<uuid:order_id>")
@require_roles(*EXPERT_ROLES, *CUSTOMER_ROLES)
def get_my_assignment(order_id):
    if _caller_is_customer():
        from customer_orders.routes import get_order_route
        return get_order_route(order_id)
    try:
        expert_user = get_current_user()

        order = OrderService.get_for_expert(order_id, expert_user)

        return success_response({"order": order, "data": order})

    except ServiceError as exc:
        return _handle_service_error(exc)


@expert_bp.post("/<uuid:order_id>/accept")
@require_roles(*EXPERT_ROLES)
def accept_my_assignment(order_id):
    try:
        expert_user = get_current_user()

        order = OrderService.accept_assignment(order_id, expert_user)

        return success_response(
            {"order": OrderService.serialize_order_for_expert(order)},
            message="Assignment accepted.",
        )

    except ServiceError as exc:
        return _handle_service_error(exc)


@expert_bp.post("/<uuid:order_id>/decline")
@require_roles(*EXPERT_ROLES)
def decline_my_assignment(order_id):
    try:
        expert_user = get_current_user()

        payload = request.get_json(silent=True) or {}

        order = OrderService.decline_assignment(
            order_id, expert_user, payload.get("reason")
        )

        return success_response(
            {"order": OrderService.serialize_order_for_expert(order)},
            message="Assignment declined.",
        )

    except ServiceError as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# Expert-facing: available orders + interest
#
# The expert portal calls two path families for the same capability
# (src/routes/orders.tsx uses /orders/available and
# /expert/orders/<id>/interests; src/routes/assignments.* uses
# /assignments and /expert/assignments/<id>), so both are served -
# expert_bp keeps the /api/v1/orders paths, expert_portal_bp adds the
# /api/v1/expert ones. Both delegate to the same services.
# ---------------------------------------------------------------------------

expert_portal_bp = Blueprint(
    "expert_portal",
    __name__,
    url_prefix="/api/v1/expert",
)


def _available_orders_response():
    expert_user = get_current_user()

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)

    result = OrderInterestService.list_available(
        expert_user,
        search=request.args.get("search"),
        page=max(page, 1),
        per_page=max(per_page, 1),
    )

    return success_response(
        {
            "data": result["items"],
            "orders": result["items"],
            "pagination": result["pagination"],
        }
    )


def _register_interest_response(order_id):
    expert_user = get_current_user()

    payload = request.get_json(silent=True) or {}

    validated = validate_interest_payload(payload)

    interest = OrderInterestService.register_interest(
        expert_user,
        order_id,
        note=validated["note"],
    )

    return success_response(
        {"data": interest},
        message=(
            "Interest registered. Support reviews every order "
            "before assigning it."
        ),
        status=201,
    )


def _withdraw_interest_response(order_id):
    expert_user = get_current_user()

    interest = OrderInterestService.withdraw_interest(
        expert_user, order_id
    )

    return success_response(
        {"data": interest},
        message="Interest withdrawn.",
    )


@expert_bp.get("/available")
@require_roles(*EXPERT_ROLES)
def list_available_orders():
    try:
        return _available_orders_response()

    except ServiceError as exc:
        return _handle_service_error(exc)


@expert_portal_bp.get("/orders/available")
@require_roles(*EXPERT_ROLES)
def list_available_orders_alias():
    try:
        return _available_orders_response()

    except ServiceError as exc:
        return _handle_service_error(exc)


@expert_bp.post("/<uuid:order_id>/interests")
@require_roles(*EXPERT_ROLES)
def register_interest(order_id):
    try:
        return _register_interest_response(order_id)

    except ValueError as exc:
        return error_response("VALIDATION_ERROR", str(exc), status=400)

    except ServiceError as exc:
        return _handle_service_error(exc)


@expert_portal_bp.post("/orders/<uuid:order_id>/interests")
@require_roles(*EXPERT_ROLES)
def register_interest_alias(order_id):
    try:
        return _register_interest_response(order_id)

    except ValueError as exc:
        return error_response("VALIDATION_ERROR", str(exc), status=400)

    except ServiceError as exc:
        return _handle_service_error(exc)


@expert_bp.delete("/<uuid:order_id>/interests")
@require_roles(*EXPERT_ROLES)
def withdraw_interest(order_id):
    try:
        return _withdraw_interest_response(order_id)

    except ServiceError as exc:
        return _handle_service_error(exc)


@expert_portal_bp.delete("/orders/<uuid:order_id>/interests")
@require_roles(*EXPERT_ROLES)
def withdraw_interest_alias(order_id):
    try:
        return _withdraw_interest_response(order_id)

    except ServiceError as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# Expert-facing: /assignments aliases onto the existing assignment
# service (the portal's assignments screens call these paths).
# ---------------------------------------------------------------------------

@expert_portal_bp.get("/assignments")
@require_roles(*EXPERT_ROLES)
def list_expert_assignments():
    try:
        expert_user = get_current_user()

        bucket = request.args.get("bucket") or request.args.get("status")

        bucket_map = {
            "assigned": "new",
            "in-progress": "active",
            "completed": "completed",
            "cancelled": "cancelled",
        }

        bucket = bucket_map.get(bucket, bucket) or "all"

        if bucket != "all" and bucket not in VALID_BUCKETS:
            return error_response(
                "VALIDATION_ERROR",
                f"bucket must be one of: all, {', '.join(VALID_BUCKETS)}",
                status=400,
            )

        page = request.args.get("page", 1, type=int)
        per_page = min(request.args.get("limit", 50, type=int), 100)

        orders = OrderService.list_for_expert(
            expert_user,
            bucket,
            search=request.args.get("search"),
            page=max(page, 1),
            per_page=max(per_page, 1),
        )

        return success_response({"data": orders, "orders": orders})

    except ServiceError as exc:
        return _handle_service_error(exc)


@expert_portal_bp.get("/assignments/<uuid:order_id>")
@require_roles(*EXPERT_ROLES)
def get_expert_assignment(order_id):
    try:
        expert_user = get_current_user()

        order = OrderService.get_for_expert(order_id, expert_user)

        return success_response({"data": order, "order": order})

    except ServiceError as exc:
        return _handle_service_error(exc)
