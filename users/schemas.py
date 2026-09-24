# users/schemas.py

import re

from users.constants import (
    PASSWORD_MIN_LENGTH,
    USER_ROLES,
    USER_STATUSES,
)
from utils.exceptions import ValidationError


EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)


def validate_email(email):
    if not email:
        raise ValidationError("Email is required.")

    email = email.strip().lower()

    if not EMAIL_PATTERN.match(email):
        raise ValidationError("Please provide a valid email address.")

    return email


def validate_password(password):
    if not password:
        raise ValidationError("Password is required.")

    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValidationError(
            f"Password must be at least {PASSWORD_MIN_LENGTH} characters long."
        )

    return password


def validate_name(value, field_name):
    if not value:
        raise ValidationError(f"{field_name} is required.")

    value = value.strip()

    if len(value) < 2:
        raise ValidationError(
            f"{field_name} must contain at least 2 characters."
        )

    return value


# Legacy/UX role names accepted from callers and normalized to the
# canonical DB value before validation. Keep in sync with the notes
# in utils/roles.py ("writer" is the legacy term for "expert"; "client"
# is the legacy term for "customer").
ROLE_ALIASES = {
    "writer": "expert",
    "client": "customer",
}


def normalize_role(role):
    if role is None:
        return role

    role = role.strip().lower()

    return ROLE_ALIASES.get(role, role)


def validate_role(role):
    role = normalize_role(role)

    if role not in USER_ROLES:
        raise ValidationError(
            "Invalid user role.",
            {"allowed": list(USER_ROLES)},
        )

    return role


def validate_full_name(value):
    """
    Validate a single "full name" field, as sent by every
    frontend's registration form (`full_name`).
    """
    if not value:
        raise ValidationError("Full name is required.")

    value = value.strip()

    if len(value) < 2:
        raise ValidationError(
            "Full name must contain at least 2 characters."
        )

    return value


def validate_status(status):
    if status not in USER_STATUSES:
        raise ValidationError(
            "Invalid user status.",
            {"allowed": list(USER_STATUSES)},
        )

    return status


def serialize_user(user):
    return {
        "id": str(user.id),
        "name": user.full_name,
        "full_name": user.full_name,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "country": user.country,
        "role": user.role,
        "status": user.status,
        "account_status": user.account_status,
        "application_status": user.application_status,
        "email_verified": user.is_email_verified,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_active": (
            user.last_active_at.isoformat()
            if user.last_active_at
            else None
        ),
        "last_login": (
            user.last_login_at.isoformat()
            if user.last_login_at
            else None
        ),
    }


def serialize_admin_user(user):
    return serialize_user(user)