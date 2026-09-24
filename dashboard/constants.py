# dashboard/constants.py

# Number of trailing months shown on the admin revenue-series chart.
REVENUE_SERIES_MONTHS = 6

# Number of trailing days shown on the request-funnel chart.
REQUEST_FUNNEL_DAYS = 7

# How many rows the "needs attention" / "latest orders" lists hold.
NEEDS_ATTENTION_LIMIT = 6
LATEST_ORDERS_LIMIT = 6

# How many rows the customer/expert "recent activity" lists hold.
RECENT_ITEMS_LIMIT = 5

# Orders/requests still "in flight" (used for open-pipeline counts).
OPEN_REQUEST_STATUSES = (
    "new",
    "reviewing",
    "quoted",
    "in-progress",
    "delivered",
)

# NOTE: "ExamStealth" licences are referenced by the admin frontend
# (active_licenses / revenueSeries.stealth) but there is currently no
# licenses model in this backend. Those fields are intentionally
# reported as 0 rather than fabricated - see dashboard/services.py.
STEALTH_LICENSES_IMPLEMENTED = False
