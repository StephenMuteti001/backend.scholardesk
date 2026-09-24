# integrity_reports/routes.py

from flask import Blueprint, request

from integrity_reports.schemas import validate_list_args, validate_scan_request
from integrity_reports.service import list_reports, submit_scan
from utils.authorization import get_current_user, require_roles
from utils.exceptions import ServiceError
from utils.response_formatter import error_response, success_response
from utils.roles import CUSTOMER_ROLES

customer_bp = Blueprint(
    "integrity_reports_customer",
    __name__,
    url_prefix="/api/v1/integrity-reports",
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


@customer_bp.get("")
@require_roles(*CUSTOMER_ROLES)
def list_reports_route():
    try:
        user = get_current_user()

        params = validate_list_args(request.args)

        result = list_reports(user, **params)

        return success_response({"data": result["items"]})

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@customer_bp.post("")
@require_roles(*CUSTOMER_ROLES)
def submit_scan_route():
    try:
        user = get_current_user()

        is_multipart = request.content_type and "multipart/form-data" in (
            request.content_type
        )

        payload = request.form if is_multipart else (
            request.get_json(silent=True) or {}
        )
        files = request.files

        fields = validate_scan_request(payload, files)

        report = submit_scan(user, fields)

        return success_response(
            {"data": report.to_dict()},
            status=201,
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)
