# analytics/services.py
"""
Analytics aggregation, one function set per user type - the sibling
of dashboard/services.py. Dashboard answers "what needs my attention
right now"; analytics answers "how are things trending". Both reuse
the same underlying services (orders, requests, payments, experts)
rather than querying the ORM from scratch wherever an existing
statistics() function already does the job.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func

from analytics.constants import (
    REQUEST_FUNNEL_DAYS,
    REVENUE_TREND_MONTHS,
    TOP_MATERIALS_LIMIT,
)
from exam_materials.exam_material import ExamMaterial
from experts.service import ExpertService
from extensions import db
from orders.order import Order
from orders.service import OrderService
from payments.constants import PAYMENT_STATUS_PAID
from payments.payment import Payment
from requests.request import ServiceRequest
from requests.service import get_request_statistics
from utils.exceptions import NotFoundError
from utils.timeseries import day_buckets, month_buckets


def _to_float(value):
    if value is None:
        return 0.0
    return float(value)


# ---------------------------------------------------------------------------
# ADMIN
#
# Response shapes match
# scholaredge-admin-frontend-code/src/services/analyticsService.ts.
# ---------------------------------------------------------------------------

def get_admin_statistics(range_arg=None):
    order_stats = OrderService.statistics()
    request_stats = get_request_statistics()

    total_requests = ServiceRequest.query.count()
    converted_requests = ServiceRequest.query.filter(
        ServiceRequest.converted_at.isnot(None)
    ).count()

    conversion_rate = (
        converted_requests / total_requests if total_requests else 0.0
    )

    avg_order_value = (
        order_stats["gross"] / order_stats["paid"]
        if order_stats["paid"]
        else 0.0
    )

    return {
        "gross_revenue": order_stats["gross"],
        "conversion_rate": round(conversion_rate, 4),
        "avg_order_value": round(avg_order_value, 2),
        "completed_jobs": request_stats["completed"],
    }


def _admin_revenue_trend(months):
    buckets = month_buckets(months)

    rows = (
        db.session.query(
            func.extract("year", Order.created_at).label("year"),
            func.extract("month", Order.created_at).label("month"),
            func.coalesce(func.sum(Order.amount), 0).label("amount"),
        )
        .filter(Order.status == "paid")
        .filter(Order.source_type == "request")
        .filter(
            Order.created_at
            >= datetime(*buckets[0][:2], 1, tzinfo=timezone.utc)
        )
        .group_by("year", "month")
        .all()
    )

    services_by_bucket = {
        (int(row.year), int(row.month)): _to_float(row.amount)
        for row in rows
    }

    return [
        {
            "month": label,
            "services": services_by_bucket.get((year, month), 0.0),
            # No licences model yet - see analytics/constants.py.
            "stealth": 0.0,
        }
        for year, month, label in buckets
    ]


def _admin_request_funnel(days):
    buckets = day_buckets(days)

    start = datetime.combine(
        buckets[0], datetime.min.time(), tzinfo=timezone.utc
    )

    # "Quoted" is approximated as requests currently in the "quoted"
    # status that were created on that day (ServiceRequest.quotes is
    # an append-only JSON log without per-entry indexing, so a precise
    # "quote issued on day X" count would need a dedicated quotes
    # table - out of scope here).
    quoted_rows = (
        db.session.query(
            func.date(ServiceRequest.created_at).label("day"),
            func.count(ServiceRequest.id).label("quoted"),
        )
        .filter(ServiceRequest.status == "quoted")
        .filter(ServiceRequest.created_at >= start)
        .group_by("day")
        .all()
    )

    quoted_by_day = {row.day: row.quoted for row in quoted_rows}

    converted_rows = (
        db.session.query(
            func.date(ServiceRequest.converted_at).label("day"),
            func.count(ServiceRequest.id).label("converted"),
        )
        .filter(ServiceRequest.converted_at.isnot(None))
        .filter(ServiceRequest.converted_at >= start)
        .group_by("day")
        .all()
    )

    converted_by_day = {row.day: row.converted for row in converted_rows}

    return [
        {
            "day": day.strftime("%a"),
            "quoted": quoted_by_day.get(day, 0),
            "converted": converted_by_day.get(day, 0),
        }
        for day in buckets
    ]


def _admin_top_materials():
    materials = (
        ExamMaterial.query.order_by(ExamMaterial.revenue.desc())
        .limit(TOP_MATERIALS_LIMIT)
        .all()
    )

    return [
        {
            "id": material.id,
            "title": material.title,
            "revenue": _to_float(material.revenue),
        }
        for material in materials
    ]


def get_admin_overview(range_arg=None):
    return {
        "revenueTrend": _admin_revenue_trend(REVENUE_TREND_MONTHS),
        "requestFunnel": _admin_request_funnel(REQUEST_FUNNEL_DAYS),
        "topMaterials": _admin_top_materials(),
    }


# ---------------------------------------------------------------------------
# CUSTOMER
# ---------------------------------------------------------------------------

def get_customer_statistics(user):
    paid_orders = Order.query.filter(
        Order.customer_id == user.id
    ).filter(Order.status == "paid")

    total_spend = (
        db.session.query(func.coalesce(func.sum(Order.amount), 0))
        .filter(Order.customer_id == user.id)
        .filter(Order.status == "paid")
        .scalar()
        or Decimal("0")
    )

    paid_count = paid_orders.count()

    avg_order_value = (
        _to_float(total_spend) / paid_count if paid_count else 0.0
    )

    return {
        "total_spend": _to_float(total_spend),
        "orders_count": paid_count,
        "avg_order_value": round(avg_order_value, 2),
    }


def get_customer_overview(user, months=None):
    buckets = month_buckets(months or REVENUE_TREND_MONTHS)

    rows = (
        db.session.query(
            func.extract("year", Order.created_at).label("year"),
            func.extract("month", Order.created_at).label("month"),
            func.coalesce(func.sum(Order.amount), 0).label("amount"),
        )
        .filter(Order.customer_id == user.id)
        .filter(Order.status == "paid")
        .filter(
            Order.created_at
            >= datetime(*buckets[0][:2], 1, tzinfo=timezone.utc)
        )
        .group_by("year", "month")
        .all()
    )

    spend_by_bucket = {
        (int(row.year), int(row.month)): _to_float(row.amount)
        for row in rows
    }

    return {
        "spendTrend": [
            {
                "month": label,
                "spend": spend_by_bucket.get((year, month), 0.0),
            }
            for year, month, label in buckets
        ]
    }


# ---------------------------------------------------------------------------
# EXPERT
# ---------------------------------------------------------------------------

def _get_expert_profile_or_raise(user):
    expert = user.expert

    if not expert:
        raise NotFoundError(
            "No expert profile exists for this account."
        )

    return expert


def get_expert_statistics(user):
    expert = _get_expert_profile_or_raise(user)

    completed = expert.completed_orders or 0

    avg_job_value = (
        _to_float(expert.total_earned) / completed if completed else 0.0
    )

    return {
        "total_earned": _to_float(expert.total_earned),
        "completed_jobs": completed,
        "avg_job_value": round(avg_job_value, 2),
        "rating": _to_float(expert.rating),
    }


def get_expert_overview(user, months=None):
    expert = _get_expert_profile_or_raise(user)

    buckets = month_buckets(months or REVENUE_TREND_MONTHS)

    rows = (
        db.session.query(
            func.extract("year", Payment.paid_at).label("year"),
            func.extract("month", Payment.paid_at).label("month"),
            func.coalesce(func.sum(Payment.amount), 0).label("amount"),
        )
        .filter(Payment.expert_id == str(expert.id))
        .filter(Payment.status == PAYMENT_STATUS_PAID)
        .filter(Payment.paid_at.isnot(None))
        .filter(
            Payment.paid_at
            >= datetime(*buckets[0][:2], 1, tzinfo=timezone.utc)
        )
        .group_by("year", "month")
        .all()
    )

    earnings_by_bucket = {
        (int(row.year), int(row.month)): _to_float(row.amount)
        for row in rows
    }

    return {
        "earningsTrend": [
            {
                "month": label,
                "earnings": earnings_by_bucket.get((year, month), 0.0),
            }
            for year, month, label in buckets
        ]
    }
