# integrity_reports/schemas.py

from integrity_reports.constants import MAX_FILE_NAME_LENGTH, MAX_WORD_COUNT
from utils.exceptions import ValidationError


def validate_scan_request(payload, files):
    """
    Accepts either a JSON body:

        { "fileName": "...", "wordCount": 1234,
          "checks": { "ai": true, "plagiarism": true } }

    or multipart/form-data with the file itself under `file` plus
    `checks[ai]` / `checks[plagiarism]` form fields - `files` is the
    request.files MultiDict, empty for the JSON-only path.
    """

    uploaded_file = files.get("file")

    if uploaded_file:
        file_name = uploaded_file.filename or ""
        word_count = payload.get("wordCount") or payload.get("word_count")
        check_ai = _to_bool(
            payload.get("checks[ai]", payload.get("checkAi", True))
        )
        check_plagiarism = _to_bool(
            payload.get(
                "checks[plagiarism]", payload.get("checkPlagiarism", True)
            )
        )
    else:
        if not isinstance(payload, dict):
            raise ValidationError("Request body must be an object.")

        file_name = payload.get("fileName") or payload.get("file_name")
        word_count = payload.get("wordCount", payload.get("word_count"))
        checks = payload.get("checks") or {}

        if not isinstance(checks, dict):
            raise ValidationError(
                "checks must be an object with ai/plagiarism booleans.",
                {"field": "checks"},
            )

        check_ai = _to_bool(checks.get("ai", True))
        check_plagiarism = _to_bool(checks.get("plagiarism", True))

    if not file_name or not isinstance(file_name, str):
        raise ValidationError(
            "fileName is required.", {"field": "fileName"}
        )

    file_name = file_name.strip()

    if len(file_name) > MAX_FILE_NAME_LENGTH:
        raise ValidationError(
            f"fileName must not exceed {MAX_FILE_NAME_LENGTH} characters.",
            {"field": "fileName"},
        )

    try:
        word_count = int(word_count) if word_count is not None else 0
    except (TypeError, ValueError):
        raise ValidationError(
            "wordCount must be an integer.", {"field": "wordCount"}
        )

    if word_count < 0 or word_count > MAX_WORD_COUNT:
        raise ValidationError(
            f"wordCount must be between 0 and {MAX_WORD_COUNT}.",
            {"field": "wordCount"},
        )

    if not check_ai and not check_plagiarism:
        raise ValidationError(
            "At least one of checks.ai or checks.plagiarism must be true.",
            {"field": "checks"},
        )

    return {
        "file_name": file_name,
        "word_count": word_count,
        "check_ai": check_ai,
        "check_plagiarism": check_plagiarism,
        "uploaded_file": uploaded_file,
    }


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def validate_list_args(args):
    page = args.get("page", 1)
    per_page = args.get("per_page", 20)

    try:
        page = int(page)
        per_page = int(per_page)
    except (TypeError, ValueError):
        raise ValidationError("page and per_page must be integers.")

    if page < 1:
        raise ValidationError("page must be at least 1.")

    per_page = min(max(per_page, 1), 100)

    return {"page": page, "per_page": per_page}
