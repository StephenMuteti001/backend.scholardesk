# customer_orders/service.py

import uuid
from datetime import datetime, timezone

from sqlalchemy import or_

from customer_orders.constants import (
    DEFAULT_CURRENCY,
    DEFAULT_REQUEST_TYPE,
    FREELY_EDITABLE_STAGES,
    NON_CANCELLABLE_STAGES,
    ORDER_STATUS_TO_PAYMENT_STATUS,
    PAYMENT_PAID,
    REQUEST_STATUS_TO_STAGE,
    STAGE_AWAITING_PAYMENT,
    STAGE_CANCELLED,
    STAGE_MATCHING_WRITER,
    STAGE_QUOTE_SENT,
    STATUS_TO_STAGES,
    UPLOAD_SUBDIR,
)
from extensions import db
from orders.order import Order
from orders.service import OrderService
from requests.constants import (
    REQUEST_STATUS_CANCELLED,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_QUOTED,
    REQUEST_STATUS_REVIEWING,
)
from requests.request import ServiceRequest
from requests.schemas import _parse_datetime
from requests.service import _generate_reference
from submissions.submission import Submission, SubmissionStatus
from support_chat.support_chat import SupportThread
from users.user import User
from utils.exceptions import ConflictError, NotFoundError, ValidationError
from utils.transaction import transaction
from utils.uploads import save_uploaded_files


# ---------------------------------------------------------------------------
# Internal lookups
# ---------------------------------------------------------------------------

def _get_owned_request_or_raise(order_id, user):
    """
    `order_id` is always a ServiceRequest.id - see the module docstring
    in customer_orders/constants.py for why that id is the one the
    customer uses for the whole lifetime of an order.
    """
    request = db.session.get(ServiceRequest, order_id)

    if not request or request.customer_id != user.id:
        raise NotFoundError(
            "Order not found.",
            {"order_id": str(order_id)},
        )

    return request


def _latest_quote(request):
    quotes = request.quotes or []
    return quotes[-1] if quotes else None


def _log_activity(subject, actor, title, detail=None):
    entries = list(subject.activity_log or [])

    entries.append(
        {
            "id": str(uuid.uuid4()),
            "at": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "title": title,
            "detail": detail,
        }
    )

    subject.activity_log = entries


# ---------------------------------------------------------------------------
# Serialization - the single place a ServiceRequest (+ its Order, if
# converted) becomes the frontend's unified `Order` shape.
# ---------------------------------------------------------------------------

def _stage_for(request, order):
    if order and order.fulfillment_stage:
        return order.fulfillment_stage

    if request.status == REQUEST_STATUS_QUOTED:
        quote = _latest_quote(request)

        if quote and quote.get("accepted_at"):
            return STAGE_AWAITING_PAYMENT

        return STAGE_QUOTE_SENT

    return REQUEST_STATUS_TO_STAGE.get(request.status, STAGE_MATCHING_WRITER)


def _payment_status_for(order):
    if not order:
        return "unpaid"

    return ORDER_STATUS_TO_PAYMENT_STATUS.get(order.status, "unpaid")


def _quote_dict(quote):
    if not quote:
        return None

    return {
        "amount": quote.get("amount"),
        "currency": quote.get("currency"),
        "issuedAt": quote.get("issued_at"),
        "expiresAt": quote.get("expires_at"),
        "deliverySchedule": quote.get("delivery_schedule"),
        "notes": quote.get("notes"),
        "acceptedAt": quote.get("accepted_at"),
        "rejectedAt": quote.get("rejected_at"),
        "issuedByRole": quote.get("issued_by_role", "admin"),
    }


def _chat_id_for(request):
    thread = (
        SupportThread.query.filter(
            SupportThread.order_reference == request.ref
        )
        .order_by(SupportThread.updated_at.desc())
        .first()
    )

    return str(thread.id) if thread else None


def _submissions_for(order):
    if not order:
        return []

    submissions = (
        Submission.query.filter(Submission.order_id == order.id)
        # Work an expert has delivered is not customer-visible until it
        # clears internal integrity review - see
        # submissions/submission.py::SubmissionStatus.PENDING_REVIEW.
        .filter(Submission.status != SubmissionStatus.PENDING_REVIEW)
        .order_by(Submission.version.asc())
        .all()
    )

    return [submission.to_dict() for submission in submissions]


def serialize_order(request):
    order = (
        db.session.get(Order, request.order_id) if request.order_id else None
    )

    metadata = request.metadata_json or {}
    quote = _latest_quote(request)

    activity = list(request.activity_log or []) + (
        list(order.activity_log or []) if order else []
    )

    amount = None

    if order:
        amount = float(order.amount)
    elif quote:
        amount = quote.get("amount")
    elif request.budget is not None:
        amount = float(request.budget)

    return {
        "id": str(request.id),
        "reference": request.ref,
        "title": request.title,
        "subject": request.subject,
        "assignmentType": metadata.get("assignment_type"),
        "wordCount": metadata.get("word_count"),
        "pages": (
            max(1, round(metadata["word_count"] / 275))
            if metadata.get("word_count")
            else None
        ),
        "citationStyle": metadata.get("citation_style"),
        "deadline": (
            request.deadline.isoformat() if request.deadline else None
        ),
        "instructions": request.description,
        "files": request.files or [],
        "stage": _stage_for(request, order),
        "paymentStatus": _payment_status_for(order),
        "amount": amount,
        "currency": (order.currency if order else request.currency)
        or DEFAULT_CURRENCY,
        "quote": _quote_dict(quote),
        "chatId": _chat_id_for(request),
        "submissions": _submissions_for(order),
        "activity": activity,
        "createdAt": (
            request.created_at.isoformat() if request.created_at else None
        ),
        "updatedAt": (
            (order.updated_at if order else request.updated_at).isoformat()
            if (order.updated_at if order else request.updated_at)
            else None
        ),
    }


# ---------------------------------------------------------------------------
# LIST / GET
# ---------------------------------------------------------------------------

def list_orders(user, page=1, per_page=20, stage=None, status=None,
                search=None):
    query = ServiceRequest.query.filter(
        ServiceRequest.customer_id == user.id
    )

    if search:
        term = f"%{search}%"
        query = query.filter(
            or_(
                ServiceRequest.title.ilike(term),
                ServiceRequest.ref.ilike(term),
            )
        )

    query = query.order_by(ServiceRequest.created_at.desc())

    # Stage filtering happens after serialization since "stage" is a
    # derived value spanning two tables/columns, not a single indexed
    # column we can filter on in SQL.
    all_requests = query.all()

    serialized = [serialize_order(request) for request in all_requests]

    # Tab counts are always computed over the whole (searched) set, not
    # the filtered slice - the portal needs every tab's badge even
    # while one tab is selected.
    counts = {
        key: sum(
            1 for order in serialized if order["stage"] in stages
        )
        for key, stages in STATUS_TO_STAGES.items()
    }

    if stage:
        serialized = [
            order for order in serialized if order["stage"] == stage
        ]

    if status:
        stages = STATUS_TO_STAGES[status]

        serialized = [
            order for order in serialized if order["stage"] in stages
        ]

    total = len(serialized)
    pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    page_items = serialized[start:start + per_page]

    return {
        "items": page_items,
        "counts": counts,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": pages,
            "has_more": page < pages,
        },
    }


def get_order(order_id, user):
    request = _get_owned_request_or_raise(order_id, user)
    return serialize_order(request)


# ---------------------------------------------------------------------------
# CREATE (quote request)
# ---------------------------------------------------------------------------

def create_quote_request(user, fields, uploaded_files=None):
    reference = _generate_reference(
        fields.get("request_type") or DEFAULT_REQUEST_TYPE
    )

    deadline = _parse_datetime(fields.get("deadline"), "deadline")

    file_records = []

    if uploaded_files:
        saved_paths = save_uploaded_files(
            uploaded_files,
            UPLOAD_SUBDIR.format(user_id=user.id, request_id=reference),
        )

        for path, upload in zip(saved_paths, uploaded_files):
            if not path:
                continue

            file_records.append(
                {
                    "id": str(uuid.uuid4()),
                    "name": upload.filename,
                    "size": getattr(upload, "content_length", None) or 0,
                    "url": path,
                }
            )
    else:
        # The current frontend only sends the *names* of attachments
        # (see docs/API.md / RequestForm.tsx), no file bytes yet - keep
        # them as metadata-only entries until real upload is wired up.
        file_records = [
            {"id": str(uuid.uuid4()), "name": name, "size": 0, "url": None}
            for name in (fields.get("file_names") or [])
        ]

    with transaction():
        request = ServiceRequest(
            ref=reference,
            type=fields.get("request_type") or DEFAULT_REQUEST_TYPE,
            title=fields["title"],
            subject=fields.get("subject"),
            description=fields.get("instructions"),
            customer_id=user.id,
            priority="normal",
            deadline=deadline,
            files=file_records,
            metadata_json={
                "full_name": fields.get("full_name"),
                "email": fields.get("email"),
                "assignment_type": fields.get("assignment_type"),
                "word_count": fields.get("word_count"),
                "citation_style": fields.get("citation_style"),
            },
        )

        _log_activity(
            request,
            actor="customer",
            title="Quote requested",
            detail=fields["title"],
        )

        db.session.add(request)
        db.session.flush()

        return request


# ---------------------------------------------------------------------------
# UPDATE (edit brief)
# ---------------------------------------------------------------------------

def update_order(order_id, user, fields):
    request = _get_owned_request_or_raise(order_id, user)

    stage = _stage_for(
        request,
        db.session.get(Order, request.order_id) if request.order_id else None,
    )

    if stage in NON_CANCELLABLE_STAGES:
        raise ConflictError(
            "This order can no longer be edited."
        )

    freely_editable = stage in FREELY_EDITABLE_STAGES

    with transaction():
        if "title" in fields:
            request.title = fields["title"]

        if "subject" in fields:
            request.subject = fields["subject"]

        if "deadline" in fields:
            request.deadline = _parse_datetime(
                fields["deadline"], "deadline"
            )

        if "instructions" in fields:
            request.description = fields["instructions"]

        metadata = dict(request.metadata_json or {})

        if "assignment_type" in fields:
            metadata["assignment_type"] = fields["assignment_type"]

        if "word_count" in fields:
            metadata["word_count"] = fields["word_count"]

        if "citation_style" in fields:
            metadata["citation_style"] = fields["citation_style"]

        request.metadata_json = metadata

        if freely_editable:
            _log_activity(
                request, actor="customer", title="Brief updated"
            )
        else:
            _log_activity(
                request,
                actor="customer",
                title="Order details updated",
                detail=(
                    "Support will review these changes for scope impact."
                ),
            )

        db.session.flush()

        return request


# ---------------------------------------------------------------------------
# QUOTE ACCEPT
# ---------------------------------------------------------------------------

def accept_quote(order_id, user):
    request = _get_owned_request_or_raise(order_id, user)

    if request.status != REQUEST_STATUS_QUOTED:
        raise ConflictError(
            "There is no pending quote to accept for this order."
        )

    quotes = list(request.quotes or [])

    if not quotes:
        raise ConflictError("There is no pending quote to accept.")

    latest = quotes[-1]

    if latest.get("accepted_at"):
        raise ConflictError("This quote has already been accepted.")

    if latest.get("issued_by_role") == "customer":
        raise ConflictError(
            "Waiting on the support team to respond to your counter-offer."
        )

    with transaction():
        latest["accepted_at"] = datetime.now(timezone.utc).isoformat()
        request.quotes = quotes

        _log_activity(
            request, actor="customer", title="Quote accepted"
        )

        # "A request whose quote has been agreed/accepted becomes an
        # order" - this is a direct product requirement, so the real
        # Order row is created right here rather than waiting on
        # payment (see OrderService.create_unpaid_from_request).
        order = OrderService.create_unpaid_from_request(
            request_obj=request,
            customer_id=user.id,
            amount=latest.get("amount"),
            currency=latest.get("currency") or request.currency or DEFAULT_CURRENCY,
        )

        request.order_id = order.id
        request.converted_at = datetime.now(timezone.utc)

        db.session.flush()

    from users.mailer_service import send_invoice_email

    send_invoice_email(user, order, latest)

    return request


# ---------------------------------------------------------------------------
# QUOTE REJECT / COUNTER
# ---------------------------------------------------------------------------

def reject_quote(order_id, user):
    """
    Firmly declines the latest quote - distinct from counter_quote()
    below, which proposes a different number instead. Puts the
    request back to "reviewing" so it's clear to the support team
    that a new quote is needed, not just a tweaked one.
    """
    request = _get_owned_request_or_raise(order_id, user)

    if request.status != REQUEST_STATUS_QUOTED:
        raise ConflictError(
            "There is no pending quote to reject for this order."
        )

    quotes = list(request.quotes or [])

    if not quotes or quotes[-1].get("accepted_at"):
        raise ConflictError("There is no pending quote to reject.")

    with transaction():
        quotes[-1]["rejected_at"] = datetime.now(timezone.utc).isoformat()
        request.quotes = quotes
        request.status = REQUEST_STATUS_REVIEWING

        _log_activity(
            request, actor="customer", title="Quote declined"
        )

        db.session.flush()

    from users.mailer_service import send_internal_alert

    send_internal_alert(
        subject=f"Quote declined - {request.title}",
        message=(
            f"{user.full_name} declined the quote for "
            f"\"{request.title}\" ({request.ref}). A new quote is needed."
        ),
        action_path="/requests",
    )

    return request


def counter_quote(order_id, user, amount, notes=None):
    """
    Client proposes a different amount instead of accepting or
    rejecting outright. Appends a new quote entry (issued_by_role
    "customer") to the same history issue_quote() writes to, so the
    support team can respond with requests.service.issue_quote() the
    same way they would to their own quote. Deliberately minimal -
    per product direction, the back-and-forth detail (why this
    number, etc.) happens over chat/email, not structured fields
    here.
    """
    request = _get_owned_request_or_raise(order_id, user)

    if request.status != REQUEST_STATUS_QUOTED:
        raise ConflictError(
            "There is no quote to counter for this order."
        )

    quotes = list(request.quotes or [])

    if not quotes or quotes[-1].get("accepted_at"):
        raise ConflictError("There is no pending quote to counter.")

    if amount is None or float(amount) <= 0:
        raise ValidationError("Counter-offer amount must be greater than zero.")

    counter = {
        "amount": float(amount),
        "currency": quotes[-1].get("currency") or request.currency or DEFAULT_CURRENCY,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": None,
        "delivery_schedule": quotes[-1].get("delivery_schedule"),
        "notes": notes,
        "issued_by": user.id,
        "issued_by_role": "customer",
        "accepted_at": None,
    }

    with transaction():
        quotes.append(counter)
        request.quotes = quotes

        _log_activity(
            request,
            actor="customer",
            title="Customer proposed a counter-offer",
            detail=f"{counter['currency']} {counter['amount']}",
        )

        db.session.flush()

    from users.mailer_service import send_internal_alert

    send_internal_alert(
        subject=f"Counter-offer received - {request.title}",
        message=(
            f"{user.full_name} proposed {counter['currency']} "
            f"{counter['amount']} for \"{request.title}\" ({request.ref})."
            + (f" Note: {notes}" if notes else "")
        ),
        action_path="/requests",
    )

    return request


# ---------------------------------------------------------------------------
# PAYMENT -> conversion to a real Order
# ---------------------------------------------------------------------------

def pay_order(order_id, user, gateway, payment_reference=None):
    request = _get_owned_request_or_raise(order_id, user)

    if not request.order_id:
        raise ConflictError(
            "You must accept a quote before paying for this order."
        )

    order = OrderService.get_order(request.order_id)

    # NOTE: this records the payment as already-settled. No real
    # payment-gateway integration (Stripe/Paystack/etc.) exists
    # anywhere in this codebase yet - wire actual charge creation +
    # webhook confirmation in here before relying on this in
    # production. See config.py for the (currently unused) Paystack
    # keys.
    #
    # The order itself was already created at quote-acceptance time
    # (see accept_quote() above) - this just confirms payment against
    # it via OrderService.mark_paid(), which also advances
    # fulfillment_stage to "matching_writer".
    OrderService.mark_paid(
        order,
        gateway=gateway,
        payment_reference=payment_reference,
    )

    with transaction():
        _log_activity(
            order,
            actor="customer",
            title="Payment received",
            detail=(
                f"{order.currency} {order.amount} via {gateway}"
                + (f" (ref {payment_reference})" if payment_reference else "")
            ),
        )

        db.session.flush()

        return request


# ---------------------------------------------------------------------------
# CANCEL
# ---------------------------------------------------------------------------

def cancel_order(order_id, user, reason=None):
    request = _get_owned_request_or_raise(order_id, user)
    order = (
        db.session.get(Order, request.order_id) if request.order_id else None
    )

    stage = _stage_for(request, order)

    if stage in NON_CANCELLABLE_STAGES:
        raise ConflictError("This order can no longer be cancelled.")

    with transaction():
        if order:
            order.fulfillment_stage = STAGE_CANCELLED
            _log_activity(
                order, actor="customer", title="Order cancelled", detail=reason
            )
        else:
            request.status = REQUEST_STATUS_CANCELLED
            request.cancelled_at = datetime.now(timezone.utc)
            _log_activity(
                request,
                actor="customer",
                title="Request cancelled",
                detail=reason,
            )

        db.session.flush()

    from users.mailer_service import send_internal_alert

    send_internal_alert(
        subject=f"Order cancelled - {request.title}",
        message=(
            f"{user.full_name} cancelled their order/request "
            f"\"{request.title}\" ({request.ref})."
            + (f" Reason: {reason}" if reason else "")
        ),
        action_path="/orders" if order else "/requests",
    )

    return request


# ---------------------------------------------------------------------------
# REFUND REQUEST
# ---------------------------------------------------------------------------

def request_refund(order_id, user, reason=None):
    request = _get_owned_request_or_raise(order_id, user)

    if not request.order_id:
        raise ConflictError("This order has not been paid for yet.")

    order = db.session.get(Order, request.order_id)

    if order.status != PAYMENT_PAID:
        raise ConflictError(
            "Only paid orders can have a refund requested."
        )

    with transaction():
        order.status = "refund_requested"

        _log_activity(
            order, actor="customer", title="Refund requested", detail=reason
        )

        db.session.flush()

    from users.mailer_service import send_internal_alert

    send_internal_alert(
        subject=f"Refund requested - order {order.reference}",
        message=(
            f"{user.full_name} requested a refund on order "
            f"{order.reference} ({order.currency} {order.amount})."
            + (f" Reason: {reason}" if reason else "")
        ),
        action_path="/orders",
    )

    return request


# ---------------------------------------------------------------------------
# SUBMISSIONS: revision requests / approval
# ---------------------------------------------------------------------------

def _get_owned_submission_or_raise(order_id, submission_id, user):
    request = _get_owned_request_or_raise(order_id, user)

    if not request.order_id:
        raise NotFoundError("Submission not found.")

    submission = db.session.get(Submission, submission_id)

    if not submission or submission.order_id != request.order_id:
        raise NotFoundError("Submission not found.")

    if submission.status == SubmissionStatus.PENDING_REVIEW:
        # Not yet cleared for customer visibility - see
        # submissions/submission.py::SubmissionStatus.PENDING_REVIEW.
        # Treat it the same as not existing rather than leaking that
        # an unreviewed submission exists.
        raise NotFoundError("Submission not found.")

    return request, submission


def _notify_expert_of_review(request, order, outcome, note=None):
    if not request.assigned_to:
        return

    from users.mailer_service import send_submission_reviewed_email

    expert_user = db.session.get(User, request.assigned_to)

    if expert_user:
        send_submission_reviewed_email(expert_user, order, outcome, note)


def request_revision(order_id, submission_id, user, note):
    request, submission = _get_owned_submission_or_raise(
        order_id, submission_id, user
    )
    order = db.session.get(Order, request.order_id)

    with transaction():

        submission.status = SubmissionStatus.REVISION_REQUESTED
        submission.revision_note = note

        order.fulfillment_stage = "revision_in_progress"

        _log_activity(
            order,
            actor="customer",
            title="Revision requested",
            detail=note,
        )

        db.session.flush()

    _notify_expert_of_review(request, order, "revision_requested", note)

    return request


def approve_submission(order_id, submission_id, user):
    request, submission = _get_owned_submission_or_raise(
        order_id, submission_id, user
    )
    order = db.session.get(Order, request.order_id)

    with transaction():

        submission.status = SubmissionStatus.APPROVED
        order.fulfillment_stage = "completed"

        request.status = REQUEST_STATUS_COMPLETED
        request.completed_at = datetime.now(timezone.utc)

        _log_activity(order, actor="customer", title="Order approved")

        db.session.flush()

    _notify_expert_of_review(request, order, "approved")

    return request


def reject_submission(order_id, submission_id, user, note=None):
    """
    A firmer "no" than request_revision() - the customer isn't asking
    for a fix, they're declining the delivery outright. Distinct
    status so support can tell the two apart and step in; the actual
    resolution (redo, partial refund, escalation, etc.) is a human
    support decision made over chat/email, not something this
    endpoint decides on its own.
    """
    request, submission = _get_owned_submission_or_raise(
        order_id, submission_id, user
    )
    order = db.session.get(Order, request.order_id)

    with transaction():

        submission.status = SubmissionStatus.REJECTED
        submission.revision_note = note
        order.fulfillment_stage = "revision_in_progress"

        _log_activity(
            order,
            actor="customer",
            title="Submission rejected",
            detail=note,
        )

        db.session.flush()

    _notify_expert_of_review(request, order, "rejected", note)

    return request


def list_submissions(order_id, user):
    request = _get_owned_request_or_raise(order_id, user)
    order = (
        db.session.get(Order, request.order_id) if request.order_id else None
    )

    return _submissions_for(order)
