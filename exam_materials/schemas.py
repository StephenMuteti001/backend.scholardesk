from marshmallow import (
    Schema,
    fields,
    validate,
    validates_schema,
    ValidationError,
)


MATERIAL_STATUSES = [
    "draft",
    "in-review",
    "published",
    "archived",
]


class ExamMaterialCreateSchema(Schema):
    title = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=255),
    )

    description = fields.Str(
        allow_none=True,
    )

    exam = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=100),
    )

    subject = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=100),
    )

    expert_id = fields.Str(
        allow_none=True,
    )

    price = fields.Decimal(
        required=False,
        places=2,
        as_string=False,
        validate=validate.Range(min=0),
        load_default=0,
    )


class ExamMaterialUpdateSchema(Schema):
    title = fields.Str(
        validate=validate.Length(min=1, max=255),
    )

    description = fields.Str(
        allow_none=True,
    )

    exam = fields.Str(
        validate=validate.Length(min=1, max=100),
    )

    subject = fields.Str(
        validate=validate.Length(min=1, max=100),
    )

    expert_id = fields.Str(
        allow_none=True,
    )

    price = fields.Decimal(
        places=2,
        as_string=False,
        validate=validate.Range(min=0),
    )


class ExamMaterialStatusSchema(Schema):
    status = fields.Str(
        required=True,
        validate=validate.OneOf(MATERIAL_STATUSES),
    )


class ExamMaterialListQuerySchema(Schema):
    page = fields.Int(
        load_default=1,
        validate=validate.Range(min=1),
    )

    per_page = fields.Int(
        load_default=20,
        validate=validate.Range(min=1, max=100),
    )

    search = fields.Str(
        load_default="",
        allow_none=True,
    )

    status = fields.Str(
        allow_none=True,
        validate=validate.OneOf(MATERIAL_STATUSES),
    )

    exam = fields.Str(
        allow_none=True,
    )

    subject = fields.Str(
        allow_none=True,
    )

    expert_id = fields.Str(
        allow_none=True,
    )

    sort_by = fields.Str(
        load_default="created_at",
    )

    direction = fields.Str(
        load_default="desc",
        validate=validate.OneOf(["asc", "desc"]),
    )


class BulkExamMaterialUpdateSchema(Schema):
    ids = fields.List(
        fields.Str(),
        required=True,
        validate=validate.Length(min=1),
    )

    status = fields.Str(
        validate=validate.OneOf(MATERIAL_STATUSES),
    )

    expert_id = fields.Str(
        allow_none=True,
    )

    price = fields.Decimal(
        places=2,
        as_string=False,
        validate=validate.Range(min=0),
    )

    @validates_schema
    def validate_update_fields(self, data, **kwargs):
        update_fields = {
            key
            for key in data
            if key != "ids"
        }

        if not update_fields:
            raise ValidationError(
                "At least one update field is required."
            )


class BulkExamMaterialDeleteSchema(Schema):
    ids = fields.List(
        fields.Str(),
        required=True,
        validate=validate.Length(min=1),
    )


class ExamMaterialUploadSchema(Schema):
    file_name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=255),
    )

    file_size = fields.Int(
        required=True,
        validate=validate.Range(min=1),
    )

    mime_type = fields.Str(
        required=True,
        validate=validate.Length(max=100),
    )

    storage_key = fields.Str(
        required=True,
    )

    file_url = fields.Str(
        allow_none=True,
    )

    page_count = fields.Int(
        allow_none=True,
        validate=validate.Range(min=1),
    )

class ExamMaterialDTO:
    @staticmethod
    def serialize(material):
        return {
            "id": str(material.id),
            "title": material.title,
            "description": material.description,

            "exam": material.exam,
            "subject": material.subject,

            "expert_id": str(material.expert_id) if material.expert_id else None,

            "author": (
                material.expert.name
                if material.expert
                else None
            ),

            "status": material.status,

            "price": float(material.price or 0),
            "downloads": material.downloads or 0,
            "revenue": float(material.revenue or 0),

            "file_url": material.file_url,
            "file_name": material.file_name,
            "file_size": material.file_size,
            "mime_type": material.mime_type,
            "storage_key": material.storage_key,

            "page_count": material.page_count,

            # frontend-friendly aliases
            "pages": material.page_count,
            "format": material.mime_type,

            "reviewed_by": material.reviewed_by,
            "reviewed_at": (
                material.reviewed_at.isoformat()
                if material.reviewed_at
                else None
            ),

            "published_at": (
                material.published_at.isoformat()
                if material.published_at
                else None
            ),

            "archived_at": (
                material.archived_at.isoformat()
                if material.archived_at
                else None
            ),

            "created_at": material.created_at.isoformat()
            if material.created_at
            else None,

            "updated_at": material.updated_at.isoformat()
            if material.updated_at
            else None,

            # frontend-friendly alias
            "updatedAt": (
                material.updated_at.isoformat()
                if material.updated_at
                else None
            ),
        }

# ---------------------------------------------------------------------------
# Plain function validators
#
# exam_materials/routes.py was written against these function-style
# validators (matching the convention used by every other module -
# customers/schemas.py, requests/schemas.py, etc: a plain function
# that raises on bad input and returns a clean dict/list), not the
# Marshmallow schema classes above, which nothing else in the app
# references. Without these, importing exam_materials.routes raised
# ImportError and the whole app failed to start. Kept in the same
# file as the existing schema classes to avoid disturbing anything
# that might import those directly.
# ---------------------------------------------------------------------------

from utils.exceptions import ValidationError as AppValidationError

EXAM_MATERIAL_EDITABLE_FIELDS = (
    "title",
    "description",
    "exam",
    "subject",
    "expert_id",
    "price",
)

EXAM_MATERIAL_SORT_FIELDS = {
    "created_at",
    "updated_at",
    "title",
    "price",
    "downloads",
    "revenue",
}


def _clean_editable_payload(payload):
    if not isinstance(payload, dict):
        raise AppValidationError("Request body must be an object.")

    return {
        field: payload[field]
        for field in EXAM_MATERIAL_EDITABLE_FIELDS
        if field in payload
    }


def validate_create_exam_material(payload):
    if not isinstance(payload, dict):
        raise AppValidationError("Request body must be an object.")

    for field in ("title", "exam", "subject"):
        value = payload.get(field)

        if not value or not isinstance(value, str) or not value.strip():
            raise AppValidationError(
                f"{field} is required.", {"field": field}
            )

    return _clean_editable_payload(payload)


def validate_update_exam_material(payload):
    cleaned = _clean_editable_payload(payload)

    if not cleaned:
        raise AppValidationError("No editable fields were provided.")

    return cleaned


def validate_list_exam_materials(args):
    try:
        page = int(args.get("page", 1))
        per_page = int(args.get("per_page", 20))
    except (TypeError, ValueError):
        raise AppValidationError("page and per_page must be integers.")

    if page < 1:
        raise AppValidationError("page must be at least 1.")

    per_page = min(max(per_page, 1), 100)

    sort_by = args.get("sort_by", "created_at")

    if sort_by not in EXAM_MATERIAL_SORT_FIELDS:
        raise AppValidationError(
            "Invalid sort field.",
            {"field": "sort_by", "allowed": sorted(EXAM_MATERIAL_SORT_FIELDS)},
        )

    direction = args.get("direction", "desc").lower()

    if direction not in {"asc", "desc"}:
        raise AppValidationError("direction must be either asc or desc.")

    return {
        "page": page,
        "per_page": per_page,
        "search": args.get("search") or None,
        "status": args.get("status") or None,
        "exam": args.get("exam") or None,
        "subject": args.get("subject") or None,
        "expert_id": args.get("expert_id") or None,
        "sort_by": sort_by,
        "direction": direction,
    }


def validate_bulk_update_exam_materials(payload):
    if not isinstance(payload, dict):
        raise AppValidationError("Request body must be an object.")

    return _clean_editable_payload(payload)


def validate_bulk_delete_exam_materials(payload):
    if not isinstance(payload, dict):
        raise AppValidationError("Request body must be an object.")

    ids = payload.get("ids")

    if not isinstance(ids, list) or not ids:
        raise AppValidationError(
            "ids must be a non-empty array.", {"field": "ids"}
        )

    if not all(isinstance(item, str) for item in ids):
        raise AppValidationError(
            "ids must be an array of strings.", {"field": "ids"}
        )

    return ids


def validate_attach_file(payload):
    if not isinstance(payload, dict):
        raise AppValidationError("Request body must be an object.")

    required_fields = ("file_name", "file_size", "mime_type", "storage_key")

    for field in required_fields:
        if not payload.get(field):
            raise AppValidationError(
                f"{field} is required.", {"field": field}
            )

    try:
        file_size = int(payload["file_size"])
    except (TypeError, ValueError):
        raise AppValidationError(
            "file_size must be an integer.", {"field": "file_size"}
        )

    if file_size < 0:
        raise AppValidationError("file_size cannot be negative.")

    return {
        "file_name": payload["file_name"],
        "file_size": file_size,
        "mime_type": payload["mime_type"],
        "storage_key": payload["storage_key"],
        "file_url": payload.get("file_url"),
        "page_count": payload.get("page_count"),
    }
