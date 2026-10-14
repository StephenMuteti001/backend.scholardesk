# support_chat/schemas.py

from support_chat.constants import (
    MAX_MESSAGE_LENGTH,
    MAX_PER_PAGE,
    MAX_SUBJECT_LENGTH,
)
from utils.exceptions import ValidationError


def validate_start_thread(payload):
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be an object.")

    subject = payload.get("subject")

    if not subject or not isinstance(subject, str) or not subject.strip():
        raise ValidationError(
            "subject is required.", {"field": "subject"}
        )

    subject = subject.strip()

    if len(subject) > MAX_SUBJECT_LENGTH:
        raise ValidationError(
            f"subject must not exceed {MAX_SUBJECT_LENGTH} characters.",
            {"field": "subject"},
        )

    order_reference = payload.get("orderReference") or payload.get(
        "order_reference"
    )

    if order_reference is not None:
        order_reference = str(order_reference).strip() or None

    return {"subject": subject, "order_reference": order_reference}


def validate_send_message(payload):
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be an object.")

    body = payload.get("body")

    if not body or not isinstance(body, str) or not body.strip():
        raise ValidationError("body is required.", {"field": "body"})

    body = body.strip()

    if len(body) > MAX_MESSAGE_LENGTH:
        raise ValidationError(
            f"body must not exceed {MAX_MESSAGE_LENGTH} characters.",
            {"field": "body"},
        )

    return {"body": body}


def validate_pagination(args):
    """
    page/per_page are optional on the thread and message list routes -
    when neither is supplied the existing "return everything" shape
    is preserved (list_threads()/list_messages() just cap it at a
    sane maximum instead), so old frontend callers see no change.
    """
    page = args.get("page")
    per_page = args.get("per_page")

    if page is not None:
        try:
            page = int(page)
        except (TypeError, ValueError):
            raise ValidationError(
                "page must be an integer.", {"field": "page"}
            )

        if page < 1:
            raise ValidationError(
                "page must be at least 1.", {"field": "page"}
            )

    if per_page is not None:
        try:
            per_page = int(per_page)
        except (TypeError, ValueError):
            raise ValidationError(
                "per_page must be an integer.", {"field": "per_page"}
            )

        if per_page < 1:
            raise ValidationError(
                "per_page must be at least 1.", {"field": "per_page"}
            )

        per_page = min(per_page, MAX_PER_PAGE)

    return {"page": page, "per_page": per_page}
