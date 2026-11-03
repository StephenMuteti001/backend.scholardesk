# contact/routes.py
"""
Public website Contact form.

    POST  /api/v1/public/contact                 (no auth, rate limited)
    GET   /api/v1/admin/contact-messages         (admin)
    PATCH /api/v1/admin/contact-messages/<id>    (admin)
"""

from flask import Blueprint, request

from contact.service import (
    create_contact_message,
    list_contact_messages,
    update_contact_message,
)
from utils.authorization import require_roles
from utils.response_formatter import success_response
from utils.roles import ADMIN_ROLES

public_bp = Blueprint("contact_public", __name__, url_prefix="/api/v1/public/contact")
admin_bp = Blueprint("contact_admin", __name__, url_prefix="/api/v1/admin/contact-messages")


def _client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.remote_addr) or None


@public_bp.post("")
def submit_contact():
    payload = request.get_json(silent=True) or {}
    # Honeypot: real visitors never fill the hidden "website" field.
    # Pretend success so bots get no signal.
    if isinstance(payload.get("website"), str) and payload["website"].strip():
        return success_response(
            {"data": {"reference": None}},
            message="Thanks, your message has been sent.",
            status=201,
        )
    msg = create_contact_message(
        payload,
        ip=_client_ip(),
        user_agent=request.headers.get("User-Agent"),
    )
    return success_response(
        {"data": {"reference": msg.reference}},
        message="Thanks, your message has been sent. We'll reply by email within 24 hours.",
        status=201,
    )


@admin_bp.get("")
@require_roles(*ADMIN_ROLES)
def list_messages():
    pagination = list_contact_messages(
        page=request.args.get("page", 1, type=int),
        per_page=request.args.get("per_page", 20, type=int),
        status=request.args.get("status") or None,
        search=request.args.get("search") or None,
    )
    return success_response(
        {
            "data": [m.to_dict() for m in pagination.items],
            "pagination": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "total": pagination.total,
                "pages": pagination.pages,
            },
        }
    )


@admin_bp.patch("/<uuid:message_id>")
@require_roles(*ADMIN_ROLES)
def update_message(message_id):
    msg = update_contact_message(message_id, request.get_json(silent=True) or {})
    return success_response({"data": msg.to_dict()}, message="Contact message updated.")
