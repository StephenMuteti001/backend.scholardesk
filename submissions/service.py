# submissions/service.py
"""
Entry point for the expert/admin side of the submissions workflow -
releasing a deliverable against an Order. The customer-facing read/act
side (list submissions, request a revision, approve) already lives in
customer_orders/service.py, since those operate on an owned request;
this module is the other half: creating a submission in the first
place, and clearing it for customer visibility.
"""

import uuid
from datetime import datetime, timezone

from extensions import db
from orders.order import Order
from submissions.constants import UPLOAD_SUBDIR
from submissions.submission import Submission, SubmissionStatus
from users.user import User
from utils.exceptions import ForbiddenError, NotFoundError
from utils.roles import ADMIN_ROLES
from utils.transaction import transaction
from utils.uploads import save_uploaded_files


def _get_order_or_raise(order_id):
    order = db.session.get(Order, order_id)

    if not order:
        raise NotFoundError("Order not found.")

    return order


def _assert_can_submit(order, actor):
    """
    Only the expert assigned to the underlying request - or an admin,
    acting on their behalf - may release a submission against an
    order. Assignment lives on ServiceRequest.assigned_to (see
    requests/request.py), not on Order itself.
    """

    if actor.role in ADMIN_ROLES:
        return

    request = order.request

    if not request or request.assigned_to != actor.id:
        raise ForbiddenError(
            "You are not assigned to this order."
        )


def _next_version(order_id):
    latest = (
        Submission.query.filter(Submission.order_id == order_id)
        .order_by(Submission.version.desc())
        .first()
    )

    return (latest.version + 1) if latest else 1


def create_submission(order_id, actor, note, uploaded_files):
    """
    Record a new deliverable version for an order.

    Deliberately created with status=PENDING_REVIEW: it stays hidden
    from the customer (see customer_orders/service.py::_submissions_for)
    until release_submission() below clears it - matching the "must
    not be exposed to the customer until the internal integrity review
    passes" rule in docs/API.md (customer-portal frontend repo).
    """

    order = _get_order_or_raise(order_id)

    _assert_can_submit(order, actor)

    version = _next_version(order.id)

    file_records = []

    if uploaded_files:
        saved_paths = save_uploaded_files(
            uploaded_files,
            UPLOAD_SUBDIR.format(order_id=order.id),
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

    with transaction():
        submission = Submission(
            order_id=order.id,
            version=version,
            title=f"Submission v{version}",
            summary=note,
            files=file_records,
            status=SubmissionStatus.PENDING_REVIEW,
        )

        db.session.add(submission)

        activity = list(order.activity_log or [])

        activity.append(
            {
                "id": str(uuid.uuid4()),
                "at": datetime.now(timezone.utc).isoformat(),
                "actor": "expert",
                "title": "Work submitted for quality review",
                "detail": None,
            }
        )

        order.activity_log = activity
        order.fulfillment_stage = "quality_review"

        db.session.flush()

    from users.mailer_service import send_internal_alert

    send_internal_alert(
        subject=f"Submission awaiting review - order {order.reference}",
        message=(
            f"{actor.full_name} delivered version {version} of "
            f"\"{order.item_title}\" ({order.reference}). It needs an "
            f"integrity review before the customer can see it."
        ),
        action_path="/orders",
    )

    return submission


def list_submissions_for_admin(order_id):
    """
    Unlike customer_orders/service.py::_submissions_for(), this
    includes PENDING_REVIEW submissions - support needs to see (and
    release) work the client can't see yet.
    """
    order = _get_order_or_raise(order_id)

    submissions = (
        Submission.query.filter(Submission.order_id == order.id)
        .order_by(Submission.version.asc())
        .all()
    )

    return [submission.to_dict() for submission in submissions]


def release_submission(order_id, submission_id, actor, note=None, additional_files=None):
    """
    Admin action: clears a PENDING_REVIEW submission for the customer to
    see, once the internal integrity review has passed. Support can
    also attach additional files at this point - e.g. an integrity
    report, a support-added cover note, or a corrected file - which
    are appended to the submission the customer sees.
    """

    order = _get_order_or_raise(order_id)

    if actor.role not in ADMIN_ROLES:
        raise ForbiddenError(
            "Only an administrator can release a submission."
        )

    submission = Submission.query.filter(
        Submission.id == submission_id,
        Submission.order_id == order.id,
    ).first()

    if not submission:
        raise NotFoundError("Submission not found.")

    if submission.status != SubmissionStatus.PENDING_REVIEW:
        return submission

    new_file_records = []

    if additional_files:
        saved_paths = save_uploaded_files(
            additional_files,
            UPLOAD_SUBDIR.format(order_id=order.id),
        )

        for path, upload in zip(saved_paths, additional_files):
            if not path:
                continue

            new_file_records.append(
                {
                    "id": str(uuid.uuid4()),
                    "name": upload.filename,
                    "size": getattr(upload, "content_length", None) or 0,
                    "url": path,
                    "added_by": "support",
                }
            )

    with transaction():
        submission.status = SubmissionStatus.DELIVERED

        if new_file_records:
            submission.files = list(submission.files or []) + new_file_records

        if note:
            submission.summary = (
                f"{submission.summary}\n\n[Support note] {note}"
                if submission.summary
                else f"[Support note] {note}"
            )

        activity = list(order.activity_log or [])

        activity.append(
            {
                "id": str(uuid.uuid4()),
                "at": datetime.now(timezone.utc).isoformat(),
                "actor": "system",
                "title": "Work delivered",
                "detail": (
                    f"{len(new_file_records)} additional file(s) attached by support."
                    if new_file_records
                    else None
                ),
            }
        )

        order.activity_log = activity
        order.fulfillment_stage = "delivered"

        db.session.flush()

    from users.mailer_service import send_submission_delivered_email

    customer = db.session.get(User, order.customer_id)

    if customer:
        send_submission_delivered_email(customer, order, submission)

    return submission
