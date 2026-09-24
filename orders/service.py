# orders/service.py

import csv
import io
import secrets
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, or_

from extensions import db
from orders.constants import (
    ASSIGNMENT_STATUS_ACCEPTED,
    ASSIGNMENT_STATUS_DECLINED,
    ASSIGNMENT_STATUS_PENDING,
    DEFAULT_PER_PAGE,
    MAX_PER_PAGE,
    ORDER_GATEWAYS,
    ORDER_SORT_FIELDS,
    ORDER_STATUSES,
)
from orders.order import Order
from orders.schemas import (
    serialize_order,
    serialize_pagination,
    validate_gateway,
    validate_order_status,
    validate_refund_payload,
)
from utils.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from utils.transaction import transaction


class OrderService:

    @staticmethod
    def get_order(order_id):
        order = db.session.get(Order, order_id)

        if not order:
            raise NotFoundError(
                "Order not found.",
                {"order_id": order_id},
            )

        return order

    @staticmethod
    def list_orders(
        page=1,
        per_page=DEFAULT_PER_PAGE,
        search=None,
        status=None,
        gateway=None,
        sort_by="createdAt",
        direction="desc",
    ):
        try:
            page = int(page)
            per_page = int(per_page)
        except (TypeError, ValueError):
            raise ValidationError("Page and per_page must be integers.")

        if page < 1:
            raise ValidationError("Page must be greater than zero.")

        per_page = min(max(per_page, 1), MAX_PER_PAGE)

        if status:
            validate_order_status(status)

        if gateway:
            validate_gateway(gateway)

        query = Order.query

        if search:
            search = search.strip()

            if search:
                term = f"%{search}%"

                query = query.join(
                    Order.customer
                ).filter(
                    or_(
                        Order.reference.ilike(term),
                        Order.item_title.ilike(term),
                        Order.payment_reference.ilike(term),
                    )
                )

        if status:
            query = query.filter(Order.status == status)

        if gateway:
            query = query.filter(Order.gateway == gateway)

        sort_column_name = ORDER_SORT_FIELDS.get(
            sort_by,
            "created_at",
        )

        sort_column = getattr(
            Order,
            sort_column_name,
            Order.created_at,
        )

        if direction == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False,
        )

        items = [
            serialize_order(order)
            for order in pagination.items
        ]

        # Standing expert interest, so the support team can see at a
        # glance which orders already have hands up before opening
        # them (orders/interest_service.py). Purely additive.
        from orders.interest_service import OrderInterestService

        interest_counts = OrderInterestService.counts_for_orders(
            [order.id for order in pagination.items]
        )

        for order, item in zip(pagination.items, items):
            item["interest_count"] = interest_counts.get(order.id, 0)

        return {
            "items": items,
            "pagination": serialize_pagination(pagination),
        }

    @staticmethod
    def statistics():
        paid = (
            db.session.query(func.count(Order.id))
            .filter(Order.status == "paid")
            .scalar()
            or 0
        )

        gross = (
            db.session.query(func.coalesce(func.sum(Order.amount), 0))
            .filter(Order.status == "paid")
            .scalar()
            or Decimal("0")
        )

        pending = (
            db.session.query(func.count(Order.id))
            .filter(Order.status == "pending")
            .scalar()
            or 0
        )

        disputed = (
            db.session.query(func.count(Order.id))
            .filter(Order.status == "disputed")
            .scalar()
            or 0
        )

        return {
            "paid": paid,
            "gross": float(gross),
            "pending": pending,
            "disputed": disputed,
        }

    @staticmethod
    def update_order(order_id, payload):
        order = OrderService.get_order(order_id)

        payload = payload or {}

        with transaction():

            if "status" in payload:
                status = payload["status"]
                validate_order_status(status)

                if order.status == "refunded" and status != "refunded":
                    raise ConflictError(
                        "A refunded order cannot be moved back "
                        "to another payment status."
                    )

                order.status = status

            if "notes" in payload:
                order.notes = payload["notes"]

        return order

    @staticmethod
    def delete_order(order_id):
        order = OrderService.get_order(order_id)

        if order.status == "paid":
            raise ConflictError(
                "Paid orders cannot be deleted. "
                "Refund the order first if necessary."
            )

        with transaction():
            db.session.delete(order)

    @staticmethod
    def refund_order(order_id, payload):
        order = OrderService.get_order(order_id)

        if order.status == "refunded":
            raise ConflictError("Order has already been refunded.")

        if order.status not in {"paid", "disputed"}:
            raise ConflictError(
                "Only paid or disputed orders can be refunded."
            )

        data = validate_refund_payload(payload)

        refund_amount = data["amount"]

        if refund_amount is None:
            refund_amount = Decimal(str(order.amount))

        order_amount = Decimal(str(order.amount))
        already_refunded = Decimal(str(order.refunded_amount or 0))

        remaining = order_amount - already_refunded

        if refund_amount > remaining:
            raise ValidationError(
                "Refund amount exceeds the remaining refundable amount.",
                {
                    "order_amount": float(order_amount),
                    "already_refunded": float(already_refunded),
                    "remaining": float(remaining),
                },
            )

        with transaction():

            order.refunded_amount = already_refunded + refund_amount
            order.refund_reason = data["reason"]
            order.refunded_at = datetime.now(timezone.utc)

            if order.refunded_amount >= order_amount:
                order.status = "refunded"

        return order

    @staticmethod
    def bulk_update(ids, payload):
        if not ids:
            raise ValidationError("At least one order ID is required.")

        status = payload.get("status")

        if not status:
            raise ValidationError("Status is required.")

        validate_order_status(status)

        orders = (
            Order.query
            .filter(Order.id.in_(ids))
            .all()
        )

        if len(orders) != len(set(ids)):
            found_ids = {str(order.id) for order in orders}
            missing = [
                order_id
                for order_id in ids
                if order_id not in found_ids
            ]

            raise NotFoundError(
                "One or more orders were not found.",
                {"missing_ids": missing},
            )

        with transaction():

            for order in orders:
                if order.status == "refunded" and status != "refunded":
                    raise ConflictError(
                        f"Refunded order {order.reference} "
                        "cannot be changed."
                    )

                order.status = status

        return {
            "count": len(orders),
        }

    @staticmethod
    def resend_receipt(order_id):
        order = OrderService.get_order(order_id)

        if not order.customer:
            raise ConflictError(
                "Order has no associated customer."
            )

        email = getattr(order.customer, "email", None)

        if not email:
            raise ConflictError(
                "Customer does not have an email address."
            )

        # Integrate this with your existing mailer.
        #
        # Example:
        #
        # from utils.mailer import send_email
        #
        # send_email(
        #     to=email,
        #     subject=f"Receipt for {order.reference}",
        #     template="order_receipt",
        #     context={"order": serialize_order(order)},
        # )

        return True

    @staticmethod
    def bulk_resend_receipts(ids):
        if not ids:
            raise ValidationError(
                "At least one order ID is required."
            )

        orders = (
            Order.query
            .filter(Order.id.in_(ids))
            .all()
        )

        if len(orders) != len(set(ids)):
            raise NotFoundError(
                "One or more orders were not found."
            )

        sent = 0

        for order in orders:
            OrderService.resend_receipt(str(order.id))
            sent += 1

        return {
            "count": sent,
        }

    @staticmethod
    def regenerate_download_link(order_id):
        order = OrderService.get_order(order_id)

        if order.source_type != "material":
            raise ConflictError(
                "Download links are only available for material orders."
            )

        if order.status != "paid":
            raise ConflictError(
                "A download link cannot be generated "
                "for an unpaid order."
            )

        if not order.material_id:
            raise ConflictError(
                "Order is missing its material reference."
            )

        # IMPORTANT:
        # Replace this with your existing exam_materials
        # download-token/storage service.
        #
        # For example:
        #
        # from exam_materials.service import generate_download_link
        #
        # return generate_download_link(order.material_id, order.customer_id)

        token = secrets.token_urlsafe(32)

        return {
            "url": f"/api/v1/materials/{order.material_id}/download?token={token}"
        }

    @staticmethod
    def export_orders(**kwargs):
        result = OrderService.list_orders(
            page=1,
            per_page=MAX_PER_PAGE,
            **kwargs,
        )

        # For exports containing more than MAX_PER_PAGE records,
        # use a direct query instead of pagination.
        query = Order.query

        search = kwargs.get("search")
        status = kwargs.get("status")
        gateway = kwargs.get("gateway")

        if search:
            term = f"%{search.strip()}%"
            query = query.join(Order.customer).filter(
                or_(
                    Order.reference.ilike(term),
                    Order.item_title.ilike(term),
                    Order.payment_reference.ilike(term),
                )
            )

        if status:
            validate_order_status(status)
            query = query.filter(Order.status == status)

        if gateway:
            validate_gateway(gateway)
            query = query.filter(Order.gateway == gateway)

        sort_by = kwargs.get("sort_by", "createdAt")
        direction = kwargs.get("direction", "desc")

        sort_column_name = ORDER_SORT_FIELDS.get(
            sort_by,
            "created_at",
        )

        sort_column = getattr(
            Order,
            sort_column_name,
            Order.created_at,
        )

        query = query.order_by(
            sort_column.asc()
            if direction == "asc"
            else sort_column.desc()
        )

        orders = query.all()

        output = io.StringIO()

        writer = csv.writer(output)

        writer.writerow([
            "Order",
            "Created",
            "Item",
            "Customer",
            "Email",
            "Amount",
            "Currency",
            "Gateway",
            "Status",
        ])

        for order in orders:
            customer = order.customer

            writer.writerow([
                order.reference,
                order.created_at.isoformat()
                if order.created_at else "",
                order.item_title,
                getattr(customer, "name", ""),
                getattr(customer, "email", ""),
                order.amount,
                order.currency,
                order.gateway,
                order.status,
            ])

        return output.getvalue()

    @staticmethod
    def create_from_request(
        request_obj,
        customer_id,
        amount,
        gateway,
        currency="USD",
        payment_reference=None,
    ):
        if not request_obj:
            raise NotFoundError("Request not found.")

        if amount is None or Decimal(str(amount)) <= 0:
            raise ValidationError(
                "Order amount must be greater than zero."
            )

        validate_gateway(gateway)

        # A request can only become one order.
        existing = (
            Order.query
            .filter(Order.request_id == request_obj.id)
            .first()
        )

        if existing:
            raise ConflictError(
                "This request has already been converted into an order.",
                {
                    "order_id": str(existing.id),
                    "reference": existing.reference,
                },
            )

        reference = OrderService._generate_reference()

        with transaction():

            order = Order(
                reference=reference,
                customer_id=customer_id,
                source_type="request",
                request_id=request_obj.id,
                material_id=None,
                item_title=request_obj.title,
                amount=Decimal(str(amount)),
                currency=currency,
                gateway=gateway,
                status="paid",
                payment_reference=payment_reference,
            )

            db.session.add(order)
            db.session.flush()

        return order

    @staticmethod
    def create_unpaid_from_request(
        request_obj,
        customer_id,
        amount,
        currency="USD",
    ):
        """
        Creates the real Order the moment a client accepts a quote
        (see customer_orders/service.py::accept_quote) - "a request
        whose quote has been agreed/accepted becomes an order" is a
        direct product requirement, independent of payment.

        Deliberately mirrors create_from_request() above but:
          - takes no gateway/payment_reference (nothing has been
            charged yet)
          - status is "pending", not "paid"
          - fulfillment_stage is left unset (None). This is safe:
            customer_orders/service.py::_stage_for() only reads
            order.fulfillment_stage when it's truthy, and otherwise
            falls back to deriving "awaiting_payment" from the
            ServiceRequest's accepted quote - exactly the state this
            order is in. mark_paid() below is what first sets a real
            fulfillment_stage, once payment clears.
        """
        if not request_obj:
            raise NotFoundError("Request not found.")

        if amount is None or Decimal(str(amount)) <= 0:
            raise ValidationError(
                "Order amount must be greater than zero."
            )

        existing = (
            Order.query
            .filter(Order.request_id == request_obj.id)
            .first()
        )

        if existing:
            raise ConflictError(
                "This request has already been converted into an order.",
                {
                    "order_id": str(existing.id),
                    "reference": existing.reference,
                },
            )

        reference = OrderService._generate_reference()

        with transaction():
            order = Order(
                reference=reference,
                customer_id=customer_id,
                source_type="request",
                request_id=request_obj.id,
                material_id=None,
                item_title=request_obj.title,
                amount=Decimal(str(amount)),
                currency=currency,
                gateway=None,
                status="pending",
            )

            db.session.add(order)
            db.session.flush()

        return order

    @staticmethod
    def mark_paid(order, gateway, payment_reference=None):
        """
        Confirms payment against an order created by
        create_unpaid_from_request() above. This is what actually
        moves fulfilment forward - see the note on fulfillment_stage
        there.
        """
        validate_gateway(gateway)

        if order.status == "paid":
            raise ConflictError("This order has already been paid for.")

        with transaction():
            order.status = "paid"
            order.gateway = gateway
            order.payment_reference = payment_reference
            order.fulfillment_stage = "matching_writer"

            db.session.flush()

        return order

    @staticmethod
    def assign_expert(order_id, expert_id, budget, admin_user):
        """
        Support-team action: assigns the expert who will fulfil a
        paid order, and sets what the platform pays them for it
        (separate from what the customer paid - see
        Order.expert_budget). The assignment itself lives on
        ServiceRequest.assigned_to (requests/request.py) - the same
        field submissions/service.py::_assert_can_submit already
        checks to authorize an expert's deliveries.

        Takes expert_id (Expert.id, a UUID) rather than a User id -
        that's what the expert-search/autocomplete this powers
        naturally returns (ExpertSchema doesn't expose user_id).
        """
        order = OrderService.get_order(order_id)

        if order.status != "paid":
            raise ConflictError(
                "An order must be paid before an expert can be assigned."
            )

        if not order.request:
            raise ConflictError(
                "This order has no underlying request to assign against."
            )

        from experts.expert import Expert, ExpertStatus

        expert_profile = db.session.get(Expert, expert_id)

        if not expert_profile:
            raise NotFoundError("Expert not found.")

        if expert_profile.status != ExpertStatus.ACTIVE:
            raise ValidationError(
                "This expert is not active."
            )

        expert_user = expert_profile.user

        if budget is None or Decimal(str(budget)) <= 0:
            raise ValidationError(
                "Budget must be greater than zero."
            )

        with transaction():
            order.request.assigned_to = expert_user.id
            order.expert_budget = Decimal(str(budget))
            order.assignment_status = ASSIGNMENT_STATUS_PENDING
            # fulfillment_stage stays "matching_writer" - this order
            # doesn't move to "in_progress" until the expert actually
            # accepts (see accept_assignment() below); they can also
            # decline, in which case support needs to assign someone
            # else.

            activity = list(order.activity_log or [])

            activity.append(
                {
                    "id": secrets.token_hex(8),
                    "at": datetime.now(timezone.utc).isoformat(),
                    "actor": "support",
                    "title": "Expert assigned",
                    "detail": f"{expert_profile.name} - budget {order.currency} {budget}",
                }
            )

            order.activity_log = activity

            db.session.flush()

        from users.mailer_service import send_expert_assigned_email

        send_expert_assigned_email(expert_user, order, budget)

        return order

    @staticmethod
    def _get_order_for_expert(order_id, expert_user):
        order = OrderService.get_order(order_id)

        if not order.request or order.request.assigned_to != expert_user.id:
            raise NotFoundError("Order not found.")

        return order

    @staticmethod
    def accept_assignment(order_id, expert_user):
        order = OrderService._get_order_for_expert(order_id, expert_user)

        if order.assignment_status == ASSIGNMENT_STATUS_ACCEPTED:
            return order

        if order.assignment_status != ASSIGNMENT_STATUS_PENDING:
            raise ConflictError(
                "This assignment is no longer awaiting your response."
            )

        with transaction():
            order.assignment_status = ASSIGNMENT_STATUS_ACCEPTED
            order.fulfillment_stage = "in_progress"

            activity = list(order.activity_log or [])
            activity.append(
                {
                    "id": secrets.token_hex(8),
                    "at": datetime.now(timezone.utc).isoformat(),
                    "actor": "expert",
                    "title": "Assignment accepted",
                    "detail": None,
                }
            )
            order.activity_log = activity

            db.session.flush()

        return order

    @staticmethod
    def decline_assignment(order_id, expert_user, reason=None):
        """
        Freeing the expert from an assignment they haven't started.
        Deliberately keeps request.assigned_to pointing at the
        declining expert (rather than clearing it) so this order
        still shows up under that expert's own "declined" history -
        support reassigning to someone else (OrderService
        .assign_expert() again) naturally overwrites it.
        """
        order = OrderService._get_order_for_expert(order_id, expert_user)

        if order.assignment_status != ASSIGNMENT_STATUS_PENDING:
            raise ConflictError(
                "This assignment is no longer awaiting your response."
            )

        with transaction():
            order.assignment_status = ASSIGNMENT_STATUS_DECLINED

            activity = list(order.activity_log or [])
            activity.append(
                {
                    "id": secrets.token_hex(8),
                    "at": datetime.now(timezone.utc).isoformat(),
                    "actor": "expert",
                    "title": "Assignment declined",
                    "detail": reason,
                }
            )
            order.activity_log = activity

            db.session.flush()

        from users.mailer_service import send_internal_alert

        send_internal_alert(
            subject=f"Expert declined assignment - order {order.reference}",
            message=(
                f"{expert_user.full_name} declined the assignment for "
                f"\"{order.item_title}\" ({order.reference})."
                + (f" Reason: {reason}" if reason else "")
                + " This order needs to be reassigned."
            ),
            action_path="/orders",
        )

        return order

    # ------------------------------------------------------------------
    # Expert-facing: "my assignments"
    # ------------------------------------------------------------------

    @staticmethod
    def list_for_expert(expert_user, bucket, search=None, page=1, per_page=50):
        from requests.request import ServiceRequest

        query = (
            Order.query.join(
                ServiceRequest, Order.request_id == ServiceRequest.id
            ).filter(ServiceRequest.assigned_to == expert_user.id)
        )

        if bucket == "new":
            query = query.filter(
                Order.assignment_status == ASSIGNMENT_STATUS_PENDING
            )
        elif bucket == "active":
            query = query.filter(
                Order.assignment_status == ASSIGNMENT_STATUS_ACCEPTED,
                Order.fulfillment_stage.notin_(["completed", "cancelled"]),
            )
        elif bucket == "completed":
            query = query.filter(Order.fulfillment_stage == "completed")
        elif bucket == "cancelled":
            query = query.filter(
                or_(
                    Order.assignment_status == ASSIGNMENT_STATUS_DECLINED,
                    Order.fulfillment_stage == "cancelled",
                )
            )

        if search:
            like = f"%{search}%"
            query = query.filter(
                or_(
                    Order.reference.ilike(like),
                    Order.item_title.ilike(like),
                )
            )

        query = query.order_by(Order.updated_at.desc().nullslast(), Order.created_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return [
            OrderService.serialize_order_for_expert(order)
            for order in pagination.items
        ]

    @staticmethod
    def get_for_expert(order_id, expert_user):
        order = OrderService._get_order_for_expert(order_id, expert_user)
        return OrderService.serialize_order_for_expert(order, detailed=True)

    @staticmethod
    def serialize_order_for_expert(order, detailed=False):
        request = order.request
        metadata = (request.metadata_json or {}) if request else {}
        customer = order.customer

        data = {
            "id": str(order.id),
            "title": order.item_title,
            "subject": metadata.get("subject"),
            "type": metadata.get("assignment_type"),
            "pages": (
                max(1, round(metadata["word_count"] / 275))
                if metadata.get("word_count")
                else None
            ),
            "words": metadata.get("word_count"),
            "deadline": request.deadline.isoformat() if request and request.deadline else None,
            "budget": float(order.expert_budget) if order.expert_budget is not None else None,
            "currency": order.currency,
            "status": order.fulfillment_stage,
            "assignment_status": order.assignment_status,
            "citation_style": metadata.get("citation_style"),
            "created_at": order.created_at.isoformat() if order.created_at else None,
        }

        if customer:
            data["client"] = {
                "id": customer.id,
                "name": customer.full_name,
                "country": customer.country,
            }

        if detailed:
            data["instructions"] = request.instructions if request else None
            data["files"] = (
                [
                    {"name": f.get("name"), "url": f.get("url")}
                    for f in (metadata.get("files") or [])
                ]
                if metadata.get("files")
                else []
            )
            # Reuse the same submissions serialization the customer
            # side already exposes, so the expert sees exactly what
            # they've delivered so far (including anything still
            # pending_review, unlike the customer's own view).
            from submissions.submission import Submission

            submissions = (
                Submission.query.filter(Submission.order_id == order.id)
                .order_by(Submission.version.asc())
                .all()
            )
            data["submissions"] = [s.to_dict() for s in submissions]
            data["activity"] = order.activity_log or []

        return data

        return order

    @staticmethod
    def create_from_material(
        material_obj,
        customer_id,
        amount,
        gateway,
        currency="USD",
        payment_reference=None,
    ):
        """
        Sibling of create_from_request() for exam-material purchases
        (customer_orders' request-based flow has no material
        equivalent - materials are a straight one-shot purchase, see
        exam_materials/service.py::purchase_material()).
        """
        if not material_obj:
            raise NotFoundError("Exam material not found.")

        if amount is None or Decimal(str(amount)) <= 0:
            raise ValidationError(
                "Order amount must be greater than zero."
            )

        validate_gateway(gateway)

        reference = OrderService._generate_reference()

        with transaction():
            order = Order(
                reference=reference,
                customer_id=customer_id,
                source_type="material",
                request_id=None,
                material_id=material_obj.id,
                item_title=material_obj.title,
                amount=Decimal(str(amount)),
                currency=currency,
                gateway=gateway,
                status="paid",
                payment_reference=payment_reference,
            )

            db.session.add(order)
            db.session.flush()

        return order

    @staticmethod
    def _generate_reference():
        prefix = datetime.now(timezone.utc).strftime("%Y%m%d")

        while True:
            suffix = secrets.randbelow(1_000_000)

            reference = f"ORD-{prefix}-{suffix:06d}"

            exists = (
                db.session.query(Order.id)
                .filter(Order.reference == reference)
                .first()
            )

            if not exists:
                return reference
