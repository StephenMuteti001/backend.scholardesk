# dashboard/routes.py
"""
Three role-scoped blueprints sharing one service layer
(dashboard/services.py). This is the pattern recommended for every
module going forward - see the architecture note in this project's
delivery notes for the reasoning.

    admin_bp    -> /admin/dashboard/...     ADMIN_ROLES
    customer_bp -> /customer/dashboard/...  CUSTOMER_ROLES
    expert_bp   -> /expert/dashboard/...    EXPERT_ROLES
"""

from flask import Blueprint, request

from dashboard.schemas import validate_overview_args
from dashboard.services import (
    get_admin_overview,
    get_admin_statistics,
    get_customer_overview,
    get_customer_statistics,
    get_expert_overview,
    get_expert_statistics,
)
from utils.authorization import get_current_user, require_roles
from utils.exceptions import ServiceError
from utils.response_formatter import error_response, success_response
from utils.roles import ADMIN_ROLES, CUSTOMER_ROLES, EXPERT_ROLES

admin_bp = Blueprint(
    "dashboard_admin",
    __name__,
    url_prefix="/api/v1/admin/dashboard",
)

customer_bp = Blueprint(
    "dashboard_customer",
    __name__,
    url_prefix="/api/v1/customer/dashboard",
)

expert_bp = Blueprint(
    "dashboard_expert",
    __name__,
    url_prefix="/api/v1/expert/dashboard",
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
# ADMIN
#
# Paths/response shapes intentionally match what
# scholaredge-admin-frontend-code/src/services/dashboardService.ts
# already calls: GET /admin/dashboard/statistics, GET
# /admin/dashboard/overview.
# ---------------------------------------------------------------------------

@admin_bp.get("/statistics")
@require_roles(*ADMIN_ROLES)
def admin_statistics_route():
    try:
        return success_response(get_admin_statistics())

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@admin_bp.get("/overview")
@require_roles(*ADMIN_ROLES)
def admin_overview_route():
    try:
        params = validate_overview_args(request.args)

        return success_response(
            get_admin_overview(months=params["months"])
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# CUSTOMER
# ---------------------------------------------------------------------------

@customer_bp.get("/statistics")
@require_roles(*CUSTOMER_ROLES)
def customer_statistics_route():
    try:
        user = get_current_user()

        return success_response(get_customer_statistics(user))

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@customer_bp.get("/overview")
@require_roles(*CUSTOMER_ROLES)
def customer_overview_route():
    try:
        user = get_current_user()

        return success_response(get_customer_overview(user))

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# EXPERT
# ---------------------------------------------------------------------------

@expert_bp.get("/statistics")
@require_roles(*EXPERT_ROLES)
def expert_statistics_route():
    try:
        user = get_current_user()

        return success_response(get_expert_statistics(user))

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@expert_bp.get("/overview")
@require_roles(*EXPERT_ROLES)
def expert_overview_route():
    try:
        user = get_current_user()

        return success_response(get_expert_overview(user))

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)
