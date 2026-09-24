# support_chat/routes.py

from flask import Blueprint, request

from support_chat.schemas import validate_send_message, validate_start_thread
from support_chat.service import (
    list_messages,
    list_threads,
    send_message,
    start_thread,
    thread_to_dict,
)
from utils.authorization import get_current_user, require_roles
from utils.exceptions import ServiceError
from utils.response_formatter import error_response, success_response
from utils.roles import CUSTOMER_ROLES, EXPERT_ROLES

# Despite the internal name, this now serves BOTH customers and
# experts contacting support - each is scoped to only their own
# threads (list_threads()/etc. filter by the requesting user's own
# id), so a customer and an expert can never see each other's
# conversation. This is what the expert portal's Messages page and
# SupportChatWidget actually call; docs/API.md's "writers are never
# participants" rule is about not being added into a *customer's*
# thread, not about experts being denied a support channel of their
# own.
customer_bp = Blueprint(
    "support_chat_customer",
    __name__,
    url_prefix="/api/v1/support-chat",
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
@require_roles(*CUSTOMER_ROLES, *EXPERT_ROLES)
def list_threads_route():
    try:
        user = get_current_user()

        return success_response({"data": list_threads(user)})

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@customer_bp.post("")
@require_roles(*CUSTOMER_ROLES, *EXPERT_ROLES)
def start_thread_route():
    try:
        user = get_current_user()

        payload = request.get_json(silent=True) or {}
        validated = validate_start_thread(payload)

        thread = start_thread(
            user,
            validated["subject"],
            validated["order_reference"],
        )

        return success_response(
            {"data": thread_to_dict(thread)},
            status=201,
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@customer_bp.get("/<uuid:chat_id>/messages")
@require_roles(*CUSTOMER_ROLES, *EXPERT_ROLES)
def list_messages_route(chat_id):
    try:
        user = get_current_user()

        return success_response(
            {"data": list_messages(chat_id, user)}
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@customer_bp.post("/<uuid:chat_id>/messages")
@require_roles(*CUSTOMER_ROLES, *EXPERT_ROLES)
def send_message_route(chat_id):
    try:
        user = get_current_user()

        payload = request.get_json(silent=True) or {}
        validated = validate_send_message(payload)

        message = send_message(chat_id, user, validated["body"])

        return success_response(
            {"data": message.to_dict()},
            status=201,
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)
