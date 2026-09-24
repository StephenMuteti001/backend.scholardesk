# requests/service.py

import csv
import io
import uuid
from datetime import datetime, timezone

from sqlalchemy import asc, desc, or_, func

from extensions import db
from utils.exceptions import (
    ConflictError,
    NotFoundError,
    ServiceError,
    ValidationError,
)
from utils.transaction import transaction

from requests.request import ServiceRequest
from requests.constants import (
    REQUEST_STATUS_CANCELLED,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_DELIVERED,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_NEW,
    REQUEST_STATUS_QUOTED,
    REQUEST_STATUS_REVIEWING,
    REQUEST_TYPE_PREFIXES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _get_request_or_404(request_id):
    request = db.session.get(
        ServiceRequest,
        request_id,
    )

    if not request:
        raise NotFoundError(
            "Request not found.",
            {"request_id": request_id},
        )

    return request


def _generate_reference(request_type):
    prefix = REQUEST_TYPE_PREFIXES.get(
        request_type,
        "REQ",
    )

    date_part = _now().strftime("%Y%m%d")

    count = (
        db.session.query(func.count(ServiceRequest.id))
        .filter(
            ServiceRequest.ref.like(
                f"{prefix}-{date_part}-%"
            )
        )
        .scalar()
        or 0
    )

    return f"{prefix}-{date_part}-{count + 1:04d}"


def _user_name(user):
    if not user:
        return None

    # Adjust this if your User model uses another display field.
    if getattr(user, "name", None):
        return user.name

    first = getattr(user, "first_name", "") or ""
    last = getattr(user, "last_name", "") or ""

    full_name = f"{first} {last}".strip()

    if full_name:
        return full_name

    return getattr(user, "email", None)


def _quote_dict(quote):
    """
    camelCase view of a raw quote entry, matching the shape
    customer_orders/service.py::_quote_dict() already exposes to the
    customer app - kept consistent across both APIs rather than
    leaving this one as raw snake_case.
    """
    if not quote:
        return None

    return {
        "amount": quote.get("amount"),
        "currency": quote.get("currency"),
        "issuedAt": quote.get("issued_at"),
        "expiresAt": quote.get("expires_at"),
        "deliverySchedule": quote.get("delivery_schedule"),
        "notes": quote.get("notes"),
        "issuedBy": quote.get("issued_by"),
        "issuedByRole": quote.get("issued_by_role", "admin"),
        "acceptedAt": quote.get("accepted_at"),
        "rejectedAt": quote.get("rejected_at"),
    }


def serialize_request(request):
    customer = request.customer
    assigned_user = request.assigned_user

    return {
        "id": str(request.id),
        "ref": request.ref,

        "title": request.title,
        "subject": request.subject,
        "description": request.description,

        "type": request.type,
        "status": request.status,
        "priority": request.priority,

        "customer": {
            "id": customer.id,
            "name": _user_name(customer),
            "email": getattr(customer, "email", None),
            "country": getattr(customer, "country", None),
        } if customer else None,

        "assignedTo": _user_name(assigned_user),
        "assignedToId": request.assigned_to,

        "budget": (
            float(request.budget)
            if request.budget is not None
            else None
        ),

        "currency": request.currency,

        "quotes": [_quote_dict(q) for q in (request.quotes or [])],
        "tags": request.tags or [],

        "deadline": (
            request.deadline.isoformat()
            if request.deadline
            else None
        ),

        "orderId": str(request.order_id) if request.order_id else None,

        "convertedAt": (
            request.converted_at.isoformat()
            if request.converted_at
            else None
        ),

        "createdAt": (
            request.created_at.isoformat()
            if request.created_at
            else None
        ),

        "updatedAt": (
            request.updated_at.isoformat()
            if request.updated_at
            else None
        ),

        "completedAt": (
            request.completed_at.isoformat()
            if request.completed_at
            else None
        ),

        "cancelledAt": (
            request.cancelled_at.isoformat()
            if request.cancelled_at
            else None
        ),

        "lastReminderAt": (
            request.last_reminder_at.isoformat()
            if request.last_reminder_at
            else None
        ),

        "metadata": request.metadata_json or {},
    }


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

def list_requests(
    *,
    page=1,
    per_page=20,
    search=None,
    types=None,
    type=None,
    status=None,
    priority=None,
    assigned_to=None,
    sort_by="updated_at",
    direction="desc",
):
    query = ServiceRequest.query

    if types:
        query = query.filter(
            ServiceRequest.type.in_(types)
        )

    if type:
        query = query.filter(
            ServiceRequest.type == type
        )

    if status:
        query = query.filter(
            ServiceRequest.status == status
        )

    if priority:
        query = query.filter(
            ServiceRequest.priority == priority
        )

    if assigned_to:
        query = query.filter(
            ServiceRequest.assigned_to == assigned_to
        )

    if search:
        pattern = f"%{search}%"

        query = query.filter(
            or_(
                ServiceRequest.ref.ilike(pattern),
                ServiceRequest.title.ilike(pattern),
                ServiceRequest.subject.ilike(pattern),
                ServiceRequest.description.ilike(pattern),
            )
        )

    sort_column_map = {
        "ref": ServiceRequest.ref,
        "title": ServiceRequest.title,
        "status": ServiceRequest.status,
        "priority": ServiceRequest.priority,
        "assigned_to": ServiceRequest.assigned_to,
        "budget": ServiceRequest.budget,
        "deadline": ServiceRequest.deadline,
        "created_at": ServiceRequest.created_at,
        "updated_at": ServiceRequest.updated_at,
    }

    sort_column = sort_column_map.get(
        sort_by,
        ServiceRequest.updated_at,
    )

    query = query.order_by(
        desc(sort_column)
        if direction == "desc"
        else asc(sort_column)
    )

    pagination = query.paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    return {
        "items": [
            serialize_request(item)
            for item in pagination.items
        ],
        "pagination": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "pages": pagination.pages,
            "total": pagination.total,
        },
    }


# ---------------------------------------------------------------------------
# GET ONE
# ---------------------------------------------------------------------------

def get_request(request_id):
    request = _get_request_or_404(request_id)

    return serialize_request(request)


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

def create_request(payload):
    customer_id = payload["customer_id"]

    # Assumes User model is available.
    from users.user import User

    customer = db.session.get(
        User,
        customer_id,
    )

    if not customer:
        raise NotFoundError(
            "Customer not found.",
            {"customer_id": customer_id},
        )

    reference = _generate_reference(
        payload["type"]
    )

    request = ServiceRequest(
        ref=reference,
        type=payload["type"],
        title=payload["title"],
        subject=payload.get("subject"),
        description=payload.get("description"),
        customer_id=customer_id,
        priority=payload.get("priority", "normal"),
        budget=payload.get("budget"),
        deadline=payload.get("deadline"),
        tags=payload.get("tags", []),
        metadata_json=payload.get("metadata", {}),
        status=REQUEST_STATUS_NEW,
    )

    with transaction():
        db.session.add(request)
        db.session.flush()

    return serialize_request(request)


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

def update_request(request_id, payload):
    request = _get_request_or_404(request_id)

    old_status = request.status

    if "status" in payload:
        next_status = payload["status"]

        # Prevent reopening completed/cancelled requests accidentally.
        if old_status in {
            REQUEST_STATUS_COMPLETED,
            REQUEST_STATUS_CANCELLED,
        } and next_status not in {
            old_status,
        }:
            raise ConflictError(
                "A completed or cancelled request cannot be reopened "
                "through this endpoint."
            )

    if "title" in payload:
        request.title = payload["title"]

    if "subject" in payload:
        request.subject = payload["subject"]

    if "description" in payload:
        request.description = payload["description"]

    if "status" in payload:
        request.status = payload["status"]

        if payload["status"] == REQUEST_STATUS_COMPLETED:
            request.completed_at = _now()

        elif payload["status"] == REQUEST_STATUS_CANCELLED:
            request.cancelled_at = _now()

    if "priority" in payload:
        request.priority = payload["priority"]

    if "assigned_to" in payload:
        if payload["assigned_to"]:
            from users.user import User

            user = db.session.get(
                User,
                payload["assigned_to"],
            )

            if not user:
                raise NotFoundError(
                    "Assigned user not found."
                )

        request.assigned_to = payload["assigned_to"]

    if "deadline" in payload:
        request.deadline = payload["deadline"]

    if "budget" in payload:
        request.budget = payload["budget"]

    if "tags" in payload:
        request.tags = payload["tags"]

    with transaction():
        db.session.add(request)
        db.session.flush()

    return serialize_request(request)

# ---------------------------------------------------------------------------
# BULK UPDATE
# ---------------------------------------------------------------------------

def bulk_update_requests(
    ids,
    payload,
    actor_id=None,
):
    requests = (
        ServiceRequest.query
        .filter(ServiceRequest.id.in_(ids))
        .all()
    )

    found_ids = {request.id for request in requests}

    missing = [
        request_id
        for request_id in ids
        if request_id not in found_ids
    ]

    if missing:
        raise NotFoundError(
            "One or more requests were not found.",
            {"missing_ids": missing},
        )

    for request in requests:
        if "status" in payload:
            next_status = payload["status"]

            if request.status in {
                REQUEST_STATUS_COMPLETED,
                REQUEST_STATUS_CANCELLED,
            }:
                raise ConflictError(
                    f"Request {request.ref} cannot be reopened."
                )

            request.status = next_status

            if next_status == REQUEST_STATUS_COMPLETED:
                request.completed_at = _now()

            if next_status == REQUEST_STATUS_CANCELLED:
                request.cancelled_at = _now()

        if "priority" in payload:
            request.priority = payload["priority"]

        if "assigned_to" in payload:
            request.assigned_to = payload["assigned_to"]

        if "deadline" in payload:
            request.deadline = payload["deadline"]

        if "budget" in payload:
            request.budget = payload["budget"]

        if "tags" in payload:
            request.tags = payload["tags"]

    with transaction():
        for request in requests:
            db.session.add(request)

        db.session.flush()

    return {
        "count": len(requests)
    }


# ---------------------------------------------------------------------------
# DELETE ONE
# ---------------------------------------------------------------------------

def delete_request(request_id):
    request = _get_request_or_404(request_id)

    # Do not permit deletion of a request that has already become an order.
    if request.order_id:
        raise ConflictError(
            "A request that has been converted to an order cannot be deleted.",
            {
                "request_id": request.id,
                "order_id": request.order_id,
            },
        )

    with transaction():
        db.session.delete(request)

    return None


# ---------------------------------------------------------------------------
# BULK DELETE
# ---------------------------------------------------------------------------

def bulk_delete_requests(ids):
    requests = (
        ServiceRequest.query
        .filter(ServiceRequest.id.in_(ids))
        .all()
    )

    found_ids = {request.id for request in requests}

    missing = [
        request_id
        for request_id in ids
        if request_id not in found_ids
    ]

    if missing:
        raise NotFoundError(
            "One or more requests were not found.",
            {"missing_ids": missing},
        )

    converted = [
        request.ref
        for request in requests
        if request.order_id
    ]

    if converted:
        raise ConflictError(
            "Converted requests cannot be deleted.",
            {"references": converted},
        )

    with transaction():
        for request in requests:
            db.session.delete(request)

    return {
        "count": len(requests)
    }

# ---------------------------------------------------------------------------
# STATISTICS
# ---------------------------------------------------------------------------

def get_request_statistics(types=None):
    query = ServiceRequest.query

    if types:
        query = query.filter(
            ServiceRequest.type.in_(types)
        )

    total = query.count()

    awaiting_triage = query.filter(
        ServiceRequest.status.in_([
            REQUEST_STATUS_NEW,
        ])
    ).count()

    open_pipeline = (
        query
        .with_entities(
            func.coalesce(
                func.sum(ServiceRequest.budget),
                0,
            )
        )
        .filter(
            ServiceRequest.status.in_([
                REQUEST_STATUS_NEW,
                REQUEST_STATUS_REVIEWING,
                REQUEST_STATUS_QUOTED,
                REQUEST_STATUS_IN_PROGRESS,
                REQUEST_STATUS_DELIVERED,
            ])
        )
        .scalar()
        or 0
    )

    completed = query.filter(
        ServiceRequest.status == REQUEST_STATUS_COMPLETED
    ).count()

    return {
        "total": total,
        "awaiting_triage": awaiting_triage,
        "open_pipeline": float(open_pipeline),
        "completed": completed,
    }


# ---------------------------------------------------------------------------
# QUOTES (admin) - counterpart to customer_orders' quote/accept flow
# ---------------------------------------------------------------------------

def issue_quote(request_id, admin_user, amount, currency, expires_at=None,
                 delivery_schedule=None, notes=None):
    """
    Append a new quote to a request and move it to "quoted".

    Quote shape (JSON, stored newest-last in ServiceRequest.quotes):
        {
          "amount": 148.0, "currency": "USD",
          "issued_at": "...", "expires_at": "..." | None,
          "delivery_schedule": "...", "notes": "..." | None,
          "issued_by": <admin user id>, "accepted_at": None,
        }

    Superseding an existing un-accepted quote is allowed (re-quoting);
    superseding an already-accepted quote is not, once payment has
    started that request must be handled as an order instead.
    """
    request = _get_request_or_404(request_id)

    if request.order_id:
        raise ConflictError(
            "This request has already been converted to an order."
        )

    if request.status not in (
        REQUEST_STATUS_NEW,
        REQUEST_STATUS_REVIEWING,
        REQUEST_STATUS_QUOTED,
    ):
        raise ConflictError(
            "Only new, reviewing, or already-quoted requests can "
            "receive a quote."
        )

    existing_quotes = list(request.quotes or [])

    if existing_quotes and existing_quotes[-1].get("accepted_at"):
        raise ConflictError(
            "The customer has already accepted a quote for this request."
        )

    quote = {
        "amount": float(amount),
        "currency": currency,
        "issued_at": _now().isoformat(),
        "expires_at": expires_at,
        "delivery_schedule": delivery_schedule,
        "notes": notes,
        "issued_by": admin_user.id,
        "issued_by_role": "admin",
        "accepted_at": None,
    }

    with transaction():
        existing_quotes.append(quote)
        request.quotes = existing_quotes
        request.status = REQUEST_STATUS_QUOTED
        request.budget = amount
        request.currency = currency

        activity = list(request.activity_log or [])
        activity.append(
            {
                "id": str(uuid.uuid4()),
                "at": _now().isoformat(),
                "actor": "support",
                "title": "Quote sent",
                "detail": f"{currency} {amount} - {delivery_schedule or ''}".strip(" -"),
            }
        )
        request.activity_log = activity

        db.session.flush()

    if request.customer:
        from users.mailer_service import send_quote_issued_email

        send_quote_issued_email(request.customer, request, quote)

    return request


# ---------------------------------------------------------------------------
# SEND REMINDER
# ---------------------------------------------------------------------------

def send_request_reminder(request_id):
    request = _get_request_or_404(request_id)

    if not request.customer:
        raise ConflictError(
            "Request has no customer."
        )

    customer_email = getattr(
        request.customer,
        "email",
        None,
    )

    if not customer_email:
        raise ConflictError(
            "Customer does not have an email address."
        )

    # Reuses the same notification template/sender as every other
    # transactional email in the app (users/mailer_service.py) rather
    # than calling utils/mailer.py directly with a mismatched
    # signature (send_email() takes `html`, not `body`).
    from users.mailer_service import send_notification_email

    send_notification_email(
        request.customer,
        message=(
            f"This is a follow-up regarding your request {request.ref}: "
            f"{request.title}. Please review your account for the "
            "latest update."
        ),
        subject=f"Update regarding request {request.ref}",
    )

    request.last_reminder_at = _now()

    with transaction():
        db.session.add(request)
        db.session.flush()


# ---------------------------------------------------------------------------
# EXPORT
# ---------------------------------------------------------------------------

def export_requests(**params):
    result = list_requests(**params)

    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([
        "Reference",
        "Title",
        "Type",
        "Customer",
        "Customer Email",
        "Status",
        "Priority",
        "Owner",
        "Budget",
        "Deadline",
        "Created",
        "Updated",
    ])

    for request in result["items"]:
        customer = request["customer"] or {}

        writer.writerow([
            request["ref"],
            request["title"],
            request["type"],
            customer.get("name"),
            customer.get("email"),
            request["status"],
            request["priority"],
            request["assignedTo"],
            request["budget"],
            request["deadline"],
            request["createdAt"],
            request["updatedAt"],
        ])

    return output.getvalue()