CUSTOMER_ROLE = "customer"

CUSTOMER_STATUSES = (
    "active",
    "pending",
    "suspended",
    "banned",
)

CUSTOMER_SORT_FIELDS = {
    "name": "name",
    "email": "email",
    "country": "country",
    "joinedAt": "joined_at",
    "joined_at": "joined_at",
    "requests": "requests",
    "orders": "orders",
    "spend": "spend",
    "status": "status",
    "lastActive": "last_active",
    "last_active": "last_active",
}

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100

DEFAULT_SORT_BY = "joined_at"
DEFAULT_DIRECTION = "desc"

DEFAULT_MESSAGE_SUBJECT = "Message from ScholarDesk"
DEFAULT_MESSAGE_BODY = "Hi, following up on your account."