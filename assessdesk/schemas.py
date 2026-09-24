# assessdesk/schemas.py
"""Input validation and JSON serialization for AssessDesk."""

import re
import uuid
from datetime import timezone

from utils.exceptions import ValidationError

from assessdesk.constants import (
    DEFAULT_PER_PAGE,
    GRACE_PERIOD,
    GRANT_ACTIVE,
    GRANT_IN_GRACE,
    GRANT_SORT_FIELDS,
    GRANT_STATUSES,
    IDEMPOTENCY_KEY_MAX_LEN,
    MAX_CONSUME_PER_CALL,
    MAX_PER_PAGE,
)
from assessdesk.models import utcnow

_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


# ---------------------------------------------------------------------------
# Primitive validators
# ---------------------------------------------------------------------------

def iso(dt):
    """ISO-8601 UTC with a trailing Z, or None. Naive values are treated as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_uuid(value, field="id"):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        raise ValidationError(f"Invalid {field}.")


def validate_int(value, field, minimum=None, maximum=None):
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a whole number.")
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a whole number.")
    if minimum is not None and n < minimum:
        raise ValidationError(f"{field} must be at least {minimum}.")
    if maximum is not None and n > maximum:
        raise ValidationError(f"{field} must be at most {maximum}.")
    return n


def validate_idempotency_key(value):
    if not value or not isinstance(value, str) or not _IDEMPOTENCY_RE.match(value):
        raise ValidationError(
            "idempotency_key is required (8-64 chars: letters, digits, '-' or '_')."
        )
    return value[:IDEMPOTENCY_KEY_MAX_LEN]


def validate_consume(data):
    return {
        "amount": validate_int(data.get("amount", 1), "amount", 1, MAX_CONSUME_PER_CALL),
        "idempotency_key": validate_idempotency_key(data.get("idempotency_key")),
        "meta": data.get("meta") if isinstance(data.get("meta"), dict) else None,
    }


def validate_pagination(args):
    page = validate_int(args.get("page", 1), "page", 1)
    per_page = validate_int(args.get("per_page", DEFAULT_PER_PAGE), "per_page", 1, MAX_PER_PAGE)
    return page, per_page


def validate_list_grants(args):
    page, per_page = validate_pagination(args)
    status = (args.get("status") or "").strip() or None
    if status and status not in GRANT_STATUSES + (GRANT_IN_GRACE,):
        raise ValidationError("Invalid status filter.")
    source = (args.get("source") or "").strip() or None
    sort_by = args.get("sort_by") or "granted_at"
    if sort_by not in GRANT_SORT_FIELDS:
        sort_by = "granted_at"
    direction = "asc" if args.get("direction") == "asc" else "desc"
    return {
        "page": page,
        "per_page": per_page,
        "status": status,
        "source": source,
        "search": (args.get("search") or "").strip()[:120] or None,
        "sort_by": sort_by,
        "direction": direction,
    }


def validate_package(data, partial=False):
    out = {}

    def has(k):
        return k in data and data[k] is not None

    if has("name") or not partial:
        name = (data.get("name") or "").strip()
        if not 2 <= len(name) <= 80:
            raise ValidationError("Package name must be 2-80 characters.")
        out["name"] = name
    if "description" in data:
        desc = (data.get("description") or "").strip()
        out["description"] = desc[:255] or None
    if has("questions") or not partial:
        out["questions"] = validate_int(data.get("questions"), "questions", 1, 100000)
    if has("validity_days") or not partial:
        out["validity_days"] = validate_int(data.get("validity_days"), "validity_days", 1, 3650)
    if has("price") or not partial:
        # Admin enters major units (e.g. 1500.00); store minor units.
        try:
            price = round(float(data.get("price")) * 100)
        except (TypeError, ValueError):
            raise ValidationError("price must be a number.")
        if price < 0:
            raise ValidationError("price cannot be negative.")
        out["price_minor"] = price
    if has("currency") or not partial:
        cur = (data.get("currency") or "KES").strip().upper()
        if not _CURRENCY_RE.match(cur):
            raise ValidationError("currency must be a 3-letter ISO code.")
        out["currency"] = cur
    if has("is_active"):
        out["is_active"] = bool(data.get("is_active"))
    if has("sort_order"):
        out["sort_order"] = validate_int(data.get("sort_order"), "sort_order", 0, 10000)
    return out


def validate_manual_grant(data):
    user_id = validate_int(data.get("user_id"), "user_id", 1)
    questions = validate_int(data.get("questions"), "questions", 1, 100000)
    validity_days = validate_int(data.get("validity_days"), "validity_days", 1, 3650)
    note = (data.get("note") or "").strip()[:255] or None
    return {"user_id": user_id, "questions": questions, "validity_days": validity_days, "note": note}


def validate_extend(data):
    hours = validate_int(data.get("hours"), "hours", 1, 24 * 365)
    return {"hours": hours}


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _seconds_until(dt, now):
    return max(0, int((dt - now).total_seconds()))


def grant_effective_status(grant, now=None):
    now = now or utcnow()
    if grant.status != GRANT_ACTIVE:
        return grant.status
    if now >= grant.expires_at + GRACE_PERIOD:
        return "expired"
    if now >= grant.expires_at:
        return GRANT_IN_GRACE
    return GRANT_ACTIVE


def serialize_grant(grant, now=None, include_user=False):
    now = now or utcnow()
    usable_until = grant.expires_at + GRACE_PERIOD
    data = {
        "id": str(grant.id),
        "source": grant.source,
        "package_id": str(grant.package_id) if grant.package_id else None,
        "package_name": grant.package.name if grant.package else None,
        "questions_granted": grant.questions_granted,
        "questions_remaining": grant.questions_remaining,
        "granted_at": iso(grant.granted_at),
        "expires_at": iso(grant.expires_at),
        "usable_until": iso(usable_until),
        "expires_in_seconds": _seconds_until(grant.expires_at, now),
        "usable_for_seconds": _seconds_until(usable_until, now),
        "status": grant_effective_status(grant, now),
        "note": grant.note,
    }
    if include_user and grant.user:
        data["user"] = {
            "id": grant.user.id,
            "name": grant.user.full_name,
            "email": grant.user.email,
            "role": grant.user.role,
        }
    return data


def serialize_package(pkg):
    return {
        "id": str(pkg.id),
        "name": pkg.name,
        "description": pkg.description,
        "questions": pkg.questions,
        "validity_days": pkg.validity_days,
        "price": pkg.price_minor / 100,
        "price_minor": pkg.price_minor,
        "currency": pkg.currency,
        "is_active": pkg.is_active,
        "sort_order": pkg.sort_order,
        "created_at": iso(pkg.created_at),
        "updated_at": iso(pkg.updated_at),
    }


def serialize_purchase(p, include_user=False):
    data = {
        "id": str(p.id),
        "reference": p.reference,
        "package_id": str(p.package_id),
        "package_name": p.package.name if p.package else None,
        "questions": p.questions,
        "validity_days": p.validity_days,
        "amount": p.amount_minor / 100,
        "currency": p.currency,
        "status": p.status,
        "paid_at": iso(p.paid_at),
        "created_at": iso(p.created_at),
    }
    if include_user and p.user:
        data["user"] = {"id": p.user.id, "name": p.user.full_name, "email": p.user.email}
    return data


def serialize_ad_user(user):
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
    }
