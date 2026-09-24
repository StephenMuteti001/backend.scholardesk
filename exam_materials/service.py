from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_

from users.user import User
from extensions import db
from experts.expert import Expert
from exam_materials.exam_material import ExamMaterial
from exam_materials.constants import (
    EDITABLE_FIELDS,
    MATERIAL_STATUSES,
    VALID_TRANSITIONS,
)
from utils.exceptions import ValidationError
from utils.transaction import transaction


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SORTABLE_FIELDS = {
    "title": ExamMaterial.title,
    "exam": ExamMaterial.exam,
    "subject": ExamMaterial.subject,
    "status": ExamMaterial.status,
    "price": ExamMaterial.price,
    "downloads": ExamMaterial.downloads,
    "revenue": ExamMaterial.revenue,
    "created_at": ExamMaterial.created_at,
    "updated_at": ExamMaterial.updated_at,
    "published_at": ExamMaterial.published_at,
    "archived_at": ExamMaterial.archived_at,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_material_or_raise(
    material_id: str,
) -> ExamMaterial:
    material = db.session.get(
        ExamMaterial,
        material_id,
    )

    if material is None:
        raise ValueError(
            "Exam material not found."
        )

    return material


def _validate_material_status(
    status: str,
) -> None:
    if status not in MATERIAL_STATUSES:
        raise ValueError(
            f"Invalid exam material status: '{status}'."
        )


def _validate_expert(
    expert_id: str | None,
) -> Expert | None:

    if expert_id is None:
        return None

    expert = db.session.get(
        Expert,
        expert_id,
    )

    if expert is None:
        raise ValueError(
            "Expert not found."
        )

    return expert


def _validate_user(
    user_id: str,
) -> User:

    user = db.session.get(
        User,
        user_id,
    )

    if user is None:
        raise ValueError(
            "User not found."
        )

    return user


def _validate_status_transition(
    current: str,
    target: str,
) -> None:

    _validate_material_status(target)

    if current == target:
        return

    allowed = VALID_TRANSITIONS.get(
        current,
        set(),
    )

    if target not in allowed:
        raise ValueError(
            f"Cannot transition material "
            f"from '{current}' to '{target}'."
        )


def _normalize_string(
    value: str | None,
) -> str | None:

    if value is None:
        return None

    return value.strip()


def _normalize_price(
    value,
) -> Decimal:

    if value is None:
        return Decimal("0.00")

    try:
        return Decimal(str(value))
    except Exception as exc:
        raise ValueError(
            "Invalid material price."
        ) from exc


def _validate_price(
    value,
) -> Decimal:

    price = _normalize_price(value)

    if price < Decimal("0.00"):
        raise ValueError(
            "Material price cannot be negative."
        )

    return price


def _validate_required_create_fields(
    payload: dict,
) -> None:

    required_fields = (
        "title",
        "exam",
        "subject",
    )

    for field in required_fields:
        value = payload.get(field)

        if value is None:
            raise ValueError(
                f"{field.replace('_', ' ').capitalize()} is required."
            )

        if isinstance(value, str) and not value.strip():
            raise ValueError(
                f"{field.replace('_', ' ').capitalize()} cannot be empty."
            )


def _apply_editable_fields(
    material: ExamMaterial,
    payload: dict,
) -> None:

    for field in EDITABLE_FIELDS:

        if field not in payload:
            continue

        value = payload[field]

        if field in {
            "title",
            "description",
            "exam",
            "subject",
        }:
            value = _normalize_string(value)

        if field == "price":
            value = _validate_price(value)

        setattr(
            material,
            field,
            value,
        )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_exam_material(
    payload: dict,
) -> ExamMaterial:

    _validate_required_create_fields(
        payload
    )

    title = _normalize_string(
        payload["title"]
    )

    exam = _normalize_string(
        payload["exam"]
    )

    subject = _normalize_string(
        payload["subject"]
    )

    description = _normalize_string(
        payload.get("description")
    )

    expert_id = payload.get(
        "expert_id"
    )

    price = _validate_price(
        payload.get(
            "price",
            Decimal("0.00"),
        )
    )

    with transaction():

        _validate_expert(
            expert_id
        )

        material = ExamMaterial(
            title=title,
            description=description,
            exam=exam,
            subject=subject,
            expert_id=expert_id,
            status="draft",
            price=price,
            downloads=0,
            revenue=Decimal("0.00"),
        )

        db.session.add(material)

        # Flush allows the generated ID/defaults to become
        # available before the transaction exits.
        db.session.flush()

    return material


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------

def get_exam_material(
    material_id: str,
) -> ExamMaterial:

    return _get_material_or_raise(
        material_id
    )


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def update_exam_material(
    material_id: str,
    payload: dict,
) -> ExamMaterial:

    with transaction():

        material = _get_material_or_raise(
            material_id
        )

        if "expert_id" in payload:
            _validate_expert(
                payload["expert_id"]
            )

        _apply_editable_fields(
            material,
            payload,
        )

        material.updated_at = datetime.utcnow()

        db.session.flush()

    return material


# ---------------------------------------------------------------------------
# Submit for review
# ---------------------------------------------------------------------------

def submit_for_review(
    material_id: str,
) -> ExamMaterial:

    with transaction():

        material = _get_material_or_raise(
            material_id
        )

        _validate_status_transition(
            material.status,
            "in-review",
        )

        if not material.file_url:
            raise ValueError(
                "A material must have an uploaded file "
                "before it can be submitted for review."
            )

        now = datetime.utcnow()

        material.status = "in-review"

        material.updated_at = now

        db.session.flush()

    return material


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

def publish_exam_material(
    material_id: str,
    reviewer_id: str,
) -> ExamMaterial:

    with transaction():

        material = _get_material_or_raise(
            material_id
        )

        _validate_status_transition(
            material.status,
            "published",
        )

        if not material.file_url:
            raise ValueError(
                "Cannot publish material without a file."
            )

        _validate_user(
            reviewer_id
        )

        now = datetime.utcnow()

        material.status = "published"

        material.reviewed_by = reviewer_id
        material.reviewed_at = now
        material.published_at = now

        material.archived_at = None

        material.updated_at = now

        db.session.flush()

    return material


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

def archive_exam_material(
    material_id: str,
) -> ExamMaterial:

    with transaction():

        material = _get_material_or_raise(
            material_id
        )

        _validate_status_transition(
            material.status,
            "archived",
        )

        now = datetime.utcnow()

        material.status = "archived"

        material.archived_at = now

        material.updated_at = now

        db.session.flush()

    return material


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_exam_material(
    material_id: str,
) -> None:

    with transaction():

        material = _get_material_or_raise(
            material_id
        )

        if material.status == "published":
            raise ValueError(
                "Published materials cannot be permanently deleted. "
                "Archive them instead."
            )

        db.session.delete(
            material
        )

        db.session.flush()


# ---------------------------------------------------------------------------
# Duplicate
# ---------------------------------------------------------------------------

def duplicate_exam_material(
    material_id: str,
) -> ExamMaterial:

    with transaction():

        original = _get_material_or_raise(
            material_id
        )

        duplicate = ExamMaterial(
            title=f"{original.title} (Copy)",

            description=original.description,

            exam=original.exam,
            subject=original.subject,

            expert_id=original.expert_id,

            status="draft",

            price=original.price,

            downloads=0,
            revenue=Decimal("0.00"),

            # Publication/review state is never copied.
            reviewed_by=None,
            reviewed_at=None,
            published_at=None,
            archived_at=None,

            # File/storage state is intentionally not copied.
            file_url=None,
            file_name=None,
            file_size=None,
            mime_type=None,
            storage_key=None,
            page_count=None,
        )

        db.session.add(
            duplicate
        )

        db.session.flush()

    return duplicate


# ---------------------------------------------------------------------------
# Attach file
# ---------------------------------------------------------------------------

def attach_file(
    material_id: str,
    payload: dict,
) -> ExamMaterial:

    required_fields = (
        "file_name",
        "file_size",
        "mime_type",
        "storage_key",
    )

    for field in required_fields:

        if not payload.get(field):
            raise ValueError(
                f"{field.replace('_', ' ').capitalize()} is required."
            )

    if payload["file_size"] < 0:
        raise ValueError(
            "File size cannot be negative."
        )

    with transaction():

        material = _get_material_or_raise(
            material_id
        )

        material.file_name = payload[
            "file_name"
        ]

        material.file_size = payload[
            "file_size"
        ]

        material.mime_type = payload[
            "mime_type"
        ]

        material.storage_key = payload[
            "storage_key"
        ]

        material.file_url = payload.get(
            "file_url"
        )

        material.page_count = payload.get(
            "page_count"
        )

        material.updated_at = datetime.utcnow()

        db.session.flush()

    return material


# ---------------------------------------------------------------------------
# List / search / filtering / pagination
# ---------------------------------------------------------------------------

def list_exam_materials(
    *,
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
    status: str | None = None,
    exam: str | None = None,
    subject: str | None = None,
    expert_id: str | None = None,
    sort_by: str = "created_at",
    direction: str = "desc",
):

    page = max(
        int(page),
        1,
    )

    per_page = max(
        min(int(per_page), 100),
        1,
    )

    query = ExamMaterial.query

    if search:

        search = search.strip()

        if search:

            term = f"%{search}%"

            query = query.filter(
                or_(
                    ExamMaterial.title.ilike(term),
                    ExamMaterial.description.ilike(term),
                    ExamMaterial.exam.ilike(term),
                    ExamMaterial.subject.ilike(term),
                )
            )

    if status:

        _validate_material_status(
            status
        )

        query = query.filter(
            ExamMaterial.status == status
        )

    if exam:

        query = query.filter(
            ExamMaterial.exam == exam
        )

    if subject:

        query = query.filter(
            ExamMaterial.subject == subject
        )

    if expert_id:

        query = query.filter(
            ExamMaterial.expert_id == expert_id
        )

    sort_column = SORTABLE_FIELDS.get(
        sort_by,
        ExamMaterial.created_at,
    )

    if direction.lower() == "asc":

        query = query.order_by(
            sort_column.asc()
        )

    else:

        query = query.order_by(
            sort_column.desc()
        )

    pagination = query.paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    return {
        "items": pagination.items,
        "pagination": {
            "page": pagination.page,
            "pages": pagination.pages,
            "total": pagination.total,
            "per_page": pagination.per_page,
        },
    }


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def get_exam_material_statistics():

    total = (
        db.session.query(
            func.count(
                ExamMaterial.id
            )
        )
        .scalar()
        or 0
    )

    published = (
        db.session.query(
            func.count(
                ExamMaterial.id
            )
        )
        .filter(
            ExamMaterial.status == "published"
        )
        .scalar()
        or 0
    )

    in_review = (
        db.session.query(
            func.count(
                ExamMaterial.id
            )
        )
        .filter(
            ExamMaterial.status == "in-review"
        )
        .scalar()
        or 0
    )

    revenue = (
        db.session.query(
            func.coalesce(
                func.sum(
                    ExamMaterial.revenue
                ),
                Decimal("0.00"),
            )
        )
        .scalar()
        or Decimal("0.00")
    )

    return {
        "total": total,
        "published": published,
        "in_review": in_review,
        "revenue": float(revenue),
    }


# ---------------------------------------------------------------------------
# Bulk update
# ---------------------------------------------------------------------------

def bulk_update_exam_materials(
    ids: list[str],
    payload: dict,
    actor_id: str,
) -> list[ExamMaterial]:

    if not ids:
        raise ValueError(
            "At least one material ID is required."
        )

    unique_ids = list(
        dict.fromkeys(ids)
    )

    with transaction():

        materials = (
            ExamMaterial.query
            .filter(
                ExamMaterial.id.in_(
                    unique_ids
                )
            )
            .all()
        )

        if len(materials) != len(
            unique_ids
        ):
            found_ids = {
                material.id
                for material in materials
            }

            missing_ids = [
                material_id
                for material_id in unique_ids
                if material_id not in found_ids
            ]

            raise ValueError(
                "One or more materials were not found: "
                + ", ".join(missing_ids)
            )

        status = payload.get(
            "status"
        )

        expert_id = payload.get(
            "expert_id"
        )

        price = payload.get(
            "price"
        )

        # ---------------------------------------------------------------
        # Validate everything BEFORE mutating anything.
        # ---------------------------------------------------------------

        if status:

            _validate_material_status(
                status
            )

            for material in materials:

                _validate_status_transition(
                    material.status,
                    status,
                )

                if (
                    status == "published"
                    and not material.file_url
                ):
                    raise ValueError(
                        f"Material '{material.title}' "
                        "cannot be published without a file."
                    )

        if status == "published":

            _validate_user(
                actor_id
            )

        if "expert_id" in payload:

            _validate_expert(
                expert_id
            )

        if "price" in payload:

            price = _validate_price(
                price
            )

        # ---------------------------------------------------------------
        # Apply changes only after every validation has succeeded.
        # ---------------------------------------------------------------

        now = datetime.utcnow()

        for material in materials:

            if status:

                material.status = status

                if status == "published":

                    material.reviewed_by = actor_id
                    material.reviewed_at = now
                    material.published_at = now
                    material.archived_at = None

                elif status == "archived":

                    material.archived_at = now

                elif status == "draft":

                    material.reviewed_by = None
                    material.reviewed_at = None
                    material.published_at = None
                    material.archived_at = None

                elif status == "in-review":

                    material.archived_at = None

            if "expert_id" in payload:

                material.expert_id = expert_id

            if "price" in payload:

                material.price = price

            material.updated_at = now

        db.session.flush()

    return materials


# ---------------------------------------------------------------------------
# Bulk delete
# ---------------------------------------------------------------------------

def bulk_delete_exam_materials(
    ids: list[str],
) -> int:

    if not ids:
        raise ValueError(
            "At least one material ID is required."
        )

    unique_ids = list(
        dict.fromkeys(ids)
    )

    with transaction():

        materials = (
            ExamMaterial.query
            .filter(
                ExamMaterial.id.in_(
                    unique_ids
                )
            )
            .all()
        )

        if len(materials) != len(
            unique_ids
        ):
            found_ids = {
                material.id
                for material in materials
            }

            missing_ids = [
                material_id
                for material_id in unique_ids
                if material_id not in found_ids
            ]

            raise ValueError(
                "One or more materials were not found: "
                + ", ".join(missing_ids)
            )

        for material in materials:

            if material.status == "published":

                raise ValueError(
                    f"Published material "
                    f"'{material.title}' cannot be deleted. "
                    "Archive it instead."
                )

        for material in materials:

            db.session.delete(
                material
            )

        db.session.flush()

    return len(materials)

# ---------------------------------------------------------------------------
# CUSTOMER PORTAL (additive) - list published materials + purchase.
#
# These are new capabilities for the customer-facing frontend and do
# not touch anything the admin routes/schemas above read or write.
# ---------------------------------------------------------------------------

def serialize_material_for_customer(material, owned_ids):
    return {
        "id": str(material.id),
        "title": material.title,
        "summary": material.description or "",
        "subject": material.subject,
        "level": material.level or "Undergraduate",
        "category": material.category or "Study guides",
        "institution": material.institution,
        "year": material.year,
        "pages": material.page_count or 0,
        "format": material.format or "PDF",
        "price": float(material.price or 0),
        "currency": material.currency or "USD",
        "rating": float(material.rating or 0),
        "downloads": material.downloads or 0,
        "owned": material.id in owned_ids,
        "downloadUrl": material.file_url if material.id in owned_ids else None,
    }


def _owned_material_ids(customer_id):
    from orders.order import Order

    rows = (
        db.session.query(Order.material_id)
        .filter(Order.customer_id == customer_id)
        .filter(Order.source_type == "material")
        .filter(Order.status == "paid")
        .all()
    )

    return {row.material_id for row in rows}


def list_materials_for_customer(user):
    """
    Every published material, unpaginated.

    Kept for callers (and the no-query-parameter case) that just want
    the full catalogue; search_materials_for_customer() below is the
    paginated form the storefront uses.
    """
    materials = (
        ExamMaterial.query.filter(ExamMaterial.status == "published")
        .order_by(
            ExamMaterial.created_at.desc(),
            ExamMaterial.id.asc(),
        )
        .all()
    )

    owned_ids = _owned_material_ids(user.id)

    return [
        serialize_material_for_customer(material, owned_ids)
        for material in materials
    ]


# Sort keys accepted on GET /exam-materials, matching MaterialFilters
# in the customer portal's src/lib/portal-data.ts. Every ordering ends
# on ExamMaterial.id so paging can never repeat or drop a row when two
# materials tie on the primary column.
CUSTOMER_MATERIAL_SORTS = ("popular", "newest", "price_low", "rating")


def _customer_material_order_by(sort):
    if sort == "newest":
        return (
            ExamMaterial.created_at.desc(),
            ExamMaterial.id.asc(),
        )

    if sort == "price_low":
        return (
            ExamMaterial.price.asc(),
            ExamMaterial.id.asc(),
        )

    if sort == "rating":
        return (
            ExamMaterial.rating.desc().nullslast(),
            ExamMaterial.downloads.desc().nullslast(),
            ExamMaterial.id.asc(),
        )

    # "popular" (the storefront default)
    return (
        ExamMaterial.downloads.desc().nullslast(),
        ExamMaterial.rating.desc().nullslast(),
        ExamMaterial.id.asc(),
    )


def search_materials_for_customer(
    user,
    q=None,
    subject=None,
    level=None,
    category=None,
    sort=None,
    page=1,
    per_page=12,
):
    page = max(int(page or 1), 1)
    per_page = min(max(int(per_page or 12), 1), 100)

    sort = (sort or "popular").strip().lower()

    if sort not in CUSTOMER_MATERIAL_SORTS:
        raise ValidationError(
            "sort must be one of: "
            f"{', '.join(CUSTOMER_MATERIAL_SORTS)}.",
            {"field": "sort"},
        )

    base = ExamMaterial.query.filter(ExamMaterial.status == "published")

    def _clean(value):
        value = (value or "").strip()

        # The storefront sends its "All ..." placeholder selections
        # through verbatim; those mean "no filter".
        if not value or value.lower().startswith("all "):
            return None

        return value

    subject = _clean(subject)
    level = _clean(level)
    category = _clean(category)

    if subject:
        base = base.filter(func.lower(ExamMaterial.subject) == subject.lower())

    if level:
        base = base.filter(func.lower(ExamMaterial.level) == level.lower())

    if category:
        base = base.filter(
            func.lower(ExamMaterial.category) == category.lower()
        )

    q = (q or "").strip()

    if q:
        term = f"%{q}%"

        base = base.filter(
            or_(
                ExamMaterial.title.ilike(term),
                ExamMaterial.description.ilike(term),
                ExamMaterial.subject.ilike(term),
                ExamMaterial.exam.ilike(term),
                ExamMaterial.institution.ilike(term),
            )
        )

    pagination = base.order_by(*_customer_material_order_by(sort)).paginate(
        page=page, per_page=per_page, error_out=False
    )

    owned_ids = _owned_material_ids(user.id)

    items = [
        serialize_material_for_customer(material, owned_ids)
        for material in pagination.items
    ]

    # Facets describe the whole published catalogue, not the current
    # page - otherwise the subject filter would collapse to whatever
    # happened to be on page one.
    subject_rows = (
        db.session.query(ExamMaterial.subject)
        .filter(ExamMaterial.status == "published")
        .filter(ExamMaterial.subject.isnot(None))
        .distinct()
        .all()
    )

    subjects = sorted(
        {row.subject.strip() for row in subject_rows if (row.subject or "").strip()}
    )

    last_page = max(1, pagination.pages or 1)

    return {
        "items": items,
        "meta": {
            "current_page": pagination.page,
            "last_page": last_page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "has_more": pagination.page < last_page,
            "facets": {"subjects": subjects},
        },
    }


def purchase_material(user, material_id):
    from orders.service import OrderService
    from utils.exceptions import ConflictError, NotFoundError

    material = db.session.get(ExamMaterial, material_id)

    if not material or material.status != "published":
        raise NotFoundError(
            "Exam material not found.", {"material_id": str(material_id)}
        )

    owned_ids = _owned_material_ids(user.id)

    if material.id in owned_ids:
        raise ConflictError("You already own this material.")

    order = OrderService.create_from_material(
        material_obj=material,
        customer_id=user.id,
        amount=material.price,
        gateway="Online Payment",
        currency=material.currency or "USD",
    )

    with transaction():
        material.downloads = (material.downloads or 0) + 1
        material.revenue = (material.revenue or 0) + material.price

        db.session.flush()

    return serialize_material_for_customer(
        material, owned_ids | {material.id}
    )
