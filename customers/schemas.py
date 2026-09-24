from customers.constants import (
    CUSTOMER_STATUSES,
    CUSTOMER_SORT_FIELDS,
    DEFAULT_PAGE,
    DEFAULT_PER_PAGE,
    MAX_PER_PAGE,
    DEFAULT_SORT_BY,
    DEFAULT_DIRECTION,
)
from utils.exceptions import ValidationError


def _clean_string(value):
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValidationError(
            "Expected a string value."
        )

    value = value.strip()

    return value or None


def _parse_positive_int(
    value,
    field_name,
    default,
    maximum=None,
):
    if value is None or value == "":
        return default

    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"{field_name} must be an integer.",
            {"field": field_name},
        )

    if value < 1:
        raise ValidationError(
            f"{field_name} must be greater than zero.",
            {"field": field_name},
        )

    if maximum is not None and value > maximum:
        raise ValidationError(
            f"{field_name} cannot exceed {maximum}.",
            {
                "field": field_name,
                "maximum": maximum,
            },
        )

    return value


def validate_list_customers(args):
    page = _parse_positive_int(
        args.get("page"),
        "page",
        DEFAULT_PAGE,
    )

    per_page = _parse_positive_int(
        args.get("per_page"),
        "per_page",
        DEFAULT_PER_PAGE,
        MAX_PER_PAGE,
    )

    search = _clean_string(args.get("search"))
    country = _clean_string(args.get("country"))
    status = _clean_string(args.get("status"))

    if status and status not in CUSTOMER_STATUSES:
        raise ValidationError(
            "Invalid customer status.",
            {
                "field": "status",
                "allowed": list(CUSTOMER_STATUSES),
            },
        )

    sort_by = _clean_string(
        args.get("sort_by")
    ) or DEFAULT_SORT_BY

    if sort_by not in CUSTOMER_SORT_FIELDS:
        raise ValidationError(
            "Invalid sort field.",
            {
                "field": "sort_by",
                "allowed": list(CUSTOMER_SORT_FIELDS.keys()),
            },
        )

    direction = (
        _clean_string(args.get("direction"))
        or DEFAULT_DIRECTION
    ).lower()

    if direction not in ("asc", "desc"):
        raise ValidationError(
            "Direction must be 'asc' or 'desc'.",
            {
                "field": "direction",
                "allowed": ["asc", "desc"],
            },
        )

    return {
        "page": page,
        "per_page": per_page,
        "search": search,
        "status": status,
        "country": country,
        "sort_by": sort_by,
        "direction": direction,
    }


def validate_update_customer(payload):
    if not isinstance(payload, dict):
        raise ValidationError(
            "Request body must be a JSON object."
        )

    allowed = {
        "status",
        "name",
        "country",
    }

    unknown = set(payload) - allowed

    if unknown:
        raise ValidationError(
            "Request contains unsupported fields.",
            {
                "fields": sorted(unknown),
            },
        )

    if not payload:
        raise ValidationError(
            "At least one field must be provided."
        )

    result = {}

    if "status" in payload:
        status = _clean_string(payload["status"])

        if status not in CUSTOMER_STATUSES:
            raise ValidationError(
                "Invalid customer status.",
                {
                    "field": "status",
                    "allowed": list(CUSTOMER_STATUSES),
                },
            )

        result["status"] = status

    if "name" in payload:
        name = _clean_string(payload["name"])

        if not name:
            raise ValidationError(
                "Customer name cannot be empty."
            )

        if len(name) > 255:
            raise ValidationError(
                "Customer name is too long."
            )

        result["name"] = name

    if "country" in payload:
        country = _clean_string(payload["country"])

        if country and len(country) > 100:
            raise ValidationError(
                "Country is too long."
            )

        result["country"] = country or ""

    return result


def validate_bulk_update_customers(payload):
    if not isinstance(payload, dict):
        raise ValidationError(
            "Request body must be a JSON object."
        )

    ids = payload.get("ids")

    if not isinstance(ids, list) or not ids:
        raise ValidationError(
            "The 'ids' field must be a non-empty array."
        )

    normalized_ids = []

    for customer_id in ids:
        if customer_id is None:
            continue

        customer_id = str(customer_id).strip()

        if customer_id:
            normalized_ids.append(customer_id)

    if not normalized_ids:
        raise ValidationError(
            "At least one valid customer ID is required."
        )

    if len(normalized_ids) != len(set(normalized_ids)):
        normalized_ids = list(dict.fromkeys(normalized_ids))

    status = _clean_string(payload.get("status"))

    if status not in CUSTOMER_STATUSES:
        raise ValidationError(
            "A valid customer status is required.",
            {
                "field": "status",
                "allowed": list(CUSTOMER_STATUSES),
            },
        )

    return {
        "ids": normalized_ids,
        "status": status,
    }


def validate_bulk_email_customers(payload):
    if not isinstance(payload, dict):
        raise ValidationError(
            "Request body must be a JSON object."
        )

    ids = payload.get("ids")

    if not isinstance(ids, list) or not ids:
        raise ValidationError(
            "The 'ids' field must be a non-empty array."
        )

    normalized_ids = [
        str(value).strip()
        for value in ids
        if value is not None and str(value).strip()
    ]

    if not normalized_ids:
        raise ValidationError(
            "At least one valid customer ID is required."
        )

    subject = _clean_string(
        payload.get("subject")
    )

    body = _clean_string(
        payload.get("body")
    )

    if body and len(body) > 10000:
        raise ValidationError(
            "Email body is too long."
        )

    if subject and len(subject) > 255:
        raise ValidationError(
            "Email subject is too long."
        )

    return {
        "ids": list(dict.fromkeys(normalized_ids)),
        "subject": subject,
        "body": body,
    }


def validate_message_customer(payload):
    if not isinstance(payload, dict):
        raise ValidationError(
            "Request body must be a JSON object."
        )

    body = _clean_string(payload.get("body"))

    if not body:
        raise ValidationError(
            "Message body is required."
        )

    if len(body) > 10000:
        raise ValidationError(
            "Message body is too long."
        )

    subject = _clean_string(
        payload.get("subject")
    )

    if subject and len(subject) > 255:
        raise ValidationError(
            "Message subject is too long."
        )

    return {
        "subject": subject,
        "body": body,
    }