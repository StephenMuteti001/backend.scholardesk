# payments/constants.py

PAYMENT_STATUS_SCHEDULED = "scheduled"
PAYMENT_STATUS_PROCESSING = "processing"
PAYMENT_STATUS_PAID = "paid"
PAYMENT_STATUS_ON_HOLD = "on-hold"

PAYMENT_STATUSES = {
    PAYMENT_STATUS_SCHEDULED,
    PAYMENT_STATUS_PROCESSING,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_ON_HOLD,
}

PAYMENT_METHOD_BANK_TRANSFER = "bank_transfer"
PAYMENT_METHOD_MOBILE_MONEY = "mobile_money"
PAYMENT_METHOD_PAYPAL = "paypal"
PAYMENT_METHOD_OTHER = "other"

PAYMENT_METHODS = {
    PAYMENT_METHOD_BANK_TRANSFER,
    PAYMENT_METHOD_MOBILE_MONEY,
    PAYMENT_METHOD_PAYPAL,
    PAYMENT_METHOD_OTHER,
}

DEFAULT_PAYMENT_CURRENCY = "USD"

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100

DEFAULT_SORT_BY = "due_at"

ALLOWED_SORT_FIELDS = {
    "expert": "expert_name",
    "period_start": "period_start",
    "period_end": "period_end",
    "jobs": "jobs",
    "amount": "amount",
    "due_at": "due_at",
    "status": "status",
    "created_at": "created_at",
}

SORT_DIRECTIONS = {
    "asc",
    "desc",
}

ALLOWED_TRANSITIONS = {
    PAYMENT_STATUS_SCHEDULED: {
        PAYMENT_STATUS_PROCESSING,
        PAYMENT_STATUS_ON_HOLD,
    },
    PAYMENT_STATUS_PROCESSING: {
        PAYMENT_STATUS_PAID,
        PAYMENT_STATUS_ON_HOLD,
    },
    PAYMENT_STATUS_ON_HOLD: {
        PAYMENT_STATUS_SCHEDULED,
        PAYMENT_STATUS_PROCESSING,
    },
    PAYMENT_STATUS_PAID: set(),
}