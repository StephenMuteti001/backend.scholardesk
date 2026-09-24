# orders/interest_service.py
"""
Expert-facing opportunities ("available orders") and the advisory
interest register that sits on top of them.

Scope boundary, deliberately kept narrow:

  * Interest NEVER assigns, reserves or locks an order. Support
    assigns work through OrderService.assign_expert() exactly as it
    does today, and may still pick an expert who never registered
    interest.
  * An order is only "available" while it is paid and nobody has been
    assigned to its underlying ServiceRequest yet
    (ServiceRequest.assigned_to - the same field the assignment flow
    and submissions/service.py already treat as the source of truth).
  * Opportunity payloads never include customer identity or contact
    details; see orders/schemas.py::serialize_available_order.
"""

from datetime import datetime, timezone

from sqlalchemy import func, or_

from extensions import db
from orders.constants import ASSIGNMENT_STATUS_DECLINED
from orders.order import Order
from orders.order_interest import OrderInterest
from orders.schemas import (
    serialize_available_order,
    serialize_order_interest,
)
from utils.exceptions import ConflictError, NotFoundError, ValidationError
from utils.transaction import transaction

# Fulfilment stages at which an unassigned order is no longer work
# anybody can pick up.
CLOSED_STAGES = ("completed", "cancelled")


class OrderInterestService:

    # ------------------------------------------------------------------
    # Internal lookups
    # ------------------------------------------------------------------

    @staticmethod
    def expert_profile_or_raise(expert_user):
        from experts.expert import Expert, ExpertStatus

        profile = (
            Expert.query.filter(Expert.user_id == expert_user.id).first()
        )

        if not profile:
            raise NotFoundError(
                "No expert profile is attached to this account."
            )

        if profile.status != ExpertStatus.ACTIVE:
            raise ValidationError(
                "Your expert profile is not active."
            )

        return profile

    @staticmethod
    def _available_orders_query(expert_profile=None):
        from requests.request import ServiceRequest

        query = (
            Order.query.join(
                ServiceRequest, Order.request_id == ServiceRequest.id
            )
            .filter(Order.status == "paid")
            .filter(Order.source_type == "request")
            .filter(ServiceRequest.assigned_to.is_(None))
            .filter(
                or_(
                    Order.fulfillment_stage.is_(None),
                    Order.fulfillment_stage.notin_(CLOSED_STAGES),
                )
            )
        )

        if expert_profile is not None:
            subjects = [
                str(s).strip().lower()
                for s in (expert_profile.specialities or [])
                if str(s).strip()
            ]

            # An expert with no declared specialities sees everything
            # that is open; otherwise the board is narrowed to the
            # subjects they were approved for.
            if subjects:
                query = query.filter(
                    func.lower(ServiceRequest.subject).in_(subjects)
                )

        return query

    @staticmethod
    def _interest_or_none(order_id, expert_id):
        return (
            OrderInterest.query.filter(
                OrderInterest.order_id == order_id,
                OrderInterest.expert_id == expert_id,
            ).first()
        )

    @staticmethod
    def _assert_order_open(order):
        if order.status != "paid":
            raise ConflictError(
                "This order is not open for interest."
            )

        if not order.request:
            raise ConflictError(
                "This order has no underlying request."
            )

        if order.request.assigned_to:
            raise ConflictError(
                "This order has already been assigned."
            )

        if order.fulfillment_stage in CLOSED_STAGES:
            raise ConflictError(
                "This order is no longer open."
            )

    # ------------------------------------------------------------------
    # Expert: available orders
    # ------------------------------------------------------------------

    @staticmethod
    def list_available(expert_user, search=None, page=1, per_page=50):
        from requests.request import ServiceRequest

        profile = OrderInterestService.expert_profile_or_raise(expert_user)

        query = OrderInterestService._available_orders_query(profile)

        if search:
            search = search.strip()

            if search:
                term = f"%{search}%"

                query = query.filter(
                    or_(
                        Order.reference.ilike(term),
                        Order.item_title.ilike(term),
                        ServiceRequest.subject.ilike(term),
                    )
                )

        query = query.order_by(
            ServiceRequest.deadline.asc().nullslast(),
            Order.created_at.desc(),
            Order.id.asc(),
        )

        pagination = query.paginate(
            page=page, per_page=per_page, error_out=False
        )

        orders = pagination.items

        interested_ids = set()

        if orders:
            rows = (
                db.session.query(OrderInterest.order_id)
                .filter(
                    OrderInterest.expert_id == profile.id,
                    OrderInterest.order_id.in_([o.id for o in orders]),
                    OrderInterest.withdrawn_at.is_(None),
                )
                .all()
            )

            interested_ids = {row.order_id for row in rows}

        return {
            "items": [
                serialize_available_order(
                    order, interested=order.id in interested_ids
                )
                for order in orders
            ],
            "pagination": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "pages": pagination.pages,
                "total": pagination.total,
            },
        }

    # ------------------------------------------------------------------
    # Expert: register / withdraw interest
    # ------------------------------------------------------------------

    @staticmethod
    def register_interest(expert_user, order_id, note=None):
        """
        Idempotent: re-registering an interest that already stands is a
        no-op success, and re-registering a withdrawn one revives it.
        """
        from orders.service import OrderService

        profile = OrderInterestService.expert_profile_or_raise(expert_user)

        order = OrderService.get_order(order_id)

        OrderInterestService._assert_order_open(order)

        interest = OrderInterestService._interest_or_none(
            order.id, profile.id
        )

        with transaction():
            if interest is None:
                interest = OrderInterest(
                    order_id=order.id,
                    expert_id=profile.id,
                    note=note,
                )

                db.session.add(interest)
            else:
                interest.withdrawn_at = None

                if note is not None:
                    interest.note = note

            db.session.flush()

        return OrderInterestService.serialize_for_expert(interest)

    @staticmethod
    def withdraw_interest(expert_user, order_id):
        from orders.service import OrderService

        profile = OrderInterestService.expert_profile_or_raise(expert_user)

        order = OrderService.get_order(order_id)

        interest = OrderInterestService._interest_or_none(
            order.id, profile.id
        )

        if interest is None:
            raise NotFoundError("You have not registered interest here.")

        if interest.withdrawn_at is None:
            with transaction():
                interest.withdrawn_at = datetime.now(timezone.utc)

                db.session.flush()

        return OrderInterestService.serialize_for_expert(interest)

    @staticmethod
    def serialize_for_expert(interest):
        return {
            "id": str(interest.id),
            "order_id": str(interest.order_id),
            "interested": interest.withdrawn_at is None,
            "note": interest.note,
            "created_at": (
                interest.created_at.isoformat()
                if interest.created_at
                else None
            ),
            "withdrawn_at": (
                interest.withdrawn_at.isoformat()
                if interest.withdrawn_at
                else None
            ),
        }

    # ------------------------------------------------------------------
    # Admin: who put their hand up
    # ------------------------------------------------------------------

    @staticmethod
    def active_assignment_counts(expert_user_ids):
        """
        How much live work each expert is already carrying - the
        signal support weighs against expertise and rating when
        choosing who to assign.
        """
        if not expert_user_ids:
            return {}

        from requests.request import ServiceRequest

        rows = (
            db.session.query(
                ServiceRequest.assigned_to,
                func.count(Order.id),
            )
            .join(Order, Order.request_id == ServiceRequest.id)
            .filter(ServiceRequest.assigned_to.in_(list(expert_user_ids)))
            .filter(
                or_(
                    Order.assignment_status.is_(None),
                    Order.assignment_status != ASSIGNMENT_STATUS_DECLINED,
                )
            )
            .filter(
                or_(
                    Order.fulfillment_stage.is_(None),
                    Order.fulfillment_stage.notin_(CLOSED_STAGES),
                )
            )
            .group_by(ServiceRequest.assigned_to)
            .all()
        )

        return {user_id: count for user_id, count in rows}

    @staticmethod
    def list_for_order(order_id, include_withdrawn=True):
        from orders.service import OrderService

        order = OrderService.get_order(order_id)

        query = OrderInterest.query.filter(
            OrderInterest.order_id == order.id
        )

        if not include_withdrawn:
            query = query.filter(OrderInterest.withdrawn_at.is_(None))

        interests = query.order_by(
            OrderInterest.created_at.desc(),
            OrderInterest.id.asc(),
        ).all()

        user_ids = [
            interest.expert.user_id
            for interest in interests
            if interest.expert and interest.expert.user_id
        ]

        counts = OrderInterestService.active_assignment_counts(user_ids)

        items = [
            serialize_order_interest(
                interest,
                active_assignments=counts.get(
                    interest.expert.user_id if interest.expert else None,
                    0,
                ),
            )
            for interest in interests
        ]

        return {"items": items, "total": len(items)}

    @staticmethod
    def counts_for_orders(order_ids):
        """
        Standing (non-withdrawn) interest counts, keyed by order id -
        used to decorate the admin order list.
        """
        if not order_ids:
            return {}

        rows = (
            db.session.query(
                OrderInterest.order_id,
                func.count(OrderInterest.id),
            )
            .filter(OrderInterest.order_id.in_(list(order_ids)))
            .filter(OrderInterest.withdrawn_at.is_(None))
            .group_by(OrderInterest.order_id)
            .all()
        )

        return {order_id: count for order_id, count in rows}
