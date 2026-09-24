from sqlalchemy import or_

from extensions import db
from .expert import Expert, ExpertStatus
from users.user import User
from utils.transaction import transaction

class ExpertService:
    """
    Business logic for Expert management.
    """

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    @staticmethod
    def create_expert(data):
        with transaction():
            expert = Expert(**data)

            db.session.add(expert)

            db.session.flush()

            return expert

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------

    @staticmethod
    def get_expert(expert_id):
        return Expert.query.get(expert_id)

    @staticmethod
    def get_by_email(email: str):
        # Expert.email is a hybrid_property with no SQL .expression
        # (see experts/expert.py) - it only works on an already-loaded
        # instance, not in a query filter. Join against User instead,
        # which is where email actually lives.
        return (
            Expert.query.join(User, Expert.user_id == User.id)
            .filter(User.email == email)
            .first()
        )

    @staticmethod
    def list_experts(
        page=1,
        per_page=20,
        search=None,
        status=None,
        sort_by="created_at",
        direction="desc",
    ):
        query = Expert.query.join(User, Expert.user_id == User.id)

        if search:
            like = f"%{search}%"

            query = query.filter(
                or_(
                    User.first_name.ilike(like),
                    User.last_name.ilike(like),
                    User.email.ilike(like),
                )
            )

        if status:
            query = query.filter(
                Expert.status == status
            )

        # Expert's name/email/first_name/last_name are hybrid_properties
        # with no SQL .expression (see experts/expert.py) - they can't be
        # used as an order_by column. Only allow genuine Expert columns;
        # anything else (e.g. a caller passing "name") falls back safely.
        sort_column = (
            getattr(Expert, sort_by, None)
            if sort_by in Expert.__table__.columns
            else None
        ) or Expert.created_at

        if direction.lower() == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        return query.paginate(
            page=page,
            per_page=per_page,
            error_out=False,
        )

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    @staticmethod
    def update_expert(
        expert: Expert,
        data: dict,
    ):
        with transaction():

            for key, value in data.items():
                setattr(expert, key, value)

            db.session.flush()

            return expert

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    @staticmethod
    def delete_expert(expert: Expert):
        with transaction():
            db.session.delete(expert)

    # ------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------

    @staticmethod
    def activate(expert: Expert):
        with transaction():
            expert.status = ExpertStatus.ACTIVE
            db.session.flush()

        return expert

    @staticmethod
    def pause(expert: Expert):
        with transaction():
            expert.status = ExpertStatus.PAUSED
            db.session.flush()

        return expert

    @staticmethod
    def offboard(expert: Expert):
        with transaction():
            expert.status = ExpertStatus.OFFBOARDED
            db.session.flush()

        return expert

    @staticmethod
    def onboard(expert: Expert):
        with transaction():
            expert.status = ExpertStatus.ONBOARDING
            db.session.flush()

        return expert

    # ------------------------------------------------------------------
    # BULK ACTIONS
    # ------------------------------------------------------------------

    @staticmethod
    def bulk_update_status(ids, status):
        if not ids:
            return []

        with transaction():
            experts = Expert.query.filter(
                Expert.id.in_(ids)
            ).all()

            for expert in experts:
                expert.status = status

            db.session.flush()

            return experts

    @staticmethod
    def bulk_delete(ids):
        if not ids:
            return 0

        with transaction():
            experts = Expert.query.filter(
                Expert.id.in_(ids)
            ).all()

            deleted = len(experts)

            for expert in experts:
                db.session.delete(expert)

            return deleted

    # ------------------------------------------------------------------
    # STATISTICS
    # ------------------------------------------------------------------

    @staticmethod
    def statistics():
        total = Expert.query.count()

        active = Expert.query.filter(
            Expert.status == ExpertStatus.ACTIVE
        ).count()

        onboarding = Expert.query.filter(
            Expert.status == ExpertStatus.ONBOARDING
        ).count()

        paused = Expert.query.filter(
            Expert.status == ExpertStatus.PAUSED
        ).count()

        offboarded = Expert.query.filter(
            Expert.status == ExpertStatus.OFFBOARDED
        ).count()

        experts = Expert.query.all()

        return {
            "total": total,
            "active": active,
            "onboarding": onboarding,
            "paused": paused,
            "offboarded": offboarded,
            "active_jobs": sum(
                e.active_jobs for e in experts
            ),
            "completed_jobs": sum(
                e.completed for e in experts
            ),
            "payout_due": sum(
                e.payout_due for e in experts
            ),
        }

    # ------------------------------------------------------------------
    # MATERIALS
    # ------------------------------------------------------------------

    @staticmethod
    def assign_material(
        expert: Expert,
        material,
    ):
        """
        Placeholder until ExamMaterialService
        is implemented.
        """

        with transaction():
            expert.exam_materials.append(material)
            db.session.flush()

        return expert

    @staticmethod
    def remove_material(
        expert: Expert,
        material,
    ):
        with transaction():
            if material in expert.exam_materials:
                expert.exam_materials.remove(material)
                db.session.flush()

        return expert
    # ------------------------------------------------------------------
    # Self-service: the expert's own profile
    # ------------------------------------------------------------------

    @staticmethod
    def get_my_profile(user):
        expert = ExpertService.get_by_user_id(user.id)

        return {
            "full_name": user.full_name,
            "email": user.email,
            "phone": user.phone_number,
            "bio": expert.bio if expert else None,
            "profile_image": expert.profile_image if expert else None,
            "timezone": expert.timezone if expert else None,
            "languages": expert.languages if expert else [],
            "specialities": expert.specialities if expert else [],
            "hourly_rate": (
                float(expert.hourly_rate)
                if expert and expert.hourly_rate is not None
                else None
            ),
        }

    @staticmethod
    def get_by_user_id(user_id):
        return Expert.query.filter(Expert.user_id == user_id).first()

    @staticmethod
    def update_my_profile(user, payload):
        expert = ExpertService.get_by_user_id(user.id)

        with transaction():
            if "full_name" in payload and payload["full_name"]:
                user.set_full_name(payload["full_name"])

            if "phone" in payload:
                user.phone_number = payload["phone"] or None

            if expert and "bio" in payload:
                expert.bio = payload["bio"] or None

            db.session.flush()

        return ExpertService.get_my_profile(user)
