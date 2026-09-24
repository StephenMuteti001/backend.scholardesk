# assessdesk/routes.py
"""
AssessDesk HTTP surface.

Auth transports (same user, same password, same OTP):
  * Browser (assessdesk.scholardesk.pro, admin portal): existing
    HttpOnly JWT cookies + X-CSRF-TOKEN, via /api/v1/auth/login.
  * Desktop app: /api/v1/assessdesk/auth/* returns a 15-min access JWT
    (Authorization: Bearer) plus a rotating, device-bound refresh token.
"""

import logging
from functools import wraps

from flask import Blueprint, g, request
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, jwt_required

from extensions import db
from users import service as user_service
from users.user import User
from utils.authorization import get_current_user, require_roles
from utils.exceptions import ServiceError, ValidationError
from utils.pagination import paginate_query
from utils.response_formatter import error_response, success_response
from utils.roles import ADMIN_ROLES

from assessdesk import paystack, service
from assessdesk.constants import DESKTOP_ACCESS_TTL
from assessdesk.schemas import (
    serialize_ad_user,
    serialize_grant,
    serialize_package,
    serialize_purchase,
    validate_consume,
    validate_extend,
    validate_list_grants,
    validate_manual_grant,
    validate_package,
    validate_pagination,
    validate_uuid,
)

log = logging.getLogger(__name__)

public_bp = Blueprint("assessdesk", __name__, url_prefix="/api/v1/assessdesk")
admin_bp = Blueprint("assessdesk_admin", __name__, url_prefix="/api/v1/admin/assessdesk")

DESKTOP_CLIENT = "assessdesk_desktop"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _body():
    return request.get_json(silent=True) or {}


def require_assessdesk_user(fn):
    """
    Any signed-in platform user (customer/expert/admin). Desktop tokens
    are additionally checked against their device row so a revoked
    device stops working within one request, not after token expiry.
    """

    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        claims = get_jwt()
        device_id = claims.get("device_id")
        if claims.get("client") == DESKTOP_CLIENT:
            if not device_id or not service.device_is_active(device_id):
                raise ServiceError("SESSION_EXPIRED", "Please sign in again.", status_code=401)
        user = get_current_user()
        if user.status in ("banned", "suspended"):
            raise ServiceError("ACCOUNT_RESTRICTED", "This account is restricted.", status_code=403)
        g.ad_user = user
        g.ad_device_id = device_id
        service.ensure_account(user)
        return fn(*args, **kwargs)

    return wrapper


def _desktop_session_payload(user, device, raw_refresh):
    access = create_access_token(
        identity=str(user.id),
        expires_delta=DESKTOP_ACCESS_TTL,
        additional_claims={"role": user.role, "client": DESKTOP_CLIENT, "device_id": str(device.id)},
    )
    return {
        "access_token": access,
        "access_expires_in": int(DESKTOP_ACCESS_TTL.total_seconds()),
        "refresh_token": raw_refresh,
        "device_id": str(device.id),
    }


# ---------------------------------------------------------------------------
# Registration (web only; the desktop app has no sign-up)
# ---------------------------------------------------------------------------

@public_bp.post("/auth/register")
def register():
    data = _body()
    user = user_service.register_user(
        full_name=data.get("full_name") or data.get("name"),
        email=data.get("email"),
        password=data.get("password"),
        role="customer",
    )
    service.ensure_account(user)
    user_service.send_verification_email_for_user(user)
    return success_response(
        {"user": user_service.serialize_user(user)},
        message="Account created. Check your email to verify it.",
        status=201,
    )


# ---------------------------------------------------------------------------
# Desktop sign-in: password -> OTP -> device session
# ---------------------------------------------------------------------------

@public_bp.post("/auth/login")
def desktop_login():
    data = _body()
    user = user_service.authenticate_password(email=data.get("email"), password=data.get("password"))
    _, otp_session_id = user_service.request_login_otp(user.email)
    return success_response(
        {"otp_required": True, "otp_session_id": otp_session_id},
        message="We've emailed you a 6-digit code.",
    )


@public_bp.post("/auth/resend-otp")
def desktop_resend_otp():
    data = _body()
    _, otp_session_id = user_service.request_login_otp(data.get("email"))
    return success_response({"otp_session_id": otp_session_id}, message="A new code has been sent.")


@public_bp.post("/auth/verify-otp")
def desktop_verify_otp():
    data = _body()
    client_device_id = (data.get("client_device_id") or "").strip()
    if not 8 <= len(client_device_id) <= 64:
        raise ValidationError("client_device_id is required.")

    user = user_service.verify_login_otp(otp_session_id=data.get("otp_session_id"), otp=data.get("otp"))
    service.ensure_account(user)
    device, raw = service.create_device_session(
        user,
        client_device_id=client_device_id,
        device_name=(data.get("device_name") or "")[:120] or None,
        client_version=(data.get("client_version") or "")[:40] or None,
    )
    payload = _desktop_session_payload(user, device, raw)
    payload["user"] = serialize_ad_user(user)
    payload["balance"] = service.build_balance(user.id)
    return success_response(payload, message="Signed in.")


@public_bp.post("/auth/refresh")
def desktop_refresh():
    user, device, raw = service.rotate_device_session(_body().get("refresh_token"))
    return success_response(_desktop_session_payload(user, device, raw))


@public_bp.post("/auth/logout")
@require_assessdesk_user
def desktop_logout():
    if g.ad_device_id:
        service.revoke_device(g.ad_device_id, user_id=g.ad_user.id)
    return success_response(message="Signed out.")


# ---------------------------------------------------------------------------
# Self-service (web cookies or desktop bearer)
# ---------------------------------------------------------------------------

@public_bp.get("/me")
@require_assessdesk_user
def me():
    return success_response({
        "user": serialize_ad_user(g.ad_user),
        "balance": service.build_balance(g.ad_user.id),
    })


@public_bp.get("/me/balance")
@require_assessdesk_user
def my_balance():
    if g.ad_device_id:
        service.touch_device(g.ad_device_id)
    return success_response(service.build_balance(g.ad_user.id))


@public_bp.post("/me/consume")
@require_assessdesk_user
def my_consume():
    f = validate_consume(_body())
    balance = service.consume(
        g.ad_user, f["amount"], f["idempotency_key"],
        device_id=g.ad_device_id, meta=f["meta"],
    )
    return success_response(balance)


@public_bp.get("/packages")
def packages():
    return success_response({"items": [serialize_package(p) for p in service.list_active_packages()]})


@public_bp.post("/purchases")
@require_assessdesk_user
def create_purchase():
    package_id = validate_uuid(_body().get("package_id"), "package_id")
    purchase, url, access_code = service.start_purchase(g.ad_user, package_id)
    return success_response(
        {"purchase": serialize_purchase(purchase), "authorization_url": url, "access_code": access_code},
        status=201,
    )


@public_bp.post("/purchases/<reference>/verify")
@require_assessdesk_user
def verify_purchase(reference):
    purchase = service.fulfil_purchase(reference)
    if purchase.user_id != g.ad_user.id:
        raise ServiceError("NOT_FOUND", "Purchase not found.", status_code=404)
    return success_response({
        "purchase": serialize_purchase(purchase),
        "balance": service.build_balance(g.ad_user.id),
    })


@public_bp.get("/me/purchases")
@require_assessdesk_user
def my_purchases():
    page, per_page = validate_pagination(request.args)
    items, pagination = service.list_my_purchases(g.ad_user.id, page, per_page)
    return success_response({"items": [serialize_purchase(p) for p in items], "pagination": pagination})


@public_bp.post("/webhooks/paystack")
def paystack_webhook():
    raw = request.get_data()
    if not paystack.valid_webhook_signature(raw, request.headers.get("x-paystack-signature", "")):
        return error_response("INVALID_SIGNATURE", "Invalid signature.", status=401)
    event = request.get_json(silent=True) or {}
    data = event.get("data") or {}
    meta = data.get("metadata") or {}
    if event.get("event") == "charge.success" and meta.get("product") == "assessdesk":
        try:
            # Re-verify with Paystack rather than trusting the payload.
            service.fulfil_purchase(data.get("reference"))
        except ServiceError as e:
            log.warning("[assessdesk] webhook fulfil failed for %s: %s", data.get("reference"), e.message)
    # Always 200 so Paystack stops retrying events we've handled or ignore.
    return success_response(message="ok")


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@admin_bp.get("/statistics")
@require_roles(*ADMIN_ROLES)
def admin_statistics():
    return success_response(service.admin_statistics())


@admin_bp.get("/packages")
@require_roles(*ADMIN_ROLES)
def admin_packages():
    return success_response({"items": [serialize_package(p) for p in service.admin_list_packages()]})


@admin_bp.post("/packages")
@require_roles(*ADMIN_ROLES)
def admin_create_package():
    pkg = service.admin_create_package(validate_package(_body()))
    return success_response({"package": serialize_package(pkg)}, message="Package created.", status=201)


@admin_bp.patch("/packages/<package_id>")
@require_roles(*ADMIN_ROLES)
def admin_update_package(package_id):
    pkg = service.admin_update_package(
        validate_uuid(package_id, "package id"), validate_package(_body(), partial=True)
    )
    return success_response({"package": serialize_package(pkg)}, message="Package updated.")


@admin_bp.get("/grants")
@require_roles(*ADMIN_ROLES)
def admin_grants():
    items, pagination = service.admin_list_grants(validate_list_grants(request.args))
    return success_response({
        "items": [serialize_grant(x, include_user=True) for x in items],
        "pagination": pagination,
    })


@admin_bp.post("/grants")
@require_roles(*ADMIN_ROLES)
def admin_create_grant():
    grant = service.admin_manual_grant(get_current_user(), validate_manual_grant(_body()))
    return success_response({"grant": serialize_grant(grant, include_user=True)},
                            message="Questions granted.", status=201)


@admin_bp.post("/grants/<grant_id>/extend")
@require_roles(*ADMIN_ROLES)
def admin_extend_grant(grant_id):
    grant = service.admin_extend_grant(
        get_current_user(), validate_uuid(grant_id, "grant id"), validate_extend(_body())["hours"]
    )
    return success_response({"grant": serialize_grant(grant, include_user=True)}, message="Grant extended.")


@admin_bp.post("/grants/<grant_id>/revoke")
@require_roles(*ADMIN_ROLES)
def admin_revoke_grant(grant_id):
    grant = service.admin_revoke_grant(get_current_user(), validate_uuid(grant_id, "grant id"))
    return success_response({"grant": serialize_grant(grant, include_user=True)}, message="Grant revoked.")


@admin_bp.get("/accounts")
@require_roles(*ADMIN_ROLES)
def admin_accounts():
    page, per_page = validate_pagination(request.args)
    items, pagination = service.admin_list_accounts(
        page, per_page, (request.args.get("search") or "").strip()[:120] or None
    )
    return success_response({"items": items, "pagination": pagination})


@admin_bp.patch("/accounts/<int:user_id>")
@require_roles(*ADMIN_ROLES)
def admin_update_account(user_id):
    data = _body()
    if "enabled" not in data:
        raise ValidationError("enabled is required.")
    service.admin_set_account_enabled(user_id, bool(data["enabled"]))
    return success_response(message="Account updated.")


@admin_bp.get("/users/search")
@require_roles(*ADMIN_ROLES)
def admin_search_users():
    """Typeahead for the manual-grant dialog (any platform user)."""
    term = (request.args.get("q") or "").strip().lower()
    if len(term) < 2:
        return success_response({"items": []})
    like = f"%{term}%"
    users = (User.query
             .filter(db.or_(db.func.lower(User.email).like(like),
                            db.func.lower(User.first_name + " " + User.last_name).like(like)))
             .order_by(User.email.asc()).limit(10).all())
    return success_response({"items": [serialize_ad_user(u) for u in users]})


@admin_bp.get("/purchases")
@require_roles(*ADMIN_ROLES)
def admin_purchases():
    page, per_page = validate_pagination(request.args)
    items, pagination = service.admin_list_purchases(
        page, per_page,
        status=(request.args.get("status") or None),
        search=(request.args.get("search") or "").strip()[:120] or None,
    )
    return success_response({
        "items": [serialize_purchase(p, include_user=True) for p in items],
        "pagination": pagination,
    })
