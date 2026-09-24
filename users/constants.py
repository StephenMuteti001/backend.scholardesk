# users/constants.py

USER_ROLES = (
    "customer",
    "expert",
    "admin",
    "super_admin",
)

USER_STATUSES = (
    "pending",
    "active",
    "suspended",
    "banned",
)

EMAIL_VERIFICATION_STATUSES = (
    "unverified",
    "verified",
)

ACCOUNT_STATUSES = (
    "awaiting_initial_deposit",
    "active",
    "suspended",
    "closed",
)

SUSPENSION_TYPES = (
    "temporary",
    "indefinite",
)

DEFAULT_USER_STATUS = "pending"
DEFAULT_ACCOUNT_STATUS = "active"
DEFAULT_EMAIL_VERIFICATION_STATUS = "unverified"

OTP_EXPIRY_MINUTES = 10
MAX_LOGIN_OTP_ATTEMPTS = 5

PASSWORD_MIN_LENGTH = 8

# Fields that administrators are allowed to sort by.
USER_SORT_FIELDS = (
    "name",
    "email",
    "country",
    "created_at",
    "last_active",
    "status",
    "role",
)

# Fields that administrators are allowed to search.
USER_SEARCH_FIELDS = (
    "first_name",
    "last_name",
    "email",
    "country",
)