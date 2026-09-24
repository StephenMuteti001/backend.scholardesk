from datetime import datetime

from payments.constants import (
    ALLOWED_SORT_FIELDS,
    DEFAULT_PAGE,
    DEFAULT_PER_PAGE,
    MAX_PER_PAGE,
    PAYMENT_STATUSES,
    SORT_DIRECTIONS,
)
from utils.exceptions import ValidationError


def _parse_int(
    value,
    field,
    default=None,
    minimum=None,
    maximum=None,
):
    if value in (None, ""):
        return default

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"{field} must be an integer.",
            {"field": field},
        )

    if minimum is not None and parsed < minimum:
        raise ValidationError(
            f"{field} must be at least {minimum}.",
            {"field": field},
        )

    if maximum is not None and parsed > maximum:
        raise ValidationError(
            f"{field} must not exceed {maximum}.",
            {"field": field},
        )

    return parsed


def validate_list_payments(args):
    page = _parse_int(
        args.get("page"),
        "page",
        DEFAULT_PAGE,
        minimum=1,
    )

    per_page = _parse_int(
        args.get("per_page"),
        "per_page",
        DEFAULT_PER_PAGE,
        minimum=1,
        maximum=MAX_PER_PAGE,
    )

    search = args.get("search")

    if search is not None:
        search = search.strip()

    status = args.get("status")

    if status:
        status = status.strip()

        if status not in PAYMENT_STATUSES:
            raise ValidationError(
                "Invalid payment status.",
                {
                    "field": "status",
                    "allowed": sorted(PAYMENT_STATUSES),
                },
            )

    sort_by = args.get(
        "sort_by",
        "due_at",
    )

    if sort_by not in ALLOWED_SORT_FIELDS:
        raise ValidationError(
            "Invalid sort field.",
            {
                "field": "sort_by",
                "allowed": sorted(
                    ALLOWED_SORT_FIELDS.keys()
                ),
            },
        )

    direction = args.get(
        "direction",
        "desc",
    )

    if direction not in SORT_DIRECTIONS:
        raise ValidationError(
            "Invalid sort direction.",
            {
                "field": "direction",
                "allowed": sorted(
                    SORT_DIRECTIONS
                ),
            },
        )

    return {
        "page": page,
        "per_page": per_page,
        "search": search,
        "status": status,
        "sort_by": sort_by,
        "direction": direction,
    }


def validate_update_payment(payload):
    if not isinstance(payload, dict):
        raise ValidationError(
            "Request body must be an object."
        )

    allowed_fields = {
        "status",
        "notes",
        "payment_method",
        "due_at",
    }

    unknown_fields = set(payload) - allowed_fields

    if unknown_fields:
        raise ValidationError(
            "Request contains unsupported fields.",
            {
                "fields": sorted(
                    unknown_fields
                )
            },
        )

    result = {}

    if "status" in payload:
        status = payload["status"]

        if status not in PAYMENT_STATUSES:
            raise ValidationError(
                "Invalid payment status.",
                {
                    "field": "status",
                    "allowed": sorted(
                        PAYMENT_STATUSES
                    ),
                },
            )

        result["status"] = status

    if "notes" in payload:
        notes = payload["notes"]

        if notes is not None and not isinstance(
            notes,
            str,
        ):
            raise ValidationError(
                "notes must be a string or null.",
                {"field": "notes"},
            )

        result["notes"] = notes

    if "payment_method" in payload:
        method = payload["payment_method"]

        if not isinstance(method, str):
            raise ValidationError(
                "payment_method must be a string.",
                {"field": "payment_method"},
            )

        result["payment_method"] = method.strip()

    if "due_at" in payload:
        due_at = payload["due_at"]

        if due_at is None:
            result["due_at"] = None
        else:
            try:
                result["due_at"] = datetime.fromisoformat(
                    due_at.replace("Z", "+00:00")
                )
            except (
                TypeError,
                ValueError,
            ):
                raise ValidationError(
                    "due_at must be a valid ISO datetime.",
                    {"field": "due_at"},
                )

    return result


def validate_bulk_update_payments(payload):
    if not isinstance(payload, dict):
        raise ValidationError(
            "Request body must be an object."
        )

    ids = payload.get("ids")

    if not isinstance(ids, list) or not ids:
        raise ValidationError(
            "The 'ids' field must be a non-empty array.",
            {"field": "ids"},
        )

    if any(
        not isinstance(item, str) or not item.strip()
        for item in ids
    ):
        raise ValidationError(
            "All payment IDs must be non-empty strings.",
            {"field": "ids"},
        )

    update = {}

    if "status" in payload:
        status = payload["status"]

        if status not in PAYMENT_STATUSES:
            raise ValidationError(
                "Invalid payment status.",
                {"field": "status"},
            )

        update["status"] = status

    if not update:
        raise ValidationError(
            "At least one update field is required."
        )

    return {
        "ids": list(dict.fromkeys(ids)),
        "update": update,
    }


def validate_bulk_delete_payments(payload):
    if not isinstance(payload, dict):
        raise ValidationError(
            "Request body must be an object."
        )

    ids = payload.get("ids")

    if not isinstance(ids, list) or not ids:
        raise ValidationError(
            "The 'ids' field must be a non-empty array.",
            {"field": "ids"},
        )

    if any(
        not isinstance(item, str) or not item.strip()
        for item in ids
    ):
        raise ValidationError(
            "All payment IDs must be non-empty strings.",
            {"field": "ids"},
        )

    return list(dict.fromkeys(ids))