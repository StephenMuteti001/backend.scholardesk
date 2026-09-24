# dashboard/services.py
"""
Dashboard aggregation, one function set per user type.

This module deliberately does *not* re-derive numbers that another
module's service layer already computes correctly - it calls into
orders.service.OrderService, requests.service, payments.service,
experts.service, customers.service and expert_applications.service
and reshapes their output for the dashboard's own response contract.
New raw queries are only written here for shapes that don't already
exist elsewhere (e.g. a monthly revenue-by-source-type breakdown).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, nullslast

from dashboard.constants import (
    LATEST_ORDERS_LIMIT,
    NEEDS_ATTENTION_LIMIT,
    OPEN_REQUEST_STATUSES,
    RECENT_ITEMS_LIMIT,
    REQUEST_FUNNEL_DAYS,
    REVENUE_SERIES_MONTHS,
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
# ---------------------------------------------------------------------------

def get_admin_statistics():
    """
    Powers the four admin dashboard stat cards.

    Matches DashboardStatistics in
    scholaredge-admin-frontend-code/src/services/dashboardService.ts.
    """

    order_stats = OrderService.statistics()

    open_requests = ServiceRequest.query.filter(
        ServiceRequest.status.in_(OPEN_REQUEST_STATUSES)
    ).count()

    material_sales = (
        db.session.query(
            func.coalesce(func.sum(ExamMaterial.revenue), 0)
        ).scalar()
        or Decimal("0")
    )

    return {
        "revenue": order_stats["gross"],
        "open_requests": open_requests,
        "material_sales": _to_float(material_sales),
        # No licences/"ExamStealth" model exists yet in this backend -
        # see dashboard/constants.py::STEALTH_LICENSES_IMPLEMENTED.
        "active_licenses": 0,
    }


def _admin_revenue_series(months):
    buckets = month_buckets(months)

    rows = (
        db.session.query(
            func.extract("year", Order.created_at).label("year"),
            func.extract("month", Order.created_at).label("month"),
            Order.source_type,
            func.coalesce(func.sum(Order.amount), 0).label("amount"),
        )
        .filter(Order.status == "paid")
        .filter(
            Order.created_at
            >= datetime(*buckets[0][:2], 1, tzinfo=timezone.utc)
        )
        .group_by("year", "month", Order.source_type)
        .all()
    )

    by_bucket = {
        (int(row.year), int(row.month)): {}
        for row in rows
    }

    for row in rows:
        key = (int(row.year), int(row.month))
        by_bucket.setdefault(key, {})[row.source_type] = _to_float(
            row.amount
        )

    series = []

    for year, month, label in buckets:
        amounts = by_bucket.get((year, month), {})

        series.append(
            {
                "month": label,
                "materials": amounts.get("material", 0.0),
                "services": amounts.get("request", 0.0),
                # See get_admin_statistics() note re: licences.
                "stealth": 0.0,
            }
        )

    return series


def _admin_request_funnel(days):
    buckets = day_buckets(days)

    start = datetime.combine(
        buckets[0], datetime.min.time(), tzinfo=timezone.utc
    )

    rows = (
        db.session.query(
            func.date(ServiceRequest.created_at).label("day"),
            func.count(ServiceRequest.id).label("requests"),
        )
        .filter(ServiceRequest.created_at >= start)
        .group_by("day")
        .all()
    )

    requests_by_day = {row.day: row.requests for row in rows}

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
            "requests": requests_by_day.get(day, 0),
            "converted": converted_by_day.get(day, 0),
        }
        for day in buckets
    ]


def _admin_needs_attention():
    requests = (
        ServiceRequest.query.filter(
            ServiceRequest.status.in_(["new", "reviewing"])
        )
        .order_by(ServiceRequest.created_at.desc())
        .limit(NEEDS_ATTENTION_LIMIT)
        .all()
    )

    return [
        {
            "id": request.id,
            "title": request.title,
            "typeLabel": request.type,
            "status": request.status,
            "customer": {
                "name": request.customer.name if request.customer else None,
                "email": (
                    request.customer.email if request.customer else None
                ),
            },
            "createdAt": (
                request.created_at.isoformat()
                if request.created_at
                else None
            ),
        }
        for request in requests
    ]


def _admin_latest_orders():
    orders = (
        Order.query.order_by(Order.created_at.desc())
        .limit(LATEST_ORDERS_LIMIT)
        .all()
    )

    return [
        {
            "id": order.id,
            "ref": order.reference,
            "materialTitle": order.item_title,
            "customer": {
                "name": order.customer.name if order.customer else None,
                "email": order.customer.email if order.customer else None,
            },
            "amount": _to_float(order.amount),
            "status": order.status,
            "createdAt": (
                order.created_at.isoformat() if order.created_at else None
            ),
        }
        for order in orders
    ]


def get_admin_overview(months=None):
    """
    Powers the admin dashboard's two charts + "needs attention" /
    "latest orders" lists.

    Matches DashboardOverview in dashboardService.ts.
    """

    return {
        "revenueSeries": _admin_revenue_series(
            months or REVENUE_SERIES_MONTHS
        ),
        "requestFunnel": _admin_request_funnel(REQUEST_FUNNEL_DAYS),
        "needsAttention": _admin_needs_attention(),
        "latestOrders": _admin_latest_orders(),
    }


# ---------------------------------------------------------------------------
# CUSTOMER
# ---------------------------------------------------------------------------

def get_customer_statistics(user):
    total_spend = (
        db.session.query(func.coalesce(func.sum(Order.amount), 0))
        .filter(Order.customer_id == user.id)
        .filter(Order.status == "paid")
        .scalar()
        or Decimal("0")
    )

    open_requests = ServiceRequest.query.filter(
        ServiceRequest.customer_id == user.id
    ).filter(
        ServiceRequest.status.in_(OPEN_REQUEST_STATUSES)
    ).count()

    completed_orders = Order.query.filter(
        Order.customer_id == user.id
    ).filter(Order.status == "paid").count()

    return {
        "total_spend": _to_float(total_spend),
        "open_requests": open_requests,
        "completed_orders": completed_orders,
    }


def get_customer_overview(user):
    recent_requests = (
        ServiceRequest.query.filter(
            ServiceRequest.customer_id == user.id
        )
        .order_by(ServiceRequest.updated_at.desc())
        .limit(RECENT_ITEMS_LIMIT)
        .all()
    )

    recent_orders = (
        Order.query.filter(Order.customer_id == user.id)
        .order_by(Order.created_at.desc())
        .limit(RECENT_ITEMS_LIMIT)
        .all()
    )

    return {
        "recentRequests": [
            {
                "id": request.id,
                "ref": request.ref,
                "title": request.title,
                "type": request.type,
                "status": request.status,
                "deadline": (
                    request.deadline.isoformat()
                    if request.deadline
                    else None
                ),
                "updatedAt": (
                    request.updated_at.isoformat()
                    if request.updated_at
                    else None
                ),
            }
            for request in recent_requests
        ],
        "recentOrders": [
            {
                "id": order.id,
                "ref": order.reference,
                "title": order.item_title,
                "amount": _to_float(order.amount),
                "status": order.status,
                "createdAt": (
                    order.created_at.isoformat()
                    if order.created_at
                    else None
                ),
            }
            for order in recent_orders
        ],
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

    active_jobs = ServiceRequest.query.filter(
        ServiceRequest.assigned_to == user.id
    ).filter(
        ServiceRequest.status.in_(["in-progress", "quoted"])
    ).count()

    pending_payout = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.expert_id == str(expert.id))
        .filter(Payment.status != PAYMENT_STATUS_PAID)
        .scalar()
        or Decimal("0")
    )

    return {
        "active_jobs": active_jobs,
        "completed_orders": expert.completed_orders or 0,
        "total_earned": _to_float(expert.total_earned),
        "pending_payout": _to_float(pending_payout),
        "rating": _to_float(expert.rating),
    }


def get_expert_overview(user):
    expert = _get_expert_profile_or_raise(user)

    assigned_requests = (
        ServiceRequest.query.filter(
            ServiceRequest.assigned_to == user.id
        )
        .order_by(nullslast(ServiceRequest.deadline.asc()))
        .limit(RECENT_ITEMS_LIMIT)
        .all()
    )

    recent_payments = (
        Payment.query.filter(Payment.expert_id == str(expert.id))
        .order_by(Payment.created_at.desc())
        .limit(RECENT_ITEMS_LIMIT)
        .all()
    )

    return {
        "upcomingDeadlines": [
            {
                "id": request.id,
                "ref": request.ref,
                "title": request.title,
                "status": request.status,
                "deadline": (
                    request.deadline.isoformat()
                    if request.deadline
                    else None
                ),
            }
            for request in assigned_requests
        ],
        "recentPayments": [
            {
                "id": payment.id,
                "amount": _to_float(payment.amount),
                "status": payment.status,
                "periodStart": payment.period_start.isoformat(),
                "periodEnd": payment.period_end.isoformat(),
                "paidAt": (
                    payment.paid_at.isoformat()
                    if payment.paid_at
                    else None
                ),
            }
            for payment in recent_payments
        ],
    }
