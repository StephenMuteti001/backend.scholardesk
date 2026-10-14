# customer_orders/schemas.py

import re

from customer_orders.constants import (
    DEFAULT_CURRENCY,
    DEFAULT_PAGE,
    DEFAULT_PER_PAGE,
    MAX_PER_PAGE,
    ORDER_LIST_STATUSES,
    ORDER_STAGES,
)
from utils.exceptions import ValidationError

MAX_TITLE_LENGTH = 255
MAX_INSTRUCTIONS_LENGTH = 20_000
MAX_FILES = 20


def _string(value, field, *, required=False, max_length=None):
    if value is None:
        if required:
            raise ValidationError(
                f"{field} is required.", {"field": field}
            )
        return None

    if not isinstance(value, str):
        raise ValidationError(
            f"{field} must be a string.", {"field": field}
        )

    value = value.strip()

    if required and not value:
        raise ValidationError(
            f"{field} cannot be empty.", {"field": field}
        )

    if max_length and len(value) > max_length:
        raise ValidationError(
            f"{field} must not exceed {max_length} characters.",
            {"field": field},
        )

    return value or None


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

def validate_list_orders(args):
    try:
        page = int(args.get("page", DEFAULT_PAGE))
        per_page = int(args.get("per_page", DEFAULT_PER_PAGE))
    except (TypeError, ValueError):
        raise ValidationError("page and per_page must be integers.")

    if page < 1:
        raise ValidationError("page must be at least 1.")

    per_page = min(max(per_page, 1), MAX_PER_PAGE)

    stage = args.get("stage")
    status = args.get("status")
    search = args.get("search")

    if stage:
        stage = stage.strip() or None

    if stage and stage not in ORDER_STAGES:
        raise ValidationError(
            f"stage must be one of: {', '.join(ORDER_STAGES)}.",
            {"field": "stage"},
        )

    if status:
        status = status.strip().lower() or None

    if status and status not in ORDER_LIST_STATUSES:
        raise ValidationError(
            f"status must be one of: {', '.join(ORDER_LIST_STATUSES)}.",
            {"field": "status"},
        )

    if search:
        search = search.strip() or None

    return {
        "page": page,
        "per_page": per_page,
        "stage": stage,
        "status": status,
        "search": search,
    }


# ---------------------------------------------------------------------------
# CREATE (quote request)
# ---------------------------------------------------------------------------

def validate_quote_request(payload):
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be an object.")

    full_name = _string(payload.get("fullName"), "fullName", max_length=255)
    email = _string(payload.get("email"), "email", max_length=255)

    title = _string(
        payload.get("title"), "title", required=True, max_length=MAX_TITLE_LENGTH
    )
    subject = _string(payload.get("subject"), "subject", max_length=255)
    assignment_type = _string(
        payload.get("assignmentType"), "assignmentType", max_length=255
    )

    word_count = payload.get("wordCount")

    if word_count is not None:
        try:
            word_count = int(word_count)
        except (TypeError, ValueError):
            raise ValidationError(
                "wordCount must be an integer.", {"field": "wordCount"}
            )

        if word_count < 0:
            raise ValidationError(
                "wordCount cannot be negative.", {"field": "wordCount"}
            )

    citation_style = _string(
        payload.get("citationStyle"), "citationStyle", max_length=50
    )

    deadline = _string(payload.get("deadline"), "deadline", required=True)

    instructions = _string(
        payload.get("instructions"),
        "instructions",
        max_length=MAX_INSTRUCTIONS_LENGTH,
    )

    file_names = payload.get("fileNames") or []

    if not isinstance(file_names, list) or not all(
        isinstance(name, str) for name in file_names
    ):
        raise ValidationError(
            "fileNames must be an array of strings.",
            {"field": "fileNames"},
        )

    if len(file_names) > MAX_FILES:
        raise ValidationError(
            f"A maximum of {MAX_FILES} files may be attached.",
            {"field": "fileNames"},
        )

    request_type = _string(payload.get("type"), "type") or None

    return {
        "full_name": full_name,
        "email": email,
        "title": title,
        "subject": subject,
        "assignment_type": assignment_type,
        "word_count": word_count,
        "citation_style": citation_style,
        "deadline": deadline,
        "instructions": instructions,
        "file_names": file_names,
        "request_type": request_type,
    }


# ---------------------------------------------------------------------------
# UPDATE (edit brief)
# ---------------------------------------------------------------------------

def validate_update_order(payload):
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be an object.")

    fields = {}

    if "title" in payload:
        fields["title"] = _string(
            payload.get("title"),
            "title",
            required=True,
            max_length=MAX_TITLE_LENGTH,
        )

    if "subject" in payload:
        fields["subject"] = _string(
            payload.get("subject"), "subject", max_length=255
        )

    if "assignmentType" in payload:
        fields["assignment_type"] = _string(
            payload.get("assignmentType"),
            "assignmentType",
            max_length=255,
        )

    if "wordCount" in payload:
        word_count = payload.get("wordCount")

        if word_count is not None:
            try:
                word_count = int(word_count)
            except (TypeError, ValueError):
                raise ValidationError(
                    "wordCount must be an integer.",
                    {"field": "wordCount"},
                )

        fields["word_count"] = word_count

    if "citationStyle" in payload:
        fields["citation_style"] = _string(
            payload.get("citationStyle"), "citationStyle", max_length=50
        )

    if "deadline" in payload:
        fields["deadline"] = _string(
            payload.get("deadline"), "deadline", required=True
        )

    if "instructions" in payload:
        fields["instructions"] = _string(
            payload.get("instructions"),
            "instructions",
            max_length=MAX_INSTRUCTIONS_LENGTH,
        )

    if not fields:
        raise ValidationError("No editable fields were provided.")

    return fields


# ---------------------------------------------------------------------------
# PAYMENTS
# ---------------------------------------------------------------------------

def validate_pay_order(payload):
    """
    The pay endpoint takes no meaningful input any more: the amount
    comes from the Order and settlement from Paystack. Anything the
    client sends is ignored; only the body's type is checked so a
    malformed body is still a clean 422.
    """
    payload = payload or {}

    if not isinstance(payload, dict):
        raise ValidationError("Request body must be an object.")

    return {}


_PAYMENT_REFERENCE_RE = re.compile(r"^[A-Z0-9-]{6,64}$")


def validate_payment_reference(reference):
    reference = (reference or "").strip().upper()

    if not _PAYMENT_REFERENCE_RE.match(reference):
        raise ValidationError("Invalid payment reference.")

    return reference


# ---------------------------------------------------------------------------
# CANCEL / REFUND
# ---------------------------------------------------------------------------

def validate_reason_payload(payload):
    payload = payload or {}

    if not isinstance(payload, dict):
        raise ValidationError("Request body must be an object.")

    return {"reason": _string(payload.get("reason"), "reason")}


def validate_counter_quote(payload):
    payload = payload or {}

    if not isinstance(payload, dict):
        raise ValidationError("Request body must be an object.")

    amount = payload.get("amount")

    if amount is None:
        raise ValidationError(
            "amount is required.", {"field": "amount"}
        )

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise ValidationError(
            "amount must be numeric.", {"field": "amount"}
        )

    if amount <= 0:
        raise ValidationError(
            "amount must be greater than zero.", {"field": "amount"}
        )

    notes = _string(payload.get("notes"), "notes", max_length=2_000)

    return {"amount": amount, "notes": notes}


# ---------------------------------------------------------------------------
# SUBMISSIONS: revision requests / approval
# ---------------------------------------------------------------------------

def validate_revision_request(payload):
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be an object.")

    note = _string(
        payload.get("note"), "note", required=True, max_length=5_000
    )

    return {"note": note}
