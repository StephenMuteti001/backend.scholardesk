# orders/schemas.py

from decimal import Decimal

from orders.constants import (
    ORDER_GATEWAYS,
    ORDER_STATUSES,
    REFUND_REASONS,
)


def _decimal(value):
    if value is None:
        return 0
    return float(Decimal(str(value)))


def serialize_customer(user):
    if not user:
        return {
            "id": None,
            "name": "Unknown",
            "email": "",
        }

    name = getattr(user, "name", None)

    if not name:
        first_name = getattr(user, "first_name", "") or ""
        last_name = getattr(user, "last_name", "") or ""
        name = f"{first_name} {last_name}".strip()

    return {
        "id": str(user.id),
        "name": name or getattr(user, "email", "Unknown"),
        "email": getattr(user, "email", ""),
    }


def serialize_order(order):
    request_type = None

    if order.request:
        request_type = getattr(
            order.request,
            "type",
            None,
        )

    return {
        "id": str(order.id),
        "ref": order.reference,
        "material_id": (
            str(order.material_id)
            if order.material_id
            else None
        ),
        "materialTitle": order.item_title,
        "sourceType": order.source_type,
        "requestType": request_type,
        "customer": serialize_customer(order.customer),
        "amount": _decimal(order.amount),
        "currency": order.currency,
        "gateway": order.gateway,
        "status": order.status,
        "fulfillmentStage": order.fulfillment_stage,
        "expertBudget": (
            _decimal(order.expert_budget)
            if order.expert_budget is not None
            else None
        ),
        "assignedExpertId": (
            order.request.assigned_to
            if order.request and order.request.assigned_to
            else None
        ),
        "assignedExpertName": (
            order.request.assigned_user.full_name
            if order.request and order.request.assigned_user
            else None
        ),
        "createdAt": (
            order.created_at.isoformat()
            if order.created_at
            else None
        ),
        "updatedAt": (
            order.updated_at.isoformat()
            if order.updated_at
            else None
        ),
    }


def validate_order_status(status):
    if status not in ORDER_STATUSES:
        raise ValueError(
            f"Invalid order status. Expected one of: "
            f"{', '.join(ORDER_STATUSES)}"
        )


def validate_gateway(gateway):
    if gateway not in ORDER_GATEWAYS:
        raise ValueError(
            f"Invalid payment gateway. Expected one of: "
            f"{', '.join(ORDER_GATEWAYS)}"
        )


def validate_refund_payload(payload):
    payload = payload or {}

    reason = payload.get("reason")
    amount = payload.get("amount")

    if not reason:
        raise ValueError("Refund reason is required.")

    if reason not in REFUND_REASONS:
        raise ValueError(
            f"Invalid refund reason. Expected one of: "
            f"{', '.join(REFUND_REASONS)}"
        )

    if amount is not None:
        try:
            amount = Decimal(str(amount))
        except Exception:
            raise ValueError("Refund amount must be numeric.")

        if amount <= 0:
            raise ValueError("Refund amount must be greater than zero.")

    return {
        "reason": reason,
        "amount": amount,
    }


def validate_assign_expert_payload(payload):
    payload = payload or {}

    expert_id = payload.get("expert_id") or payload.get("expertId")
    budget = payload.get("budget")

    if not expert_id:
        raise ValueError("expert_id is required.")

    if budget is None:
        raise ValueError("budget is required.")

    try:
        budget = Decimal(str(budget))
    except Exception:
        raise ValueError("budget must be numeric.")

    if budget <= 0:
        raise ValueError("budget must be greater than zero.")

    return {
        "expert_id": expert_id,
        "budget": budget,
    }


def serialize_pagination(pagination):
    return {
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pagination.pages,
        "total": pagination.total,
    }

# ---------------------------------------------------------------------------
# Expert opportunities + interest (additive)
#
# serialize_available_order() is deliberately narrower than
# serialize_order_for_expert(): an order the expert has NOT been
# assigned must never leak customer identity or contact details.
# ---------------------------------------------------------------------------

def serialize_available_order(order, interested=False):
    request = order.request
    metadata = (request.metadata_json or {}) if request else {}

    return {
        "id": str(order.id),
        "reference": order.reference,
        "title": order.item_title,
        "subject": (request.subject if request else None)
        or metadata.get("subject"),
        "assignmentType": metadata.get("assignment_type"),
        "words": metadata.get("word_count"),
        "pages": (
            max(1, round(metadata["word_count"] / 275))
            if metadata.get("word_count")
            else None
        ),
        "citationStyle": metadata.get("citation_style"),
        "deadline": (
            request.deadline.isoformat()
            if request and request.deadline
            else None
        ),
        "currency": order.currency,
        "interested": bool(interested),
        "createdAt": (
            order.created_at.isoformat()
            if order.created_at
            else None
        ),
    }


def serialize_order_interest(interest, active_assignments=0):
    """
    Admin-facing view of one expert's registered interest.

    Field names match the admin portal's orderInterestService.ts,
    which normalizes snake_case straight onto its own type.
    """
    expert = interest.expert
    user = expert.user if expert else None

    specialities = (expert.specialities if expert else None) or []

    if not isinstance(specialities, list):
        specialities = [specialities]

    return {
        "id": str(interest.id),
        "order_id": str(interest.order_id),
        "expert_id": str(interest.expert_id),
        "expert_name": (expert.name if expert else None) or "Unknown",
        "expert_email": (
            getattr(user, "email", None) if user else None
        ) or "",
        "specialities": specialities,
        "rating": float(expert.rating or 0) if expert else 0.0,
        "completed_orders": (
            int(expert.completed_orders or 0) if expert else 0
        ),
        "active_assignments": int(active_assignments or 0),
        "is_available": bool(expert.is_available) if expert else False,
        "status": expert.status if expert else None,
        "note": interest.note,
        "created_at": (
            interest.created_at.isoformat()
            if interest.created_at
            else None
        ),
        "withdrawn_at": (
            interest.withdrawn_at.isoformat()
            if interest.withdrawn_at
            else None
        ),
    }


def validate_interest_payload(payload):
    payload = payload or {}

    if not isinstance(payload, dict):
        raise ValueError("Request body must be an object.")

    note = payload.get("note")

    if note is not None:
        if not isinstance(note, str):
            raise ValueError("note must be a string.")

        note = note.strip() or None

        if note and len(note) > 1000:
            raise ValueError("note must not exceed 1000 characters.")

    return {"note": note}
