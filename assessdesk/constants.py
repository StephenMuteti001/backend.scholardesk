# assessdesk/constants.py
"""
AssessDesk: answer-question credits for the AssessDesk desktop tool.

All times are UTC. Every datetime column is TIMESTAMPTZ and every value
written by this module comes from `utcnow()` below, never from the
client. The desktop app receives `expires_in_seconds` alongside ISO
timestamps so a wrong local clock can never extend (or shorten) access.
"""

from datetime import timedelta

# --- Starter grant (every new AssessDesk account, once) ---
STARTER_QUESTIONS = 5
STARTER_VALIDITY_DAYS = 7

# --- Expiry grace window ---
# After `expires_at`, remaining questions stay usable for this long,
# then they are forfeited. The user is emailed when grace begins.
GRACE_PERIOD = timedelta(hours=3)

# --- Low-balance thresholds (questions left). Each is notified once
# per downward crossing; a new purchase re-arms them. ---
LOW_BALANCE_THRESHOLDS = (10, 3, 0)

# --- Expiry warnings (hours before expires_at). Each notified once per grant. ---
EXPIRY_WARNING_HOURS = (72, 24)

# --- Consumption limits ---
MAX_CONSUME_PER_CALL = 10
IDEMPOTENCY_KEY_MAX_LEN = 64

# --- Desktop device sessions ---
DESKTOP_ACCESS_TTL = timedelta(minutes=15)
DESKTOP_REFRESH_TTL = timedelta(days=30)
MAX_ACTIVE_DEVICES_PER_USER = 3

# --- Grant statuses (stored) ---
GRANT_ACTIVE = "active"
GRANT_EXHAUSTED = "exhausted"
GRANT_EXPIRED = "expired"
GRANT_REVOKED = "revoked"
GRANT_STATUSES = (GRANT_ACTIVE, GRANT_EXHAUSTED, GRANT_EXPIRED, GRANT_REVOKED)

# Derived (API-only) status for an active grant inside the grace window.
GRANT_IN_GRACE = "grace"

# --- Grant sources ---
SOURCE_STARTER = "starter"
SOURCE_PURCHASE = "purchase"
SOURCE_ADMIN = "admin"
GRANT_SOURCES = (SOURCE_STARTER, SOURCE_PURCHASE, SOURCE_ADMIN)

# --- Ledger reasons ---
LEDGER_GRANT = "grant"
LEDGER_CONSUME = "consume"
LEDGER_REVOKE = "revoke"
LEDGER_EXPIRE = "expire"
LEDGER_ADJUST = "adjust"

# --- Purchase statuses ---
PURCHASE_PENDING = "pending"
PURCHASE_PAID = "paid"
PURCHASE_FAILED = "failed"
PURCHASE_ABANDONED = "abandoned"
PURCHASE_STATUSES = (PURCHASE_PENDING, PURCHASE_PAID, PURCHASE_FAILED, PURCHASE_ABANDONED)

# --- Admin listing ---
GRANT_SORT_FIELDS = {"granted_at", "expires_at", "questions_remaining", "status"}
PACKAGE_SORT_FIELDS = {"sort_order", "price", "questions", "created_at"}
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100

PAYSTACK_API_BASE = "https://api.paystack.co"
