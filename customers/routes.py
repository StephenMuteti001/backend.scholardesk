from flask import Blueprint, request
from utils.authorization import require_roles
from utils.roles import ADMIN_ROLES
from customers.customer import customer_to_dict

from customers.schemas import (
    validate_list_customers,
    validate_update_customer,
    validate_bulk_update_customers,
    validate_bulk_email_customers,
    validate_message_customer,
)

from customers.service import (
    list_customers,
    get_customer,
    update_customer,
    delete_customer,
    bulk_update_customers,
    bulk_email_customers,
    message_customer,
    get_customer_statistics,
)

from utils.response_formatter import (
    success_response,
    error_response,
)

from utils.exceptions import ServiceError


customers_bp = Blueprint(
    "customers",
    __name__,
    url_prefix="/api/v1/admin/customers",
)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def _handle_service_error(exc):
    if isinstance(exc, ServiceError):
        status = 400

        if exc.code == "NOT_FOUND":
            status = 404

        elif exc.code == "CONFLICT":
            status = 409

        elif exc.code == "VALIDATION_ERROR":
            status = 422

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

@customers_bp.get("")
@require_roles(*ADMIN_ROLES)
def list_customer_route():

    try:
        params = validate_list_customers(
            request.args
        )

        result = list_customers(
            **params
        )

        return success_response(
            {
                "items": [
                    customer_to_dict(
                        customer
                    )
                    for customer in result["items"]
                ],
                "pagination": result["pagination"],
                "countries": result["countries"],
            }
        )

    except ServiceError as exc:
        return _handle_service_error(exc)

    except Exception as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# STATISTICS
# ---------------------------------------------------------------------------

@customers_bp.get("/statistics")
@require_roles(*ADMIN_ROLES)
def customer_statistics_route():

    try:
        statistics = (
            get_customer_statistics()
        )

        return success_response(
            statistics
        )

    except ServiceError as exc:
        return _handle_service_error(exc)

    except Exception as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# GET ONE
# ---------------------------------------------------------------------------

@customers_bp.get("/<int:customer_id>")
@require_roles(*ADMIN_ROLES)
def get_customer_route(customer_id):

    try:
        customer = get_customer(
            customer_id
        )

        return success_response(
            {
                "customer":
                    customer_to_dict(
                        customer
                    )
            }
        )

    except ServiceError as exc:
        return _handle_service_error(exc)

    except Exception as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

@customers_bp.patch("/<int:customer_id>")
@require_roles(*ADMIN_ROLES)
def update_customer_route(
    customer_id
):

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

        payload = validate_update_customer(
            payload
        )

        customer = update_customer(
            customer_id,
            payload,
        )

        return success_response(
            {
                "customer":
                    customer_to_dict(
                        customer
                    )
            },
            message="Customer updated successfully.",
        )

    except ServiceError as exc:
        return _handle_service_error(exc)

    except Exception as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@customers_bp.delete("/<int:customer_id>")
@require_roles(*ADMIN_ROLES)
def delete_customer_route(
    customer_id
):

    try:
        delete_customer(
            customer_id
        )

        return success_response(
            message="Customer deleted successfully."
        )

    except ServiceError as exc:
        return _handle_service_error(exc)

    except Exception as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# MESSAGE
# ---------------------------------------------------------------------------

@customers_bp.post(
    "/<int:customer_id>/messages"
)
@require_roles(*ADMIN_ROLES)
def message_customer_route(
    customer_id
):

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

        payload = (
            validate_message_customer(
                payload
            )
        )

        result = message_customer(
            customer_id,
            payload.get("subject"),
            payload["body"],
        )

        return success_response(
            result,
            message="Message sent successfully.",
        )

    except ServiceError as exc:
        return _handle_service_error(exc)

    except Exception as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# BULK UPDATE
# ---------------------------------------------------------------------------

@customers_bp.patch("/bulk")
@require_roles(*ADMIN_ROLES)
def bulk_update_customer_route():

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
            validate_bulk_update_customers(
                payload
            )
        )

        count = bulk_update_customers(
            validated["ids"],
            validated["status"],
        )

        return success_response(
            {
                "count": count,
            },
            message="Customers updated successfully.",
        )

    except ServiceError as exc:
        return _handle_service_error(exc)

    except Exception as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# BULK EMAIL
# ---------------------------------------------------------------------------

@customers_bp.post("/bulk/emails")
@require_roles(*ADMIN_ROLES)
def bulk_email_customer_route():

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
            validate_bulk_email_customers(
                payload
            )
        )

        count = bulk_email_customers(
            validated["ids"],
            validated.get("subject"),
            validated.get("body"),
        )

        return success_response(
            {
                "count": count,
            },
            message="Email sent successfully.",
        )

    except ServiceError as exc:
        return _handle_service_error(exc)

    except Exception as exc:
        return _handle_service_error(exc)