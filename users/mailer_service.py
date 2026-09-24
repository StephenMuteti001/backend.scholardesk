# users/mailer_service.py
"""
Centralised transactional-email sending.

Every outbound email in the app should be sent from a function in
here (or, for very module-specific notifications, a sibling function
that still calls utils.mailer.send_email + render_template the same
way) so that:

  - there is exactly one COMPANY_NAME / branding source,
  - every template's expected variables are documented in one place,
  - other modules (expert_applications, orders, payments, ...) import
    from here instead of re-implementing send_email/render_template
    plumbing inline, per the "reuse the existing implementation"
    convention used throughout this codebase.

NOTE: `User.full_name` is the canonical name accessor (users/user.py) -
`.name` still exists too, as a backward-compatible alias to it. Either
works; functions below use `.full_name`.
"""

from datetime import datetime

from flask import current_app, render_template

from utils.mailer import send_email

COMPANY_NAME = "ScholarDesk"


def _year():
    return datetime.utcnow().year


def _frontend_url(path=""):
    """Auth/marketing portal (verify-email, login OTP, register)."""
    base = current_app.config["FRONTEND_URL"].rstrip("/")
    return f"{base}{path}"


def _customer_url(path=""):
    base = current_app.config["CUSTOMER_FRONTEND_URL"].rstrip("/")
    return f"{base}{path}"


def _expert_url(path=""):
    base = current_app.config["EXPERT_FRONTEND_URL"].rstrip("/")
    return f"{base}{path}"


def _admin_url(path=""):
    base = current_app.config["ADMIN_FRONTEND_URL"].rstrip("/")
    return f"{base}{path}"


# ---------------------------------------------------------------------------
# Account / auth
# ---------------------------------------------------------------------------

def send_verification_email(user, token):
    verify_url = _frontend_url(f"/verify-email?token={token}")

    html = render_template(
        "emails/verify_email.html",
        title="Verify your account",
        full_name=user.name,
        verify_url=verify_url,
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject=f"Verify your {COMPANY_NAME} account",
        html=html,
    )


def send_login_otp(user, otp):
    html = render_template(
        "emails/login_otp.html",
        title="Your login code",
        full_name=user.name,
        otp=otp,
        expires_in_minutes=10,
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject=f"Your {COMPANY_NAME} login code",
        html=html,
    )


def send_account_suspension_email(
    user,
    suspension_type,
    reasons,
    notes=None,
    suspended_until=None,
):
    duration_text = (
        suspended_until.strftime("%B %d, %Y")
        if suspension_type == "temporary" and suspended_until
        else "Indefinite"
    )

    html = render_template(
        "emails/account_suspended.html",
        title="Account Suspension",
        full_name=user.name,
        suspension_type=suspension_type,
        reasons=reasons,
        notes=notes,
        duration_text=duration_text,
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject=f"{COMPANY_NAME} Account Update",
        html=html,
    )


def send_account_reactivated_email(user):
    html = render_template(
        "emails/account_reactivated.html",
        title="Account Reactivated",
        full_name=user.name,
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject=f"Your {COMPANY_NAME} account has been reactivated",
        html=html,
    )


# ---------------------------------------------------------------------------
# Expert applications (expert_applications/routes.py)
# ---------------------------------------------------------------------------

def send_application_received_email(user):
    html = render_template(
        "emails/application_received.html",
        title="Application Received",
        full_name=user.name,
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject=f"We've received your {COMPANY_NAME} application",
        html=html,
    )


def send_application_approved_email(user, feedback=None):
    html = render_template(
        "emails/application_approved.html",
        title="Application Approved",
        full_name=user.name,
        feedback=feedback,
        onboarding_url=_expert_url("/"),
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject=f"Your {COMPANY_NAME} application has been approved",
        html=html,
    )


def send_application_rejected_email(user, feedback=None):
    html = render_template(
        "emails/application_rejected.html",
        title="Application Update",
        full_name=user.name,
        feedback=feedback,
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject=f"An update on your {COMPANY_NAME} application",
        html=html,
    )


def send_deposit_approved_email(user):
    html = render_template(
        "emails/deposit_approved.html",
        title="Deposit Approved",
        full_name=user.name,
        dashboard_url=_expert_url("/"),
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject=f"Your {COMPANY_NAME} account is now active",
        html=html,
    )


# ---------------------------------------------------------------------------
# Orders (orders/service.py, requests/service.py)
# ---------------------------------------------------------------------------

def send_bid_accepted_email(user, order_title):
    html = render_template(
        "emails/bid_accepted.html",
        title="Bid Accepted",
        full_name=user.name,
        order_title=order_title,
        dashboard_url=_expert_url("/orders"),
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject=f"You've been assigned: {order_title}",
        html=html,
    )


def send_new_order_admin_notification(admin_user, order, customer_name, customer_email):
    html = render_template(
        "emails/new_order_admin_notification.html",
        title="New Order Submitted",
        admin_name=admin_user.full_name,
        order=order,
        customer_name=customer_name,
        customer_email=customer_email,
        dashboard_url=_admin_url("/orders"),
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=admin_user.email,
        subject="New order awaiting assignment",
        html=html,
    )


def send_order_cancelled_email(user, order_title, reason=None):
    html = render_template(
        "emails/order_cancelled.html",
        title="Order Cancelled",
        full_name=user.name,
        order_title=order_title,
        reason=reason,
        dashboard_url=_expert_url("/orders"),
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject=f"Order cancelled: {order_title}",
        html=html,
    )


def send_order_completed_email(user, order_title, amount):
    html = render_template(
        "emails/order_completed.html",
        title="Order Completed",
        full_name=user.name,
        order_title=order_title,
        amount=amount,
        dashboard_url=_expert_url("/earnings"),
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject=f"Order completed: {order_title}",
        html=html,
    )


def send_order_restored_email(user, order_title, restored_status):
    html = render_template(
        "emails/order_restored.html",
        title="Order Restored",
        full_name=user.name,
        order_title=order_title,
        restored_status=restored_status,
        dashboard_url=_expert_url("/orders"),
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject=f"Order restored: {order_title}",
        html=html,
    )


# ---------------------------------------------------------------------------
# Payments / withdrawals (payments/service.py)
# ---------------------------------------------------------------------------

def send_payout_paid_email(user, payment):
    html = render_template(
        "emails/payout_paid.html",
        title="Payout paid",
        full_name=user.full_name,
        period_start=payment.period_start.isoformat(),
        period_end=payment.period_end.isoformat(),
        amount=payment.amount,
        currency=payment.currency,
        dashboard_url=_expert_url("/earnings"),
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject="Your ScholarDesk payout has been paid",
        html=html,
    )


def send_payout_on_hold_email(user, payment, reason=None):
    html = render_template(
        "emails/payout_on_hold.html",
        title="Payout on hold",
        full_name=user.full_name,
        period_start=payment.period_start.isoformat(),
        period_end=payment.period_end.isoformat(),
        amount=payment.amount,
        currency=payment.currency,
        reason=reason,
        dashboard_url=_expert_url("/earnings"),
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject="Your ScholarDesk payout is on hold",
        html=html,
    )


# ---------------------------------------------------------------------------
# Generic notification (customers/service.py message_customer / bulk email)
# ---------------------------------------------------------------------------

def send_notification_email(user, message, sender_team=None, subject=None):
    html = render_template(
        "emails/notification.html",
        title=subject or f"A message from {COMPANY_NAME}",
        full_name=user.name,
        message=message,
        sender_team=sender_team or f"The {COMPANY_NAME} Team",
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject=subject or f"A message from {COMPANY_NAME}",
        html=html,
    )


def send_internal_alert(subject, message, action_path=None, action_label="Open in admin"):
    """
    Support-team-facing alert (new counter-offer, submission awaiting
    review, refund requested, expert declined an assignment, etc.) -
    goes to the shared SUPPORT_TEAM_EMAIL inbox rather than every
    individual admin. `action_path` is a root-relative path on the
    admin app, e.g. "/orders" or "/requests".
    """
    full_message = message

    if action_path:
        full_message += f'<br/><br/><a href="{_admin_url(action_path)}">{action_label}</a>'

    html = render_template(
        "emails/notification.html",
        title=subject,
        full_name="Team",
        message=full_message,
        sender_team=f"{COMPANY_NAME} Platform",
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=current_app.config["SUPPORT_TEAM_EMAIL"],
        subject=subject,
        html=html,
    )


# ---------------------------------------------------------------------------
# Prospective-customer outreach (marketing - not tied to a user account)
# ---------------------------------------------------------------------------

def send_prospective_outreach_email(to_email, full_name):
    html = render_template(
        "emails/prospective_outreach.html",
        title=f"Introducing {COMPANY_NAME}",
        full_name=full_name,
        onboarding_url=_frontend_url("/"),
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=to_email,
        subject=f"Introducing {COMPANY_NAME}",
        html=html,
    )


def send_prospective_order_wizard_email(to_email, full_name):
    html = render_template(
        "emails/prospective2.html",
        title=f"A faster way to order on {COMPANY_NAME}",
        full_name=full_name,
        onboarding_url=_customer_url("/new-request"),
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=to_email,
        subject=f"Ordering on {COMPANY_NAME} just got easier",
        html=html,
    )


# ---------------------------------------------------------------------------
# Request / order lifecycle - quote issued, invoice on acceptance
# ---------------------------------------------------------------------------
#
# These two are the revenue-critical pair: a quote lands, we need the
# customer to come back and act on it; once they accept, we need to
# get them paid without friction. See customer_orders/service.py
# (issue is triggered from requests/service.py::issue_quote and
# customer_orders/service.py::accept_quote respectively).

def send_quote_issued_email(user, request_obj, quote):
    html = render_template(
        "emails/quote_issued.html",
        title="Your quote is ready",
        customer_name=user.full_name,
        order_title=request_obj.title,
        amount=quote.get("amount"),
        currency=quote.get("currency") or "USD",
        portal_url=_customer_url(f"/orders/{request_obj.id}"),
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject=f"Your {COMPANY_NAME} quote is ready to review",
        html=html,
    )


def send_invoice_email(user, order, quote=None):
    html = render_template(
        "emails/invoice.html",
        title="Your ScholarDesk invoice",
        invoice_number=order.reference,
        issue_date=datetime.utcnow().strftime("%B %d, %Y"),
        customer_name=user.full_name,
        customer_email=user.email,
        order_reference=order.reference,
        order_title=order.item_title,
        delivery_schedule=(quote or {}).get("delivery_schedule"),
        amount=order.amount,
        currency=order.currency,
        pay_url=_customer_url(f"/orders/{order.id}"),
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=user.email,
        subject=f"Invoice {order.reference} - payment due",
        html=html,
    )


# ---------------------------------------------------------------------------
# Fulfilment lifecycle - expert assigned, work delivered, submission reviewed
# ---------------------------------------------------------------------------

def send_expert_assigned_email(expert_user, order, budget):
    html = render_template(
        "emails/expert_assigned.html",
        title="New order assigned to you",
        expert_name=expert_user.full_name,
        order_title=order.item_title,
        order_reference=order.reference,
        currency=order.currency,
        budget=budget,
        order_url=_expert_url(f"/orders/{order.id}"),
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=expert_user.email,
        subject=f"You've been assigned order {order.reference}",
        html=html,
    )


def send_submission_delivered_email(customer_user, order, submission):
    html = render_template(
        "emails/submission_delivered.html",
        title="New delivery on your order",
        customer_name=customer_user.full_name,
        order_title=order.item_title,
        order_reference=order.reference,
        version=submission.version,
        order_url=_customer_url(f"/orders/{order.id}"),
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=customer_user.email,
        subject=f"New delivery on order {order.reference}",
        html=html,
    )


def send_submission_reviewed_email(expert_user, order, outcome, note=None):
    """
    outcome: "approved" | "revision_requested" | "rejected"
    """
    subject_by_outcome = {
        "approved": f"Order {order.reference} approved - nice work!",
        "revision_requested": f"Revision requested on order {order.reference}",
        "rejected": f"Order {order.reference} was rejected by the customer",
    }

    html = render_template(
        "emails/submission_reviewed.html",
        title="Update on your delivery",
        expert_name=expert_user.full_name,
        order_title=order.item_title,
        order_reference=order.reference,
        outcome=outcome,
        note=note,
        order_url=_expert_url(f"/orders/{order.id}"),
        company_name=COMPANY_NAME,
        year=_year(),
    )

    send_email(
        to=expert_user.email,
        subject=subject_by_outcome.get(outcome, f"Update on order {order.reference}"),
        html=html,
    )
