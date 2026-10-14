import uuid as uuid_module

from marshmallow import (
    Schema,
    ValidationError,
    fields,
    validate,
    validates,
    validates_schema,
)

from utils.exceptions import ValidationError as AppValidationError


EXPERT_STATUSES = (
    "active",
    "onboarding",
    "paused",
    "offboarded",
)


def validate_specialities(value):
    if not value:
        raise ValidationError(
            "At least one speciality must be provided."
        )

    if len(value) > 30:
        raise ValidationError(
            "Too many specialities supplied."
        )


class ExpertSchema(Schema):
    """
    Response schema.
    """

    id = fields.UUID(dump_only=True)

    name = fields.String(dump_only=True)

    first_name = fields.String(required=True)

    last_name = fields.String(required=True)

    email = fields.Email(required=True)

    phone = fields.String(allow_none=True)

    avatar = fields.String(allow_none=True)

    bio = fields.String(allow_none=True)

    title = fields.String(allow_none=True)

    highest_qualification = fields.String(
        allow_none=True
    )

    years_of_experience = fields.Integer()

    hourly_rate = fields.Decimal(
        places=2,
        as_string=False,
        allow_none=True,
    )

    timezone = fields.String(
        allow_none=True
    )

    languages = fields.List(
        fields.String(),
        load_default=list,
    )

    specialities = fields.List(
        fields.String(),
        required=True,
        validate=validate_specialities,
    )

    certifications = fields.List(
        fields.String(),
        load_default=list,
    )

    status = fields.String(
        validate=validate.OneOf(EXPERT_STATUSES)
    )

    is_verified = fields.Boolean()

    is_available = fields.Boolean()

    rating = fields.Float(
        dump_only=True,
    )

    active_jobs = fields.Integer(
        dump_only=True,
    )

    completed = fields.Integer(
        dump_only=True,
    )

    payout_due = fields.Float(
        dump_only=True,
    )

    joined_at = fields.DateTime(
        dump_only=True,
    )

    created_at = fields.DateTime(
        dump_only=True,
    )

    updated_at = fields.DateTime(
        dump_only=True,
    )


class CreateExpertSchema(Schema):
    """
    POST /experts
    """

    first_name = fields.String(
        required=True,
        validate=validate.Length(
            min=2,
            max=100,
        ),
    )

    last_name = fields.String(
        required=True,
        validate=validate.Length(
            min=2,
            max=100,
        ),
    )

    email = fields.Email(
        required=True,
    )

    phone = fields.String()

    avatar = fields.String()

    bio = fields.String()

    title = fields.String()

    highest_qualification = fields.String()

    years_of_experience = fields.Integer(
        load_default=0,
    )

    hourly_rate = fields.Decimal(
        places=2,
        as_string=False,
        allow_none=True,
    )

    timezone = fields.String()

    languages = fields.List(
        fields.String(),
        load_default=list,
    )

    specialities = fields.List(
        fields.String(),
        required=True,
        validate=validate_specialities,
    )

    certifications = fields.List(
        fields.String(),
        load_default=list,
    )

    status = fields.String(
        load_default="onboarding",
        validate=validate.OneOf(EXPERT_STATUSES),
    )

    is_verified = fields.Boolean(
        load_default=False,
    )

    is_available = fields.Boolean(
        load_default=True,
    )

    @validates("years_of_experience")
    def validate_years(self, value, **kwargs):
        if value < 0:
            raise ValidationError(
                "Years of experience cannot be negative."
            )


class UpdateExpertSchema(Schema):
    """
    PATCH /experts/<id>
    """

    first_name = fields.String()

    last_name = fields.String()

    email = fields.Email()

    phone = fields.String(
        allow_none=True,
    )

    avatar = fields.String(
        allow_none=True,
    )

    bio = fields.String(
        allow_none=True,
    )

    title = fields.String(
        allow_none=True,
    )

    highest_qualification = fields.String(
        allow_none=True,
    )

    years_of_experience = fields.Integer()

    hourly_rate = fields.Decimal(
        places=2,
        as_string=False,
        allow_none=True,
    )

    timezone = fields.String(
        allow_none=True,
    )

    languages = fields.List(
        fields.String(),
    )

    specialities = fields.List(
        fields.String(),
    )

    certifications = fields.List(
        fields.String(),
    )

    status = fields.String(
        validate=validate.OneOf(EXPERT_STATUSES),
    )

    is_verified = fields.Boolean()

    is_available = fields.Boolean()

    @validates_schema
    def validate_payload(self, data, **kwargs):
        if not data:
            raise ValidationError(
                "No fields supplied for update."
            )

        if (
            "specialities" in data
            and not data["specialities"]
        ):
            raise ValidationError(
                "Specialities cannot be empty.",
                "specialities",
            )


class ExpertStatusSchema(Schema):
    """
    PATCH /experts/<id>/status
    """

    status = fields.String(
        required=True,
        validate=validate.OneOf(EXPERT_STATUSES),
    )


#
# Ready-to-use instances
#

expert_schema = ExpertSchema()

experts_schema = ExpertSchema(
    many=True,
)

create_expert_schema = CreateExpertSchema()

update_expert_schema = UpdateExpertSchema()

expert_status_schema = ExpertStatusSchema()

# ---------------------------------------------------------------------------
# Bulk status / bulk delete
#
# Plain functions (not marshmallow) raising the project's
# utils.exceptions.ValidationError, matching the style used by other
# modules' schemas.py (e.g. customers/schemas.py::validate_bulk_update_customers)
# so a bad payload here goes through the same global error-response
# path (422 VALIDATION_ERROR) instead of the bare `payload["ids"]`
# KeyError these two routes used to raise straight from Flask's index.
# ---------------------------------------------------------------------------

def _normalized_id_list(ids):
    if not isinstance(ids, list) or not ids:
        raise AppValidationError(
            "The 'ids' field must be a non-empty array.",
            {"field": "ids"},
        )

    normalized = []

    for value in ids:
        if value is None:
            continue

        value = str(value).strip()

        if not value:
            continue

        try:
            uuid_module.UUID(value)
        except (ValueError, AttributeError, TypeError):
            raise AppValidationError(
                "ids must contain valid expert IDs.",
                {"field": "ids"},
            )

        normalized.append(value)

    if not normalized:
        raise AppValidationError(
            "At least one valid expert ID is required.",
            {"field": "ids"},
        )

    return list(dict.fromkeys(normalized))


def validate_bulk_status(payload):
    if not isinstance(payload, dict):
        raise AppValidationError("Request body must be an object.")

    ids = _normalized_id_list(payload.get("ids"))

    status = payload.get("status")

    if not isinstance(status, str) or status not in EXPERT_STATUSES:
        raise AppValidationError(
            f"status must be one of: {', '.join(EXPERT_STATUSES)}.",
            {"field": "status"},
        )

    return {"ids": ids, "status": status}


def validate_bulk_ids(payload):
    if not isinstance(payload, dict):
        raise AppValidationError("Request body must be an object.")

    return {"ids": _normalized_id_list(payload.get("ids"))}
