# submissions/schemas.py

from submissions.constants import MAX_FILES, MAX_NOTE_LENGTH
from utils.exceptions import ValidationError


def validate_create_submission(form, files):
    """
    Validate a POST /orders/{order_id}/submissions payload.

    The expert portal sends this as multipart/form-data (see
    src/routes/orders.$orderId.submit.tsx in the expert-portal
    frontend repo): a `note` text field plus one or more `files[]`
    attachments. At least one file is required - the frontend itself
    blocks submission without one, but the API enforces it too.
    """

    note = (form.get("note") or "").strip()

    if len(note) > MAX_NOTE_LENGTH:
        raise ValidationError(
            f"note must not exceed {MAX_NOTE_LENGTH} characters.",
            {"field": "note"},
        )

    file_list = [f for f in (files or []) if f and f.filename]

    if not file_list:
        raise ValidationError(
            "At least one file is required.",
            {"field": "files"},
        )

    if len(file_list) > MAX_FILES:
        raise ValidationError(
            f"A maximum of {MAX_FILES} files may be attached.",
            {"field": "files"},
        )

    return {
        "note": note or None,
        "files": file_list,
    }
