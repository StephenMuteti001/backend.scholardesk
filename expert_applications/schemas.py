# expert_applications/schemas.py

from expert_applications.constants import (
    APPLICATION_SORT_FIELDS,
    APPLICATION_STATUSES,
    DEFAULT_PAGE,
    DEFAULT_PER_PAGE,
    DEFAULT_SORT_BY,
    DEFAULT_SORT_DIRECTION,
    MAX_DEGREE_CERTIFICATES,
    MAX_PER_PAGE,
    MAX_WORK_SAMPLES,
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

    return value or None


# ---------------------------------------------------------------------------
# LIST (admin)
# ---------------------------------------------------------------------------

def validate_list_applications(args):
    try:
        page = int(args.get("page", DEFAULT_PAGE))
        per_page = int(args.get("per_page", DEFAULT_PER_PAGE))
    except (TypeError, ValueError):
        raise ValidationError("page and per_page must be integers.")

    if page < 1:
        raise ValidationError("page must be at least 1.")

    per_page = min(max(per_page, 1), MAX_PER_PAGE)

    status = args.get("status")

    if status and status not in APPLICATION_STATUSES:
        raise ValidationError(
            "Invalid application status.",
            {
                "field": "status",
                "allowed": sorted(APPLICATION_STATUSES),
            },
        )

    search = args.get("search")

    if search:
        search = search.strip() or None

    sort_by = args.get("sort_by", DEFAULT_SORT_BY)

    if sort_by not in APPLICATION_SORT_FIELDS:
        raise ValidationError(
            "Invalid sort field.",
            {
                "field": "sort_by",
                "allowed": sorted(APPLICATION_SORT_FIELDS),
            },
        )

    direction = args.get("direction", DEFAULT_SORT_DIRECTION).lower()

    if direction not in {"asc", "desc"}:
        raise ValidationError("direction must be either asc or desc.")

    return {
        "page": page,
        "per_page": per_page,
        "status": status,
        "search": search,
        "sort_by": sort_by,
        "direction": direction,
    }


# ---------------------------------------------------------------------------
# APPLY (customer)
# ---------------------------------------------------------------------------

def validate_apply_payload(form):
    """
    Validate the multipart/form-data fields of an expert-application
    submission. `form` is a werkzeug ImmutableMultiDict (request.form).

    Accepts several historical/alternate key names for the same field
    (snake_case, camelCase, and the auth-portal frontend's own naming
    - see writer-onboarding.apply.tsx) since more than one caller has
    been built against this endpoint over time.
    """

    country = _string(form.get("country"), "country", max_length=100)
    city = _string(form.get("city"), "city", max_length=100)
    phone_number = _string(
        form.get("phone_number") or form.get("phoneNumber") or form.get("phone"),
        "phone_number",
        max_length=40,
    )

    education = _string(
        form.get("education") or form.get("education_level"),
        "education",
        required=True,
        max_length=255,
    )
    specialization = _string(
        form.get("specialization"),
        "specialization",
        max_length=255,
    )
    years_experience = _string(
        form.get("years_experience")
        or form.get("yearsExperience")
        or form.get("experience"),
        "years_experience",
        max_length=50,
    )

    selected_prompt = _string(
        form.get("selected_prompt") or form.get("selectedPrompt"),
        "selected_prompt",
        max_length=255,
    )
    prompt_response = _string(
        form.get("prompt_response") or form.get("promptResponse"),
        "prompt_response",
    )

    selected_essay_topic = _string(
        form.get("selected_essay_topic")
        or form.get("selectedEssayTopic")
        or form.get("essay_topic"),
        "selected_essay_topic",
        max_length=255,
    )

    essay_text = _string(
        form.get("essay_text") or form.get("essay"),
        "essay_text",
    )

    return {
        "country": country,
        "city": city,
        "phone_number": phone_number,
        "education": education,
        "specialization": specialization,
        "years_experience": years_experience,
        "selected_prompt": selected_prompt,
        "prompt_response": prompt_response,
        "selected_essay_topic": selected_essay_topic,
        "essay_text": essay_text,
    }


def validate_proficiency_answers(raw_value):
    """
    proficiency_answers is submitted as a JSON-encoded string inside
    the multipart form (there is no native "object" field type for
    multipart/form-data).

    The auth-portal frontend (writer-onboarding/apply) sends a plain
    JSON array, ordered by question index (answers[i] for each
    question in PROFICIENCY_QUESTIONS) rather than an object keyed by
    question id - both shapes are accepted and stored as-is; nothing
    downstream needs to key into this by question id today.
    """
    import json

    if not raw_value:
        return {}

    if isinstance(raw_value, (dict, list)):
        return raw_value

    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError):
        raise ValidationError(
            "proficiency_answers must be valid JSON.",
            {"field": "proficiency_answers"},
        )

    if not isinstance(parsed, (dict, list)):
        raise ValidationError(
            "proficiency_answers must be a JSON object or array.",
            {"field": "proficiency_answers"},
        )

    return parsed


# Minimum essay length the auth-portal form itself enforces per
# writing-prompt response (writer-onboarding.apply.tsx::stepValid).
# Re-checked here so the requirement holds regardless of caller.
MIN_WRITING_SAMPLE_LENGTH = 150


def validate_writing_samples(form):
    """
    The auth-portal form submits one field per writing prompt, named
    `sample_<promptId>` (see writer-data.ts::WRITING_PROMPTS and
    writer-onboarding.apply.tsx). Rather than hardcode the current
    two prompt ids, collect every `sample_*` field so this keeps
    working if the frontend's prompt list changes.
    """
    samples = {}

    for key in form.keys():
        if not key.startswith("sample_"):
            continue

        prompt_id = key[len("sample_"):]
        text = (form.get(key) or "").strip()

        if text:
            samples[prompt_id] = text

    for prompt_id, text in samples.items():
        if len(text) < MIN_WRITING_SAMPLE_LENGTH:
            raise ValidationError(
                f"Writing sample for '{prompt_id}' must be at least "
                f"{MIN_WRITING_SAMPLE_LENGTH} characters.",
                {"field": f"sample_{prompt_id}"},
            )

    return samples


def validate_file_counts(files):
    work_samples = files.getlist("work_samples") or files.getlist("workSamples")
    degree_certificates = (
        files.getlist("degree_certificates")
        or files.getlist("degreeCertificates")
    )

    if len(work_samples) > MAX_WORK_SAMPLES:
        raise ValidationError(
            f"A maximum of {MAX_WORK_SAMPLES} work samples may be uploaded.",
            {"field": "work_samples"},
        )

    if len(degree_certificates) > MAX_DEGREE_CERTIFICATES:
        raise ValidationError(
            f"A maximum of {MAX_DEGREE_CERTIFICATES} degree "
            "certificates may be uploaded.",
            {"field": "degree_certificates"},
        )

    return work_samples, degree_certificates


# ---------------------------------------------------------------------------
# REVIEW (admin) - approve / reject
# ---------------------------------------------------------------------------

def validate_review_payload(payload, *, feedback_required=False):
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be an object.")

    feedback = _string(payload.get("feedback"), "feedback")

    if feedback_required and not feedback:
        raise ValidationError(
            "feedback is required.",
            {"field": "feedback"},
        )

    return {"feedback": feedback}
