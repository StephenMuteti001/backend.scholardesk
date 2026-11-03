# orders/checkout_service.py
"""
Customer checkout through Paystack, for both order sources:

  * request orders  - a quote the customer accepted (customer_orders/)
  * material orders - an exam-material purchase (exam_materials/)

Flow:
  1. start_checkout()  - the server creates an OrderCheckout row, asks
     Paystack for a hosted checkout page and hands back its URL.
  2. The customer pays and Paystack redirects them to the portal, which
     calls the verify endpoint. Paystack also calls the webhook
     (payments/webhooks.py).
  3. fulfil_checkout() - called by BOTH. Re-verifies with Paystack,
     checks amount and currency, locks the rows and settles exactly
     once; whichever call arrives second is a no-op.

Nothing the browser sends is trusted: the amount comes from the Order,
the settlement decision from Paystack's verify endpoint.

Expert payouts are deliberately not here - Accounts pays those manually
against withdrawal requests (payments/).
"""

import logging
import uuid
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from flask import current_app
from sqlalchemy.orm import lazyload

from extensions import db
from orders.checkout import (
    CHECKOUT_ABANDONED,
    CHECKOUT_FAILED,
    CHECKOUT_PAID,
    CHECKOUT_PENDING,
    OrderCheckout,
    utcnow,
)
from orders.order import Order
from utils import paystack
from utils.exceptions import ConflictError, NotFoundError, ValidationError
from utils.transaction import transaction

log = logging.getLogger(__name__)

PAYSTACK_GATEWAY = "Paystack"
PAYSTACK_PRODUCT = "scholardesk_order"
REFERENCE_PREFIX = "SDP-"

# A pending checkout younger than this is handed back as-is on a repeat
# "Pay" click instead of opening a second Paystack session.
REUSE_WINDOW = timedelta(minutes=30)


def to_minor(amount):
    minor = (Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(minor)


def _callback_url():
    base = current_app.config.get(
        "CUSTOMER_FRONTEND_URL", "https://portal.scholardesk.pro"
    ).rstrip("/")
    return f"{base}/payments/callback"


def serialize_checkout(checkout):
    pending = checkout.status == CHECKOUT_PENDING
    return {
        "reference": checkout.reference,
        "status": checkout.status,
        "authorizationUrl": checkout.authorization_url if pending else None,
        "accessCode": checkout.access_code if pending else None,
        "amount": float(Decimal(checkout.amount_minor) / 100),
        "currency": checkout.currency,
        "orderId": str(checkout.order_id),
        "paidAt": checkout.paid_at.isoformat() if checkout.paid_at else None,
        "createdAt": checkout.created_at.isoformat() if checkout.created_at else None,
    }


# ---------------------------------------------------------------------------
# 1. Start
# ---------------------------------------------------------------------------

def start_checkout(order, user):
    if order is None or order.customer_id != user.id:
        raise NotFoundError("Order not found.")

    if order.status == "paid":
        raise ConflictError("This order has already been paid for.")

    if order.status not in ("pending", "failed"):
        raise ConflictError(
            "This order cannot be paid in its current state.",
            {"status": order.status},
        )

    if not user.email:
        raise ValidationError("An email address is required to pay.")

    amount_minor = to_minor(order.amount)
    if amount_minor <= 0:
        raise ValidationError("Order amount must be greater than zero.")

    currency = (order.currency or "USD").upper()

    # The row is written first so the reference exists before Paystack
    # can call the webhook with it. Two rapid clicks serialise on the
    # order row lock, and the second one finds the first checkout above.
    with transaction():
        db.session.query(Order).filter(Order.id == order.id).with_for_update().one()

        existing = (
            OrderCheckout.query.filter_by(
                order_id=order.id,
                status=CHECKOUT_PENDING,
                amount_minor=amount_minor,
                currency=currency,
            )
            .filter(OrderCheckout.created_at >= utcnow() - REUSE_WINDOW)
            .filter(OrderCheckout.authorization_url.isnot(None))
            .order_by(OrderCheckout.created_at.desc())
            .first()
        )
        if existing:
            return existing

        checkout = OrderCheckout(
            order_id=order.id,
            customer_id=user.id,
            amount_minor=amount_minor,
            currency=currency,
            reference=f"{REFERENCE_PREFIX}{uuid.uuid4().hex[:20].upper()}",
            status=CHECKOUT_PENDING,
        )
        db.session.add(checkout)

    try:
        data = paystack.initialize_transaction(
            email=user.email,
            amount_minor=amount_minor,
            currency=currency,
            reference=checkout.reference,
            callback_url=_callback_url(),
            metadata={
                "product": PAYSTACK_PRODUCT,
                "checkout_id": str(checkout.id),
                "order_id": str(order.id),
                "order_reference": order.reference,
                "user_id": user.id,
            },
        )
    except Exception:
        # Never leave a pending row behind that the reuse window would
        # later hand back without an authorization URL.
        with transaction():
            checkout.status = CHECKOUT_FAILED
        raise

    with transaction():
        checkout.authorization_url = data.get("authorization_url")
        checkout.access_code = data.get("access_code")

    return checkout


# ---------------------------------------------------------------------------
# 2. Fulfil (redirect verify + webhook)
# ---------------------------------------------------------------------------

def _settle_order(order, checkout):
    """
    Apply the effects of a confirmed payment. Runs inside the caller's
    transaction with the order row already locked.
    """
    order.status = "paid"
    order.gateway = PAYSTACK_GATEWAY
    order.payment_reference = checkout.reference

    if order.source_type == "request":
        order.fulfillment_stage = "matching_writer"

        from customer_orders.service import _log_activity

        _log_activity(
            order,
            actor="customer",
            title="Payment received",
            detail=(
                f"{order.currency} {order.amount} via Paystack "
                f"(ref {checkout.reference})"
            ),
        )

    elif order.source_type == "material" and order.material_id:
        from exam_materials.exam_material import ExamMaterial

        material = (
            db.session.query(ExamMaterial)
            .filter(ExamMaterial.id == order.material_id)
            .with_for_update()
            .first()
        )
        if material is not None:
            material.downloads = (material.downloads or 0) + 1
            material.revenue = (material.revenue or 0) + order.amount


def fulfil_checkout(reference, gateway_data=None):
    checkout = OrderCheckout.query.filter_by(reference=reference).first()
    if not checkout:
        raise NotFoundError("Payment not found.")
    if checkout.status == CHECKOUT_PAID:
        return checkout

    data = gateway_data or paystack.verify_transaction(reference)
    gw_status = data.get("status")
    settled_order = None

    with transaction():
        checkout = (
            OrderCheckout.query.options(lazyload("*"))
            .filter_by(reference=reference)
            .with_for_update()
            .one()
        )
        if checkout.status == CHECKOUT_PAID:
            return checkout

        checkout.gateway_response = paystack.summarise_gateway_data(data)

        if gw_status != "success":
            if gw_status in ("failed", "reversed"):
                checkout.status = CHECKOUT_FAILED
            elif gw_status == "abandoned":
                checkout.status = CHECKOUT_ABANDONED
            return checkout

        if int(data.get("amount") or 0) != checkout.amount_minor or (
            (data.get("currency") or "").upper() != checkout.currency
        ):
            log.error("[checkout] amount/currency mismatch on %s: %s", reference, data)
            checkout.status = CHECKOUT_FAILED
            return checkout

        order = (
            db.session.query(Order)
            .options(lazyload("*"))
            .filter(Order.id == checkout.order_id)
            .with_for_update()
            .one()
        )

        checkout.status = CHECKOUT_PAID
        checkout.paid_at = utcnow()

        if order.status == "paid":
            # A second successful attempt against an already-paid order
            # (two browser tabs, say). Money was taken twice: record it,
            # never settle twice, and let the support team refund it.
            log.error(
                "[checkout] duplicate payment %s for already-paid order %s",
                reference,
                order.reference,
            )
        else:
            _settle_order(order, checkout)
            settled_order = order

    if settled_order is not None:
        _alert(
            f"Payment received - {settled_order.item_title}",
            (
                f"{settled_order.currency} {settled_order.amount} received via "
                f"Paystack for {settled_order.reference} (ref {checkout.reference})."
            ),
            checkout.reference,
        )
    else:
        _alert(
            "Duplicate payment needs a refund",
            (
                f"Paystack payment {checkout.reference} succeeded for an order "
                "that was already paid. Please refund it."
            ),
            checkout.reference,
        )

    return checkout


def _alert(subject, message, reference):
    try:
        from users.mailer_service import send_internal_alert

        send_internal_alert(subject=subject, message=message, action_path="/orders")
    except Exception:  # an email failure must never undo a settled payment
        log.exception("[checkout] alert failed for %s", reference)


def verify_for_customer(reference, user):
    """Redirect-return path: verify, then enforce ownership."""
    checkout = OrderCheckout.query.filter_by(reference=reference).first()
    if checkout is None or checkout.customer_id != user.id:
        raise NotFoundError("Payment not found.")
    return fulfil_checkout(reference)
