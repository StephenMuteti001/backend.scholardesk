from flask import Blueprint, request

from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies,
)

from utils.authorization import require_roles
from utils.exceptions import ConflictError
from utils.roles import ADMIN_ROLES
from utils.response_formatter import success_response
from users import service

users_bp = Blueprint(
    "users",
    __name__,
    url_prefix="/api/v1",
)

@users_bp.post("/auth/register")
def register():
    data = request.get_json() or {}

    user = service.register_user(
        full_name=data.get("full_name") or data.get("name"),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        email=data.get("email"),
        password=data.get("password"),
        country=data.get("country"),
        role=data.get("role", "customer"),
    )

    service.send_verification_email_for_user(user)

    return success_response(
        {
            "user": service.serialize_user(user),
        },
        message="Account created successfully.",
        status=201,
    )



@users_bp.post("/auth/login")
def login():
    data = request.get_json() or {}

    user = service.authenticate_password(
        email=data.get("email"),
        password=data.get("password"),
    )

    _, otp_session_id = service.request_login_otp(user.email)

    return success_response(
        {
            "otp_required": True,
            "otp_session_id": otp_session_id,
        },
        message="A login code has been sent.",
    )


@users_bp.post("/auth/login/otp")
def request_otp():
    data = request.get_json() or {}

    _, otp_session_id = service.request_login_otp(
        data.get("email")
    )

    return success_response(
        {
            "otp_session_id": otp_session_id,
        },
        message="A login code has been sent."
    )



@users_bp.post("/auth/login/verify-otp")
def verify_login_otp():
    data = request.get_json() or {}

    user = service.verify_login_otp(
        otp_session_id=data.get("otp_session_id"),
        otp=data.get("otp"),
    )

    access_token, refresh_token = (
        service.generate_tokens_for_user(user)
    )

    response, status = success_response(
        {
            "user": service.serialize_user(user),
        },
        message="Login successful.",
    )

    set_access_cookies(
        response,
        access_token,
    )

    set_refresh_cookies(
        response,
        refresh_token,
    )

    return response, status


@users_bp.get("/auth/me")
@jwt_required()
def me():
    user_id = get_jwt_identity()

    user = service.get_user_by_id(user_id)

    return success_response({
        "user": service.serialize_user(user),
    })


@users_bp.get("/auth/verify-email")
def verify_email():
    token = request.args.get("token")

    user = service.verify_user_email(token)

    return success_response(
        {
            "user": service.serialize_user(user),
        },
        message="Email verified successfully.",
    )


@users_bp.get("/admin/users")
@require_roles(*ADMIN_ROLES)
def list_admin_users():
    page = request.args.get(
        "page",
        1,
        type=int,
    )

    per_page = request.args.get(
        "per_page",
        20,
        type=int,
    )

    pagination = service.list_users(
        page=page,
        per_page=per_page,
        search=request.args.get("search"),
        status=request.args.get("status"),
        role=request.args.get("role"),
        country=request.args.get("country"),
        sort_by=request.args.get(
            "sort_by",
            "created_at",
        ),
        direction=request.args.get(
            "direction",
            "desc",
        ),
    )

    return success_response({
        "items": [
            service.serialize_user(user)
            for user in pagination.items
        ],
        "pagination": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "pages": pagination.pages,
            "total": pagination.total,
        },
    })


@users_bp.get("/admin/users/<int:user_id>")
@require_roles(*ADMIN_ROLES)
def get_admin_user(user_id):
    user = service.get_user_by_id(user_id)

    return success_response({
        "user": service.serialize_user(user),
    })



@users_bp.patch("/admin/users/<int:user_id>")
@require_roles(*ADMIN_ROLES)
def update_admin_user(user_id):
    data = request.get_json() or {}

    acting_user = service.get_user_by_id(
        get_jwt_identity()
    )

    user = service.update_user(
        user_id,
        data,
        acting_user=acting_user,
    )

    return success_response({
        "user": service.serialize_user(user),
    })



@users_bp.delete("/admin/users/<int:user_id>")
@require_roles(*ADMIN_ROLES)
def delete_admin_user(user_id):
    acting_user = service.get_user_by_id(
        get_jwt_identity()
    )

    service.delete_user(
        user_id,
        acting_user=acting_user,
    )

    return success_response(
        message="User account removed."
    )


@users_bp.post("/auth/refresh")
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()

    user = service.get_user_by_id(user_id)

    if user.status in {"banned", "suspended"}:
        raise ConflictError(
            "This account is currently unavailable."
        )

    access_token = service.generate_access_token(user)


    response, status = success_response(
        {
            "user": service.serialize_user(user),
        },
        message="Access token refreshed.",
    )

    set_access_cookies(
        response,
        access_token,
    )

    return response, status


@users_bp.post("/auth/logout")
@jwt_required(optional=True)
def logout():
    response, status = success_response(
        message="Successfully logged out."
    )

    unset_jwt_cookies(response)

    return response, status