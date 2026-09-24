from datetime import datetime

from sqlalchemy import or_, func, asc, desc

from extensions import db

from utils.exceptions import (
    NotFoundError,
    ValidationError,
    ConflictError,
)

from utils.transaction import transaction

from payments.payment import Payment
from payments.constants import (
    ALLOWED_SORT_FIELDS,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PROCESSING,
    PAYMENT_STATUS_ON_HOLD,
    PAYMENT_STATUS_SCHEDULED,
    ALLOWED_TRANSITIONS,
)

# Adjust this import to your existing Expert model.
from experts.expert import Expert


def _validate_status_transition(
    current,
    new,
):
    if current == new:
        return

    allowed = ALLOWED_TRANSITIONS.get(
        current,
        set(),
    )

    if new not in allowed:
        raise ConflictError(
            f"Cannot change payment from "
            f"{current} to {new}.",
            {
                "current_status": current,
                "requested_status": new,
            },
        )


def _get_payment_or_raise(payment_id):
    payment = db.session.get(
        Payment,
        payment_id,
    )

    if payment is None:
        raise NotFoundError(
            "Payment not found.",
            {"payment_id": payment_id},
        )

    return payment


def _get_expert_or_raise(expert_id):
    expert = db.session.get(
        Expert,
        expert_id,
    )

    if expert is None:
        raise NotFoundError(
            "Expert not found.",
            {"expert_id": expert_id},
        )

    return expert


def _expert_name(expert):
    if not expert:
        return "Unknown expert"

    return (
        getattr(expert, "name", None)
        or getattr(expert, "full_name", None)
        or getattr(expert, "email", None)
        or "Unknown expert"
    )


def _serialize_payment_row(payment, expert=None):
    return {
        "id": str(payment.id),
        "expert_id": str(payment.expert_id),
        "expert": _expert_name(expert),
        "period": (
            f"{payment.period_start.isoformat()}"
            f" – "
            f"{payment.period_end.isoformat()}"
        ),
        "period_start": (
            payment.period_start.isoformat()
            if payment.period_start
            else None
        ),
        "period_end": (
            payment.period_end.isoformat()
            if payment.period_end
            else None
        ),
        "jobs": payment.jobs,
        "amount": float(payment.amount or 0),
        "currency": payment.currency,
        "method": payment.payment_method,
        "due_at": (
            payment.due_at.isoformat()
            if payment.due_at
            else None
        ),
        "status": payment.status,
        "processed_at": (
            payment.processed_at.isoformat()
            if payment.processed_at
            else None
        ),
        "processed_by": payment.processed_by,
        "paid_at": (
            payment.paid_at.isoformat()
            if payment.paid_at
            else None
        ),
        "external_reference": payment.external_reference,
        "notes": payment.notes,
        "created_at": (
            payment.created_at.isoformat()
            if payment.created_at
            else None
        ),
        "updated_at": (
            payment.updated_at.isoformat()
            if payment.updated_at
            else None
        ),
    }


def list_payments(
    page=1,
    per_page=20,
    search=None,
    status=None,
    sort_by="due_at",
    direction="desc",
):
    expert_name = func.concat(
        Expert.first_name,
        " ",
        Expert.last_name,
    )

    query = (
        db.session.query(
            Payment,
            Expert,
        )
        .outerjoin(
            Expert,
            Expert.id == Payment.expert_id,
        )
    )

    if search:
        pattern = f"%{search}%"

        query = query.filter(
            or_(
                expert_name.ilike(pattern),
                Expert.email.ilike(pattern),
                Payment.payment_method.ilike(pattern),
                Payment.status.ilike(pattern),
            )
        )

    if status:
        query = query.filter(
            Payment.status == status
        )

    sort_column = ALLOWED_SORT_FIELDS.get(
        sort_by
    )

    if sort_column == "expert_name":
        sort_expression = expert_name
    else:
        sort_expression = getattr(
            Payment,
            sort_column,
        )

    if direction == "asc":
        query = query.order_by(
            asc(sort_expression)
        )
    else:
        query = query.order_by(
            desc(sort_expression)
        )

    total = query.count()

    items = (
        query
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    pages = (
        (total + per_page - 1) // per_page
        if total
        else 1
    )

    return {
        "items": [
            _serialize_payment_row(
                payment,
                expert,
            )
            for payment, expert in items
        ],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "total": total,
        },
    }


def get_payment(payment_id):
    payment = _get_payment_or_raise(
        payment_id
    )

    expert = db.session.get(
        Expert,
        payment.expert_id,
    )

    return _serialize_payment_row(
        payment,
        expert,
    )


def get_payment_statistics():
    total = (
        db.session.query(
            func.count(Payment.id)
        )
        .scalar()
        or 0
    )

    due_this_cycle = (
        db.session.query(
            func.coalesce(
                func.sum(Payment.amount),
                0,
            )
        )
        .filter(
            Payment.status != PAYMENT_STATUS_PAID
        )
        .scalar()
        or 0
    )

    paid_30_days = (
        db.session.query(
            func.coalesce(
                func.sum(Payment.amount),
                0,
            )
        )
        .filter(
            Payment.status == PAYMENT_STATUS_PAID,
        )
        .filter(
            Payment.paid_at.isnot(None)
        )
        .filter(
            Payment.paid_at >= datetime.utcnow()
        )
        .scalar()
        or 0
    )

    on_hold = (
        db.session.query(
            func.count(Payment.id)
        )
        .filter(
            Payment.status == PAYMENT_STATUS_ON_HOLD
        )
        .scalar()
        or 0
    )

    experts_paid = (
        db.session.query(
            func.count(
                func.distinct(
                    Payment.expert_id
                )
            )
        )
        .filter(
            Payment.status == PAYMENT_STATUS_PAID
        )
        .scalar()
        or 0
    )

    return {
        "total": total,
        "due_this_cycle": float(
            due_this_cycle
        ),
        "paid_30_days": float(
            paid_30_days
        ),
        "on_hold": on_hold,
        "experts_paid": experts_paid,
    }


def update_payment(
    payment_id,
    payload,
    actor_id,
):
    payment = _get_payment_or_raise(
        payment_id
    )

    new_status = payload.get(
        "status"
    )

    with transaction():
        if new_status:
            _validate_status_transition(
                payment.status,
                new_status,
            )

            payment.status = new_status

            if new_status == PAYMENT_STATUS_PROCESSING:
                payment.processed_at = datetime.utcnow()
                payment.processed_by = actor_id

            elif new_status == PAYMENT_STATUS_PAID:
                if not payment.processed_at:
                    payment.processed_at = (
                        datetime.utcnow()
                    )

                if not payment.processed_by:
                    payment.processed_by = actor_id

                payment.paid_at = datetime.utcnow()

        if "notes" in payload:
            payment.notes = payload["notes"]

        if "payment_method" in payload:
            payment.payment_method = (
                payload["payment_method"]
            )

        if "due_at" in payload:
            payment.due_at = payload["due_at"]

    expert = db.session.get(
        Expert,
        payment.expert_id,
    )

    if new_status and expert and expert.user:
        from users.mailer_service import (
            send_payout_on_hold_email,
            send_payout_paid_email,
        )

        if new_status == PAYMENT_STATUS_PAID:
            send_payout_paid_email(expert.user, payment)
        elif new_status == PAYMENT_STATUS_ON_HOLD:
            send_payout_on_hold_email(expert.user, payment, payload.get("notes"))

    return _serialize_payment_row(
        payment,
        expert,
    )


def bulk_update_payments(
    ids,
    update,
    actor_id,
):
    payments = (
        db.session.query(Payment)
        .filter(
            Payment.id.in_(ids)
        )
        .all()
    )

    found_ids = {
        payment.id
        for payment in payments
    }

    missing_ids = [
        payment_id
        for payment_id in ids
        if payment_id not in found_ids
    ]

    if missing_ids:
        raise NotFoundError(
            "One or more payments were not found.",
            {"payment_ids": missing_ids},
        )

    status = update.get("status")

    with transaction():
        for payment in payments:
            if status:
                _validate_status_transition(
                    payment.status,
                    status,
                )

                payment.status = status

                if status == PAYMENT_STATUS_PROCESSING:
                    payment.processed_at = (
                        datetime.utcnow()
                    )
                    payment.processed_by = actor_id

                elif status == PAYMENT_STATUS_PAID:
                    payment.processed_at = (
                        payment.processed_at
                        or datetime.utcnow()
                    )
                    payment.processed_by = (
                        payment.processed_by
                        or actor_id
                    )
                    payment.paid_at = datetime.utcnow()

    experts = {
        expert.id: expert
        for expert in (
            db.session.query(Expert)
            .filter(
                Expert.id.in_(
                    [p.expert_id for p in payments]
                )
            )
            .all()
        )
    }

    if status in (PAYMENT_STATUS_PAID, PAYMENT_STATUS_ON_HOLD):
        from users.mailer_service import (
            send_payout_on_hold_email,
            send_payout_paid_email,
        )

        for payment in payments:
            expert = experts.get(payment.expert_id)

            if not expert or not expert.user:
                continue

            if status == PAYMENT_STATUS_PAID:
                send_payout_paid_email(expert.user, payment)
            else:
                send_payout_on_hold_email(expert.user, payment, update.get("notes"))

    return [
        _serialize_payment_row(
            payment,
            experts.get(payment.expert_id),
        )
        for payment in payments
    ]


def delete_payment(payment_id):
    payment = _get_payment_or_raise(
        payment_id
    )

    if payment.status == PAYMENT_STATUS_PAID:
        raise ConflictError(
            "Paid payments cannot be deleted."
        )

    with transaction():
        db.session.delete(payment)

    return True


def bulk_delete_payments(ids):
    payments = (
        db.session.query(Payment)
        .filter(
            Payment.id.in_(ids)
        )
        .all()
    )

    missing_ids = [
        payment_id
        for payment_id in ids
        if payment_id
        not in {p.id for p in payments}
    ]

    if missing_ids:
        raise NotFoundError(
            "One or more payments were not found.",
            {"payment_ids": missing_ids},
        )

    paid = [
        payment.id
        for payment in payments
        if payment.status == PAYMENT_STATUS_PAID
    ]

    if paid:
        raise ConflictError(
            "Paid payments cannot be deleted.",
            {"payment_ids": paid},
        )

    with transaction():
        for payment in payments:
            db.session.delete(payment)

    return len(payments)

# ---------------------------------------------------------------------------
# Expert-facing: "my earnings" (balance + transaction history)
# ---------------------------------------------------------------------------

def get_balance_for_expert(expert_id):
    """
    There's no separate running ledger in this model - a payout only
    exists as a Payment row once support has scheduled one. "Available"
    approximates money that's been scheduled but not yet sent;
    "pending" is one already being processed; "total_earned" is
    everything actually paid out, lifetime.
    """
    rows = (
        db.session.query(Payment.status, func.sum(Payment.amount))
        .filter(Payment.expert_id == expert_id)
        .group_by(Payment.status)
        .all()
    )

    totals = {status: float(total or 0) for status, total in rows}

    return {
        "available": totals.get(PAYMENT_STATUS_SCHEDULED, 0.0),
        "pending": totals.get(PAYMENT_STATUS_PROCESSING, 0.0),
        "total_earned": totals.get(PAYMENT_STATUS_PAID, 0.0),
        "on_hold": totals.get(PAYMENT_STATUS_ON_HOLD, 0.0),
    }


def list_transactions_for_expert(expert_id, page=1, per_page=50):
    pagination = (
        Payment.query.filter(Payment.expert_id == expert_id)
        .order_by(Payment.period_end.desc(), Payment.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return [
        {
            "id": str(payment.id),
            "type": "payout",
            "amount": float(payment.amount),
            "description": (
                f"Payout for {payment.period_start.isoformat()} - "
                f"{payment.period_end.isoformat()}"
            ),
            "status": payment.status,
            "order_id": None,
            "created_at": (
                payment.paid_at.isoformat()
                if payment.paid_at
                else payment.created_at.isoformat()
            ),
        }
        for payment in pagination.items
    ]
