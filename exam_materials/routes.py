from flask import Blueprint, redirect, request, send_file
from utils.authorization import require_roles
from utils.roles import ADMIN_ROLES
from flask_jwt_extended import get_jwt_identity

from exam_materials.schemas import (
    validate_attach_file,
    validate_bulk_delete_exam_materials,
    validate_bulk_update_exam_materials,
    validate_create_exam_material,
    validate_list_exam_materials,
    validate_update_exam_material,
)
from exam_materials.service import (
    archive_exam_material,
    attach_file,
    attach_uploaded_file,
    resolve_material_download,
    bulk_delete_exam_materials,
    bulk_update_exam_materials,
    create_exam_material,
    delete_exam_material,
    duplicate_exam_material,
    get_exam_material,
    get_exam_material_statistics,
    list_exam_materials,
    publish_exam_material,
    submit_for_review,
    update_exam_material,
)
from utils.response_formatter import (
    error_response,
    success_response,
)
from utils.exceptions import ServiceError


# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------

exam_materials_bp = Blueprint(
    "exam_materials",
    __name__,
    url_prefix="/api/v1/admin/materials",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_current_user_id():
    """
    Retrieve the authenticated user's ID from the JWT.

    Authentication is intentionally kept out of individual route handlers
    so that route handlers remain focused on HTTP request/response handling.
    """
    return get_jwt_identity()


def _serialize_material(material):
    """
    Serialize an ExamMaterial model into the DTO expected by the frontend.

    The service layer returns domain models. Routes are responsible for
    converting those models into transport representations.
    """
    return {
        "id": str(material.id),
        "title": material.title,
        "description": material.description,
        "exam": material.exam,
        "subject": material.subject,
        "expert_id": str(material.expert_id) if material.expert_id else None,
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
        "created_at": (
            material.created_at.isoformat()
            if material.created_at
            else None
        ),
        "updated_at": (
            material.updated_at.isoformat()
            if material.updated_at
            else None
        ),
    }


def _serialize_material_list(result):
    """
    Serialize a paginated material list.
    """
    return {
        "items": [
            _serialize_material(material)
            for material in result["items"]
        ],
        "pagination": result["pagination"],
    }


def _handle_service_error(exc):
    """
    Convert known service exceptions into the application's standard
    response format.

    ValueError is currently used by the service layer for domain validation.
    Once the service layer is migrated fully to ServiceError subclasses,
    this handler can be narrowed accordingly.
    """
    if isinstance(exc, ServiceError):
        return error_response(
            exc.code,
            exc.message,
            exc.details,
            exc.status_code,
        )

    return error_response(
        "SERVICE_ERROR",
        str(exc),
        status=400,
    )


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@exam_materials_bp.get("")
@require_roles(*ADMIN_ROLES)
def list_materials():
    """
    GET /admin/exam-materials

    Supported query parameters:

        page
        per_page
        search
        status
        exam
        subject
        expert_id
        sort_by
        direction
    """
    try:
        params = validate_list_exam_materials(
            request.args
        )

        result = list_exam_materials(
            **params
        )

        return success_response(
            _serialize_material_list(result)
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# STATISTICS
# ---------------------------------------------------------------------------

@exam_materials_bp.get("/statistics")
@require_roles(*ADMIN_ROLES)
def material_statistics():
    """
    GET /admin/exam-materials/statistics
    """
    try:
        statistics = get_exam_material_statistics()

        return success_response(
            statistics
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

@exam_materials_bp.post("")
@require_roles(*ADMIN_ROLES)
def create_material():
    """
    POST /admin/exam-materials
    """
    try:
        # Multipart upload (the admin portal): store the binary locally.
        uploaded = request.files.get("file") if request.files else None
        if uploaded is not None:
            material = attach_uploaded_file(
                material_id,
                uploaded,
                request.form.get("page_count"),
            )
            return success_response(
                {"material": _serialize_material(material)},
                message="Material file attached successfully.",
            )

        payload = request.get_json(
            silent=True
        )

        if payload is None:
            return error_response(
                "INVALID_JSON",
                "Request body must contain valid JSON.",
                status=400,
            )

        payload = validate_create_exam_material(
            payload
        )

        material = create_exam_material(
            payload
        )

        return success_response(
            {
                "material": _serialize_material(
                    material
                )
            },
            message="Exam material created successfully.",
            status=201,
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# GET ONE
# ---------------------------------------------------------------------------

@exam_materials_bp.get("/<uuid:material_id>")
@require_roles(*ADMIN_ROLES)
def get_material(material_id):
    """
    GET /admin/exam-materials/<material_id>
    """
    try:
        material = get_exam_material(
            material_id
        )

        return success_response(
            {
                "material": _serialize_material(
                    material
                )
            }
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

@exam_materials_bp.patch("/<uuid:material_id>")
@require_roles(*ADMIN_ROLES)
def update_material(material_id):
    """
    PATCH /admin/exam-materials/<material_id>

    Updates material metadata only.

    Workflow transitions such as publishing, archiving, and submitting
    for review are handled by dedicated endpoints.
    """
    try:
        payload = request.get_json(
            silent=True
        )

        if payload is None:
            return error_response(
                "INVALID_JSON",
                "Request body must contain valid JSON.",
                status=400,
            )

        payload = validate_update_exam_material(
            payload
        )

        material = update_exam_material(
            material_id,
            payload,
        )

        return success_response(
            {
                "material": _serialize_material(
                    material
                )
            },
            message="Exam material updated successfully.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# DELETE ONE
# ---------------------------------------------------------------------------

@exam_materials_bp.delete("/<uuid:material_id>")
@require_roles(*ADMIN_ROLES)
def delete_material(material_id):
    """
    DELETE /admin/exam-materials/<material_id>
    """
    try:
        delete_exam_material(
            material_id
        )

        return success_response(
            message="Exam material deleted successfully."
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# DUPLICATE
# ---------------------------------------------------------------------------

@exam_materials_bp.post(
    "/<uuid:material_id>/duplicate"
)
@require_roles(*ADMIN_ROLES)
def duplicate_material(material_id):
    """
    POST /admin/exam-materials/<material_id>/duplicate
    """
    try:
        material = duplicate_exam_material(
            material_id
        )

        return success_response(
            {
                "material": _serialize_material(
                    material
                )
            },
            message="Exam material duplicated successfully.",
            status=201,
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# SUBMIT FOR REVIEW
# ---------------------------------------------------------------------------

@exam_materials_bp.post(
    "/<uuid:material_id>/submit-review"
)
@require_roles(*ADMIN_ROLES)
def submit_material_for_review(material_id):
    """
    POST /admin/exam-materials/<material_id>/submit-review
    """
    try:
        material = submit_for_review(
            material_id
        )

        return success_response(
            {
                "material": _serialize_material(
                    material
                )
            },
            message="Exam material submitted for review.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# PUBLISH
# ---------------------------------------------------------------------------

@exam_materials_bp.post(
    "/<uuid:material_id>/publish"
)
@require_roles(*ADMIN_ROLES)
def publish_material(material_id):
    """
    POST /admin/exam-materials/<material_id>/publish
    """
    try:
        reviewer_id = _get_current_user_id()

        if not reviewer_id:
            return error_response(
                "AUTHENTICATION_REQUIRED",
                "An authenticated reviewer is required.",
                status=401,
            )

        material = publish_exam_material(
            material_id,
            str(reviewer_id),
        )

        return success_response(
            {
                "material": _serialize_material(
                    material
                )
            },
            message="Exam material published successfully.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# ARCHIVE
# ---------------------------------------------------------------------------

@exam_materials_bp.post(
    "/<uuid:material_id>/archive"
)
@require_roles(*ADMIN_ROLES)
def archive_material(material_id):
    """
    POST /admin/exam-materials/<material_id>/archive
    """
    try:
        material = archive_exam_material(
            material_id
        )

        return success_response(
            {
                "material": _serialize_material(
                    material
                )
            },
            message="Exam material archived successfully.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# ATTACH FILE
# ---------------------------------------------------------------------------

@exam_materials_bp.post(
    "/<uuid:material_id>/file"
)
@require_roles(*ADMIN_ROLES)
def attach_material_file(material_id):
    """
    POST /admin/exam-materials/<material_id>/file

    The actual binary storage/upload mechanism remains separate.

    This endpoint receives storage metadata and attaches it atomically
    to the ExamMaterial record.

    Expected JSON:

        {
            "file_name": "...",
            "file_size": 12345,
            "mime_type": "application/pdf",
            "storage_key": "...",
            "file_url": "...",
            "page_count": 10
        }
    """
    try:
        payload = request.get_json(
            silent=True
        )

        if payload is None:
            return error_response(
                "INVALID_JSON",
                "Request body must contain valid JSON.",
                status=400,
            )

        payload = validate_attach_file(
            payload
        )

        material = attach_file(
            material_id,
            payload,
        )

        return success_response(
            {
                "material": _serialize_material(
                    material
                )
            },
            message="Material file attached successfully.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# BULK UPDATE
# ---------------------------------------------------------------------------

@exam_materials_bp.patch("/bulk")
@require_roles(*ADMIN_ROLES)
def bulk_update_materials():
    """
    PATCH /admin/exam-materials/bulk

    Expected body:

        {
            "ids": ["id1", "id2"],
            "status": "published"
        }

    or:

        {
            "ids": ["id1", "id2"],
            "price": 10.00
        }

    or:

        {
            "ids": ["id1", "id2"],
            "expert_id": "expert-id"
        }
    """
    try:
        payload = request.get_json(
            silent=True
        )

        if payload is None:
            return error_response(
                "INVALID_JSON",
                "Request body must contain valid JSON.",
                status=400,
            )

        ids = payload.get("ids")

        if not isinstance(ids, list):
            return error_response(
                "INVALID_IDS",
                "The 'ids' field must be an array.",
                status=400,
            )

        validated_payload = (
            validate_bulk_update_exam_materials(
                payload
            )
        )

        actor_id = _get_current_user_id()

        if not actor_id:
            return error_response(
                "AUTHENTICATION_REQUIRED",
                "An authenticated user is required.",
                status=401,
            )

        materials = bulk_update_exam_materials(
            ids,
            validated_payload,
            str(actor_id),
        )

        return success_response(
            {
                "items": [
                    _serialize_material(material)
                    for material in materials
                ],
                "count": len(materials),
            },
            message="Exam materials updated successfully.",
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


# ---------------------------------------------------------------------------
# BULK DELETE
# ---------------------------------------------------------------------------

@exam_materials_bp.delete("/bulk")
@require_roles(*ADMIN_ROLES)
def bulk_delete_materials():
    """
    DELETE /admin/exam-materials/bulk

    Expected body:

        {
            "ids": ["id1", "id2"]
        }
    """
    try:
        payload = request.get_json(
            silent=True
        )

        if payload is None:
            return error_response(
                "INVALID_JSON",
                "Request body must contain valid JSON.",
                status=400,
            )

        ids = validate_bulk_delete_exam_materials(
            payload
        )

        count = bulk_delete_exam_materials(
            ids
        )

        return success_response(
            {
                "count": count
            },
            message=(
                f"{count} exam material(s) "
                "deleted successfully."
            ),
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)

# ---------------------------------------------------------------------------
# CUSTOMER PORTAL (additive)
#
# Matches docs/API.md in the customer-portal frontend repo:
#   GET  /exam-materials             list purchasable materials
#   POST /exam-materials/{id}/purchase
# ---------------------------------------------------------------------------

from exam_materials.service import (
    list_materials_for_customer,
    purchase_material,
    search_materials_for_public,
    search_materials_for_customer,
)
from utils.authorization import get_current_user
from utils.roles import CUSTOMER_ROLES

customer_bp = Blueprint(
    "exam_materials_customer",
    __name__,
    url_prefix="/api/v1/exam-materials",
)

public_customer_bp = Blueprint(
    "exam_materials_public_catalogue",
    __name__,
    url_prefix="/api/v1/public/exam-materials",
)


@public_customer_bp.get("")
def list_public_materials_route():
    try:
        result = search_materials_for_public(
            q=request.args.get("q"), subject=request.args.get("subject"),
            level=request.args.get("level"), category=request.args.get("category"),
            sort=request.args.get("sort"), page=request.args.get("page", 1, type=int),
            per_page=request.args.get("per_page", 12, type=int),
        )
        return success_response({"data": result["items"], "meta": result["meta"]})
    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@customer_bp.get("")
@require_roles(*CUSTOMER_ROLES)
def list_materials_route():
    try:
        user = get_current_user()

        result = search_materials_for_customer(
            user,
            q=request.args.get("q"),
            subject=request.args.get("subject"),
            level=request.args.get("level"),
            category=request.args.get("category"),
            sort=request.args.get("sort"),
            page=request.args.get("page", 1, type=int),
            per_page=request.args.get("per_page", 12, type=int),
        )

        return success_response(
            {"data": result["items"], "meta": result["meta"]}
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@customer_bp.post("/<uuid:material_id>/purchase")
@require_roles(*CUSTOMER_ROLES)
def purchase_material_route(material_id):
    try:
        user = get_current_user()

        return success_response(
            {"data": purchase_material(user, material_id)},
            status=201,
        )

    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


def _send_material(material, user=None):
    kind, target = resolve_material_download(material, user)
    if kind == "redirect":
        return redirect(target, code=302)
    return send_file(
        target,
        as_attachment=True,
        download_name=material.file_name or "material",
        max_age=0,
    )


@exam_materials_bp.get("/<uuid:material_id>/file")
@require_roles(*ADMIN_ROLES)
def download_material_file_admin(material_id):
    try:
        return _send_material(get_exam_material(material_id))
    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@customer_bp.get("/<uuid:material_id>/download")
@require_roles(*CUSTOMER_ROLES)
def download_material_route(material_id):
    from exam_materials.exam_material import ExamMaterial
    from extensions import db
    from utils.exceptions import NotFoundError

    try:
        material = db.session.get(ExamMaterial, material_id)
        if material is None:
            raise NotFoundError("File not found.")
        response = _send_material(material, get_current_user())
        response.headers["Cache-Control"] = "private, no-store"
        return response
    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


def _bulk_status(status):
    try:
        payload = request.get_json(silent=True) or {}
        ids = payload.get("ids")
        if not isinstance(ids, list) or not ids or not all(
            isinstance(i, str) and i for i in ids
        ):
            return error_response(
                "VALIDATION_ERROR", "ids must be a non-empty list.", status=400
            )
        materials = bulk_update_exam_materials(
            ids, {"status": status}, _get_current_user_id()
        )
        return success_response(
            {"items": [_serialize_material(m) for m in materials],
             "count": len(materials)},
            message="Materials updated successfully.",
        )
    except (ValueError, ServiceError) as exc:
        return _handle_service_error(exc)


@exam_materials_bp.post("/bulk/publish")
@require_roles(*ADMIN_ROLES)
def bulk_publish_materials():
    return _bulk_status("published")


@exam_materials_bp.post("/bulk/archive")
@require_roles(*ADMIN_ROLES)
def bulk_archive_materials():
    return _bulk_status("archived")
