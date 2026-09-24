# platform_settings/routes.py

from flask import Blueprint, request

from platform_settings.service import get_settings, update_settings
from utils.authorization import get_current_user, require_roles
from utils.exceptions import ServiceError
from utils.response_formatter import error_response, success_response
from utils.roles import ADMIN_ROLES

# Public - read by every ScholarDesk frontend, no auth required. See
# the auth-portal frontend repo, src/lib/platform.ts, for the exact
# contract this must satisfy.
public_bp = Blueprint(
    "platform_settings_public",
    __name__,
    url_prefix="/platform",
)

admin_bp = Blueprint(
    "platform_settings_admin",
    __name__,
    url_prefix="/api/v1/admin/settings",
)


@public_bp.get("/settings")
def get_platform_settings():
    settings = get_settings()

    return success_response({"data": settings.to_dict()})


@admin_bp.get("/writer-hiring")
@require_roles(*ADMIN_ROLES)
def get_writer_hiring_setting():
    settings = get_settings()

    return success_response({"data": settings.to_dict()})


@admin_bp.patch("/writer-hiring")
@require_roles(*ADMIN_ROLES)
def update_writer_hiring_setting():
    try:
        actor = get_current_user()

        payload = request.get_json(silent=True) or {}

        settings = update_settings(payload, actor)

        return success_response(
            {"data": settings.to_dict()},
            message="Settings updated.",
        )

    except ServiceError as exc:
        return error_response(exc.code, exc.message, exc.details, exc.status_code)
