# requests/constants.py

# ---------------------------------------------------------------------------
# Request types
# ---------------------------------------------------------------------------

REQUEST_TYPE_ASSIGNMENT = "assignment"
REQUEST_TYPE_CLASS = "class"
REQUEST_TYPE_AI_REPORT = "ai-report"
REQUEST_TYPE_AI_REMOVAL = "ai-removal"
REQUEST_TYPE_EXAM = "exam"
REQUEST_TYPE_INTERVIEW = "interview"

REQUEST_TYPES = {
    REQUEST_TYPE_ASSIGNMENT,
    REQUEST_TYPE_CLASS,
    REQUEST_TYPE_AI_REPORT,
    REQUEST_TYPE_AI_REMOVAL,
    REQUEST_TYPE_EXAM,
    REQUEST_TYPE_INTERVIEW,
}


# ---------------------------------------------------------------------------
# Request statuses
# ---------------------------------------------------------------------------

REQUEST_STATUS_NEW = "new"
REQUEST_STATUS_REVIEWING = "reviewing"
REQUEST_STATUS_QUOTED = "quoted"
REQUEST_STATUS_IN_PROGRESS = "in-progress"
REQUEST_STATUS_DELIVERED = "delivered"
REQUEST_STATUS_COMPLETED = "completed"
REQUEST_STATUS_CANCELLED = "cancelled"

REQUEST_STATUSES = {
    REQUEST_STATUS_NEW,
    REQUEST_STATUS_REVIEWING,
    REQUEST_STATUS_QUOTED,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_DELIVERED,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_CANCELLED,
}


# ---------------------------------------------------------------------------
# Priorities
# ---------------------------------------------------------------------------

PRIORITY_LOW = "low"
PRIORITY_NORMAL = "normal"
PRIORITY_HIGH = "high"
PRIORITY_URGENT = "urgent"

REQUEST_PRIORITIES = {
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    PRIORITY_HIGH,
    PRIORITY_URGENT,
}


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

REQUEST_SORT_FIELDS = {
    "ref",
    "title",
    "status",
    "priority",
    "assigned_to",
    "budget",
    "deadline",
    "created_at",
    "updated_at",
}


# ---------------------------------------------------------------------------
# Default pagination
# ---------------------------------------------------------------------------

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


# ---------------------------------------------------------------------------
# Request reference prefixes
# ---------------------------------------------------------------------------

REQUEST_TYPE_PREFIXES = {
    REQUEST_TYPE_ASSIGNMENT: "ASG",
    REQUEST_TYPE_CLASS: "CLS",
    REQUEST_TYPE_AI_REPORT: "AIR",
    REQUEST_TYPE_AI_REMOVAL: "AIR",
    REQUEST_TYPE_EXAM: "EXM",
    REQUEST_TYPE_INTERVIEW: "INT",
}