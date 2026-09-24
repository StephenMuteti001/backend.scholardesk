# utils/timeseries.py
"""
Small date-bucketing helpers shared by dashboard/services.py and
analytics/services.py, so both modules build their monthly/daily
chart series the same way instead of each rolling their own.
"""

from datetime import datetime, timedelta, timezone


def month_buckets(count):
    """
    Return `count` (year, month, label) tuples for the trailing
    months ending with the current month, oldest first.

    label is a short "Jan", "Feb", ... form for chart x-axes.
    """
    now = datetime.now(timezone.utc)

    buckets = []

    year, month = now.year, now.month

    for _ in range(count):
        buckets.append((year, month))

        month -= 1

        if month == 0:
            month = 12
            year -= 1

    buckets.reverse()

    return [
        (year, month, datetime(year, month, 1).strftime("%b"))
        for year, month in buckets
    ]


def day_buckets(count):
    """
    Return `count` date objects for the trailing days ending today,
    oldest first.
    """
    today = datetime.now(timezone.utc).date()

    return [
        today - timedelta(days=offset)
        for offset in range(count - 1, -1, -1)
    ]
