from flask import Blueprint, request
from utils.authorization import get_current_user, require_roles
from utils.roles import ADMIN_ROLES, EXPERT_ROLES

from utils.response_formatter import (
    success_response,
    error_response,
)

from experts.service import ExpertService
from experts.schemas import (
    expert_schema,
    experts_schema,
    create_expert_schema,
    update_expert_schema,
    expert_status_schema,
    validate_bulk_ids,
    validate_bulk_status,
)

bp = Blueprint(
    "experts",
    __name__,
    url_prefix="/api/v1/experts",
)

# Self-service: the expert's own profile. Not nested under
# /api/v1/experts (that blueprint is admin-only) - mounted directly
# at /api/v1 to match the expert portal frontend's actual calls
# (GET/PATCH /profile).
self_bp = Blueprint(
    "experts_self",
    __name__,
    url_prefix="/api/v1",
)


@self_bp.get("/profile")
@require_roles(*EXPERT_ROLES)
def get_my_profile_route():
    user = get_current_user()

    return success_response(
        {"data": ExpertService.get_my_profile(user)}
    )


@self_bp.patch("/profile")
@require_roles(*EXPERT_ROLES)
def update_my_profile_route():
    user = get_current_user()

    payload = request.get_json(silent=True) or {}

    profile = ExpertService.update_my_profile(user, payload)

    return success_response(
        {"data": profile}, message="Profile updated."
    )

@bp.get("")
@require_roles(*ADMIN_ROLES)
def list_experts():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    search = request.args.get("search")
    status = request.args.get("status")
    sort_by = request.args.get("sort_by", "created_at")
    direction = request.args.get("direction", "desc")

    experts = ExpertService.list_experts(
        page=page,
        per_page=per_page,
        search=search,
        status=status,
        sort_by=sort_by,
        direction=direction,
    )

    return success_response({
        "items": experts_schema.dump(experts.items),
        "pagination": {
            "page": experts.page,
            "per_page": experts.per_page,
            "pages": experts.pages,
            "total": experts.total,
            "has_next": experts.has_next,
            "has_prev": experts.has_prev,
        },
    })


@bp.get("/statistics")
@require_roles(*ADMIN_ROLES)
def statistics():
    return success_response(
        ExpertService.statistics()
    )


@bp.get("/<uuid:expert_id>")
@require_roles(*ADMIN_ROLES)
def get_expert(expert_id):

    expert = ExpertService.get_expert(expert_id)

    if not expert:
        return error_response(
            "NOT_FOUND",
            "Expert not found",
            status=404,
        )

    return success_response(
        expert_schema.dump(expert)
    )


@bp.post("")
@require_roles(*ADMIN_ROLES)
def create_expert():

    payload = create_expert_schema.load(
        request.get_json() or {}
    )

    if ExpertService.get_by_email(payload["email"]):
        return error_response(
            "EMAIL_EXISTS",
            "Expert already exists.",
            status=409,
        )

    expert = ExpertService.create_expert(payload)

    return success_response(
        expert_schema.dump(expert),
        message="Expert created successfully.",
        status=201,
    )


@bp.patch("/<uuid:expert_id>")
@require_roles(*ADMIN_ROLES)
def update_expert(expert_id):

    expert = ExpertService.get_expert(expert_id)

    if not expert:
        return error_response(
            "NOT_FOUND",
            "Expert not found",
            status=404,
        )

    payload = update_expert_schema.load(
        request.get_json() or {}
    )

    expert = ExpertService.update_expert(
        expert,
        payload,
    )

    return success_response(
        expert_schema.dump(expert),
        message="Expert updated successfully.",
    )


@bp.delete("/<uuid:expert_id>")
@require_roles(*ADMIN_ROLES)
def delete_expert(expert_id):

    expert = ExpertService.get_expert(expert_id)

    if not expert:
        return error_response(
            "NOT_FOUND",
            "Expert not found",
            status=404,
        )

    ExpertService.delete_expert(expert)

    return success_response(
        message="Expert deleted successfully."
    )


@bp.patch("/<uuid:expert_id>/status")
@require_roles(*ADMIN_ROLES)
def update_status(expert_id):

    expert = ExpertService.get_expert(expert_id)

    if not expert:
        return error_response(
            "NOT_FOUND",
            "Expert not found",
            status=404,
        )

    payload = expert_status_schema.load(
        request.get_json() or {}
    )

    status = payload["status"]

    if status == "active":
        expert = ExpertService.activate(expert)

    elif status == "paused":
        expert = ExpertService.pause(expert)

    elif status == "onboarding":
        expert = ExpertService.onboard(expert)

    elif status == "offboarded":
        expert = ExpertService.offboard(expert)

    return success_response(
        expert_schema.dump(expert),
        message="Status updated successfully.",
    )


@bp.patch("/bulk/status")
@require_roles(*ADMIN_ROLES)
def bulk_status():

    payload = request.get_json(silent=True) or {}

    validated = validate_bulk_status(payload)

    experts = ExpertService.bulk_update_status(
        validated["ids"],
        validated["status"],
    )

    return success_response({
        "items": experts_schema.dump(experts)
    })


@bp.delete("/bulk")
@require_roles(*ADMIN_ROLES)
def bulk_delete():

    payload = request.get_json(silent=True) or {}

    validated = validate_bulk_ids(payload)

    deleted = ExpertService.bulk_delete(
        validated["ids"]
    )

    return success_response(
        {
            "deleted": deleted,
        },
        message="Experts deleted.",
    )


# POST    /experts/<id>/materials Assign exam material (future)
# DELETE  /experts/<id>/materials/<material_id>   Remove material (future)