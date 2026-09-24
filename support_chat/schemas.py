# support_chat/schemas.py

from support_chat.constants import MAX_MESSAGE_LENGTH, MAX_SUBJECT_LENGTH
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
