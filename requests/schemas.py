# requests/schemas.py

from datetime import datetime

from requests.constants import (
    DEFAULT_PAGE,
    DEFAULT_PER_PAGE,
    MAX_PER_PAGE,
    REQUEST_PRIORITIES,
    REQUEST_SORT_FIELDS,
    REQUEST_STATUSES,
    REQUEST_TYPES,
)
from utils.exceptions import ValidationError


def _string(value, field, *, required=False, max_length=None):
    if value is None:
        if required:
            raise ValidationError(
                f"{field} is required.",
                {"field": field},
            )
        return None

    if not isinstance(value, str):
        raise ValidationError(
            f"{field} must be a string.",
            {"field": field},
        )

    value = value.strip()

    if required and not value:
        raise ValidationError(
            f"{field} cannot be empty.",
            {"field": field},
        )

    if max_length and len(value) > max_length:
        raise ValidationError(
            f"{field} must not exceed {max_length} characters.",
            {"field": field},
        )

    return value


def _optional_number(value, field):
    if value is None:
        return None

    if isinstance(value, bool):
        raise ValidationError(
            f"{field} must be a number.",
            {"field": field},
        )

    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"{field} must be a number.",
            {"field": field},
        )

    if value < 0:
        raise ValidationError(
            f"{field} cannot be negative.",
            {"field": field},
        )

    return value


def _parse_datetime(value, field):
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValidationError(
            f"{field} must be an ISO-8601 datetime.",
            {"field": field},
        )

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        raise ValidationError(
            f"{field} must be a valid ISO-8601 datetime.",
            {"field": field},
        )


def _validate_ids(ids):
    if not isinstance(ids, list):
        raise ValidationError(
            "'ids' must be an array.",
            {"field": "ids"},
        )

    if not ids:
        raise ValidationError(
            "'ids' cannot be empty.",
            {"field": "ids"},
        )

    if len(ids) > 100:
        raise ValidationError(
            "A maximum of 100 requests may be processed at once.",
            {"field": "ids"},
        )

    cleaned = []

    for item in ids:
        if not isinstance(item, str) or not item.strip():
            raise ValidationError(
                "Every request ID must be a non-empty string.",
                {"field": "ids"},
            )

        cleaned.append(item.strip())

    return list(dict.fromkeys(cleaned))


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

def validate_list_requests(args):
    try:
        page = int(args.get("page", DEFAULT_PAGE))
        per_page = int(
            args.get("per_page", DEFAULT_PER_PAGE)
        )
    except ValueError:
        raise ValidationError(
            "page and per_page must be integers."
        )

    if page < 1:
        raise ValidationError(
            "page must be at least 1."
        )

    if per_page < 1 or per_page > MAX_PER_PAGE:
        raise ValidationError(
            f"per_page must be between 1 and {MAX_PER_PAGE}."
        )

    search = args.get("search")
    if search:
        search = search.strip()

    status = args.get("status")
    if status and status not in REQUEST_STATUSES:
        raise ValidationError(
            "Invalid request status.",
            {
                "field": "status",
                "allowed": sorted(REQUEST_STATUSES),
            },
        )

    priority = args.get("priority")
    if priority and priority not in REQUEST_PRIORITIES:
        raise ValidationError(
            "Invalid request priority.",
            {
                "field": "priority",
                "allowed": sorted(REQUEST_PRIORITIES),
            },
        )

    request_type = args.get("type")
    if request_type and request_type not in REQUEST_TYPES:
        raise ValidationError(
            "Invalid request type.",
            {
                "field": "type",
                "allowed": sorted(REQUEST_TYPES),
            },
        )

    types = args.get("types")
    parsed_types = None

    if types:
        parsed_types = []

        for item in types.split(","):
            item = item.strip()

            if item:
                if item not in REQUEST_TYPES:
                    raise ValidationError(
                        "Invalid request type in types.",
                        {
                            "field": "types",
                            "invalid": item,
                            "allowed": sorted(REQUEST_TYPES),
                        },
                    )

                parsed_types.append(item)

        parsed_types = list(dict.fromkeys(parsed_types))

    assigned_to = args.get("assigned_to")
    if assigned_to:
        assigned_to = assigned_to.strip()

    sort_by = args.get("sort_by", "updated_at")

    if sort_by not in REQUEST_SORT_FIELDS:
        raise ValidationError(
            "Invalid sort field.",
            {
                "field": "sort_by",
                "allowed": sorted(REQUEST_SORT_FIELDS),
            },
        )

    direction = args.get("direction", "desc").lower()

    if direction not in {"asc", "desc"}:
        raise ValidationError(
            "direction must be either asc or desc."
        )

    return {
        "page": page,
        "per_page": per_page,
        "search": search,
        "types": parsed_types,
        "type": request_type,
        "status": status,
        "priority": priority,
        "assigned_to": assigned_to,
        "sort_by": sort_by,
        "direction": direction,
    }


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

def validate_create_request(payload):
    if not isinstance(payload, dict):
        raise ValidationError(
            "Request body must be an object."
        )

    request_type = payload.get("type")

    if request_type not in REQUEST_TYPES:
        raise ValidationError(
            "Invalid request type.",
            {
                "field": "type",
                "allowed": sorted(REQUEST_TYPES),
            },
        )

    title = _string(
        payload.get("title"),
        "title",
        required=True,
        max_length=255,
    )

    subject = _string(
        payload.get("subject"),
        "subject",
        max_length=255,
    )

    description = _string(
        payload.get("description"),
        "description",
    )

    customer_id = _string(
        payload.get("customer_id"),
        "customer_id",
        required=True,
        max_length=36,
    )

    priority = payload.get("priority", "normal")

    if priority not in REQUEST_PRIORITIES:
        raise ValidationError(
            "Invalid request priority.",
            {"field": "priority"},
        )

    budget = _optional_number(
        payload.get("budget"),
        "budget",
    )

    deadline = _parse_datetime(
        payload.get("deadline"),
        "deadline",
    )

    tags = payload.get("tags", [])

    if not isinstance(tags, list):
        raise ValidationError(
            "tags must be an array."
        )

    clean_tags = []

    for tag in tags:
        if not isinstance(tag, str):
            raise ValidationError(
                "Every tag must be a string."
            )

        tag = tag.strip()

        if tag:
            clean_tags.append(tag)

    metadata = payload.get("metadata", {})

    if not isinstance(metadata, dict):
        raise ValidationError(
            "metadata must be an object."
        )

    return {
        "type": request_type,
        "title": title,
        "subject": subject,
        "description": description,
        "customer_id": customer_id,
        "priority": priority,
        "budget": budget,
        "deadline": deadline,
        "tags": list(dict.fromkeys(clean_tags)),
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

def validate_update_request(payload):
    if not isinstance(payload, dict):
        raise ValidationError(
            "Request body must be an object."
        )

    if not payload:
        raise ValidationError(
            "At least one field must be provided."
        )

    result = {}

    if "title" in payload:
        result["title"] = _string(
            payload["title"],
            "title",
            required=True,
            max_length=255,
        )

    if "subject" in payload:
        result["subject"] = _string(
            payload["subject"],
            "subject",
            max_length=255,
        )

    if "description" in payload:
        result["description"] = _string(
            payload["description"],
            "description",
        )

    if "status" in payload:
        if payload["status"] not in REQUEST_STATUSES:
            raise ValidationError(
                "Invalid request status.",
                {"field": "status"},
            )

        result["status"] = payload["status"]

    if "priority" in payload:
        if payload["priority"] not in REQUEST_PRIORITIES:
            raise ValidationError(
                "Invalid request priority.",
                {"field": "priority"},
            )

        result["priority"] = payload["priority"]

    if "assignedTo" in payload:
        assigned = payload["assignedTo"]

        if assigned is not None:
            assigned = _string(
                assigned,
                "assignedTo",
                max_length=36,
            )

        result["assigned_to"] = assigned

    if "deadline" in payload:
        result["deadline"] = _parse_datetime(
            payload["deadline"],
            "deadline",
        )

    if "budget" in payload:
        result["budget"] = _optional_number(
            payload["budget"],
            "budget",
        )

    if "tags" in payload:
        tags = payload["tags"]

        if not isinstance(tags, list):
            raise ValidationError(
                "tags must be an array."
            )

        result["tags"] = [
            tag.strip()
            for tag in tags
            if isinstance(tag, str) and tag.strip()
        ]

    return result


# ---------------------------------------------------------------------------
# BULK UPDATE
# ---------------------------------------------------------------------------

def validate_bulk_update_requests(payload):
    if not isinstance(payload, dict):
        raise ValidationError(
            "Request body must be an object."
        )

    ids = _validate_ids(payload.get("ids"))

    update_payload = {
        key: value
        for key, value in payload.items()
        if key != "ids"
    }

    validated = validate_update_request(
        update_payload
    )

    return ids, validated


# ---------------------------------------------------------------------------
# BULK DELETE
# ---------------------------------------------------------------------------

def validate_bulk_delete_requests(payload):
    if not isinstance(payload, dict):
        raise ValidationError(
            "Request body must be an object."
        )

    return _validate_ids(payload.get("ids"))

# ---------------------------------------------------------------------------
# ISSUE QUOTE
# ---------------------------------------------------------------------------

def validate_issue_quote(payload):
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be an object.")

    amount = payload.get("amount")

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise ValidationError(
            "amount is required and must be a number.",
            {"field": "amount"},
        )

    if amount <= 0:
        raise ValidationError(
            "amount must be greater than zero.",
            {"field": "amount"},
        )

    currency = (payload.get("currency") or "USD").strip().upper()

    if len(currency) != 3:
        raise ValidationError(
            "currency must be a 3-letter ISO code.",
            {"field": "currency"},
        )

    delivery_schedule = payload.get("deliverySchedule") or payload.get(
        "delivery_schedule"
    )
    notes = payload.get("notes")
    expires_at = payload.get("expiresAt") or payload.get("expires_at")

    return {
        "amount": amount,
        "currency": currency,
        "delivery_schedule": delivery_schedule,
        "notes": notes,
        "expires_at": expires_at,
    }
