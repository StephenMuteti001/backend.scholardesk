# platform_settings/workspace.py
"""
Admin portal "Settings & Team" backend.

    GET    /api/v1/admin/settings               -> { settings }
    PUT    /api/v1/admin/settings               -> { settings }  (partial merge)
    GET    /api/v1/admin/team                   -> { items }
    POST   /api/v1/admin/team/invitations       -> { member }    (super_admin)
    PATCH  /api/v1/admin/team/<id>              -> { member }    (super_admin)
    DELETE /api/v1/admin/team/<id>              -> 200           (super_admin)

"Team" = users with an admin role. Inviting promotes an EXISTING
ScholarDesk account (matched by email) to admin; no passwords are ever
generated or emailed. Removing demotes the member back to customer.
"""

import copy

from flask import Blueprint, current_app, request

from extensions import db
from platform_settings.service import get_settings
from users.user import User
from utils.authorization import get_current_user, require_roles
from utils.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from utils.response_formatter import success_response
from utils.roles import ADMIN_ROLES

WORKSPACE_DEFAULTS = {
    "general": {
        "brand_name": "ScholarDesk",
        "support_email": "support@scholardesk.pro",
        "default_currency": "USD",
        "api_base_url": "https://api.scholardesk.pro/api/v1",
        "policy_note": "",
    },
    "services": {
        "quote_sla_minutes": 60,
        "rush_surcharge_percent": 25,
        "ai_report_base_price": 0,
        "free_revisions": 2,
        "auto_assign_by_speciality": False,
        "require_quote_approval": True,
    },
    "notifications": {
        "new_request_email": True,
        "quote_accepted_alerts": True,
        "licence_expiry_warnings": True,
        "weekly_performance_digest": False,
    },
}

workspace_bp = Blueprint("workspace_admin", __name__, url_prefix="/api/v1/admin")


def _merged(stored):
    out = copy.deepcopy(WORKSPACE_DEFAULTS)
    for section, values in (stored or {}).items():
        if section in out and isinstance(values, dict):
            out[section].update({k: v for k, v in values.items() if k in out[section]})
    return out


def _validate(payload):
    errors = {}
    clean = {}
    for section, values in payload.items():
        if section not in WORKSPACE_DEFAULTS:
            continue
        if not isinstance(values, dict):
            errors[section] = "Must be an object."
            continue
        clean[section] = {}
        for key, value in values.items():
            if key not in WORKSPACE_DEFAULTS[section]:
                continue
            default = WORKSPACE_DEFAULTS[section][key]
            field = f"{section}.{key}"
            if isinstance(default, bool):
                if not isinstance(value, bool):
                    errors[field] = "Must be true or false."
                    continue
            elif isinstance(default, (int, float)):
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                    errors[field] = "Must be a number of 0 or more."
                    continue
            else:
                if not isinstance(value, str) or len(value) > 1000:
                    errors[field] = "Must be text under 1000 characters."
                    continue
                value = value.strip()
                if key == "support_email" and value and "@" not in value:
                    errors[field] = "Enter a valid email address."
                    continue
                if key == "default_currency" and value and len(value) != 3:
                    errors[field] = "Use a 3-letter currency code, e.g. USD."
                    continue
                if key == "default_currency":
                    value = value.upper()
            clean[section][key] = value
    if errors:
        raise ValidationError("Some settings are invalid.", details=errors)
    return clean


@workspace_bp.get("/settings")
@require_roles(*ADMIN_ROLES)
def get_workspace_settings():
    settings = get_settings()
    return success_response({"settings": _merged(settings.workspace)})


@workspace_bp.put("/settings")
@require_roles(*ADMIN_ROLES)
def update_workspace_settings():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError("Send the settings as a JSON object.")
    clean = _validate(payload)
    settings = get_settings()
    stored = copy.deepcopy(settings.workspace or {})
    for section, values in clean.items():
        stored.setdefault(section, {}).update(values)
    settings.workspace = stored
    settings.updated_by = get_current_user().id
    db.session.commit()
    return success_response({"settings": _merged(stored)}, message="Settings saved.")


# ----------------------------------------------------------------- team

def _member(user):
    status = "suspended" if user.status in {"suspended", "banned"} else "active"
    return {
        "id": str(user.id),
        "name": user.full_name or user.email,
        "email": user.email,
        "role": "superadmin" if user.role == "super_admin" else user.role,
        "status": status,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def _require_super_admin():
    actor = get_current_user()
    if actor.role != "super_admin":
        raise ForbiddenError("Only a super admin can manage the team.")
    return actor


def _get_admin(member_id):
    user = db.session.get(User, member_id)
    if not user or user.role not in ADMIN_ROLES:
        raise NotFoundError("Team member not found.")
    return user


@workspace_bp.get("/team")
@require_roles(*ADMIN_ROLES)
def list_team():
    users = (
        User.query.filter(User.role.in_(ADMIN_ROLES))
        .order_by(User.created_at.asc())
        .all()
    )
    return success_response({"items": [_member(u) for u in users]})


@workspace_bp.post("/team/invitations")
@require_roles(*ADMIN_ROLES)
def invite_member():
    _require_super_admin()
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise ValidationError("Enter a valid email address.", details={"email": "Invalid email."})
    user = User.query.filter(db.func.lower(User.email) == email).first()
    if not user:
        raise NotFoundError(
            "No ScholarDesk account uses this email yet. Ask them to create an account "
            "at auth.scholardesk.pro first, then invite them again."
        )
    if user.role in ADMIN_ROLES:
        raise ConflictError("This person is already on the admin team.")
    user.role = "admin"
    db.session.commit()
    current_app.logger.info("User %s promoted to admin", user.id)
    return success_response(
        {"member": _member(user)},
        message=f"{user.email} now has admin access.",
        status=201,
    )


@workspace_bp.patch("/team/<int:member_id>")
@require_roles(*ADMIN_ROLES)
def update_member(member_id):
    actor = _require_super_admin()
    user = _get_admin(member_id)
    payload = request.get_json(silent=True) or {}
    if user.id == actor.id and payload.get("status") == "suspended":
        raise ConflictError("You cannot suspend your own account.")
    if payload.get("status") in {"active", "suspended"}:
        user.status = "active" if payload["status"] == "active" else "suspended"
    db.session.commit()
    return success_response({"member": _member(user)}, message="Team member updated.")


@workspace_bp.delete("/team/<int:member_id>")
@require_roles(*ADMIN_ROLES)
def remove_member(member_id):
    actor = _require_super_admin()
    user = _get_admin(member_id)
    if user.id == actor.id:
        raise ConflictError("You cannot remove yourself from the team.")
    user.role = "customer"
    db.session.commit()
    return success_response(message="Admin access removed.")
