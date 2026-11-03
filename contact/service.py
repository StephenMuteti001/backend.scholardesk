# contact/service.py
import html
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app, render_template
from sqlalchemy import or_

from contact.contact_message import CONTACT_STATUSES, CONTACT_TOPICS, ContactMessage
from extensions import db
from utils.exceptions import NotFoundError, ServiceError, ValidationError
from utils.mailer import send_email

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

# Abuse limits for the unauthenticated form.
MAX_PER_IP_PER_HOUR = 5
MAX_PER_EMAIL_PER_DAY = 10

LIMITS = {"name": (2, 120), "subject": (3, 200), "message": (10, 5000)}


class RateLimitedError(ServiceError):
    status_code = 429

    def __init__(self, message):
        super().__init__(code="RATE_LIMITED", message=message, status_code=429)


def _clean(value):
    return value.strip() if isinstance(value, str) else ""


def validate_contact_payload(payload):
    data = {
        "name": _clean(payload.get("name")),
        "email": _clean(payload.get("email")).lower(),
        "subject": _clean(payload.get("subject")),
        "message": _clean(payload.get("message")),
        "topic": _clean(payload.get("topic")) or "general",
        "source_page": _clean(payload.get("source_page"))[:255] or None,
    }
    errors = {}
    for field, (lo, hi) in LIMITS.items():
        length = len(data[field])
        if length == 0:
            errors[field] = "This field is required."
        elif length < lo:
            errors[field] = f"Please enter at least {lo} characters."
        elif length > hi:
            errors[field] = f"Please keep this under {hi} characters."
    if not data["email"]:
        errors["email"] = "This field is required."
    elif len(data["email"]) > 255 or not EMAIL_RE.match(data["email"]):
        errors["email"] = "Please enter a valid email address."
    if data["topic"] not in CONTACT_TOPICS:
        errors["topic"] = "Please choose a valid topic."
    if errors:
        raise ValidationError("Please check the highlighted fields.", details=errors)
    return data


def _new_reference():
    return "CT-" + secrets.token_hex(3).upper()


def _enforce_rate_limits(ip, email):
    now = datetime.now(timezone.utc)
    if ip:
        recent_ip = ContactMessage.query.filter(
            ContactMessage.ip_address == ip,
            ContactMessage.created_at >= now - timedelta(hours=1),
        ).count()
        if recent_ip >= MAX_PER_IP_PER_HOUR:
            raise RateLimitedError(
                "You've sent several messages in a short time. Please wait a little "
                "while before trying again, or email us directly."
            )
    recent_email = ContactMessage.query.filter(
        ContactMessage.email == email,
        ContactMessage.created_at >= now - timedelta(days=1),
    ).count()
    if recent_email >= MAX_PER_EMAIL_PER_DAY:
        raise RateLimitedError(
            "We've already received several messages from this email today. "
            "Our team will reply to them shortly."
        )


def _notify(msg):
    """Best effort: the message is already saved, so mail failures are
    logged, never surfaced to the visitor."""
    year = datetime.now(timezone.utc).year
    try:
        body = (
            f"<strong>From:</strong> {html.escape(msg.name)} &lt;{html.escape(msg.email)}&gt;<br/>"
            f"<strong>Topic:</strong> {html.escape(msg.topic)}<br/>"
            f"<strong>Subject:</strong> {html.escape(msg.subject)}<br/><br/>"
            f"{html.escape(msg.message).replace(chr(10), '<br/>')}"
        )
        send_email(
            to=current_app.config["SUPPORT_TEAM_EMAIL"],
            subject=f"[Contact {msg.reference}] {msg.subject}",
            html=render_template(
                "emails/notification.html",
                title=f"New contact message {msg.reference}",
                full_name="Team",
                message=body,
                sender_team="ScholarDesk Website",
                company_name="ScholarDesk",
                year=year,
            ),
            reply_to=msg.email,
        )
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Contact %s: support alert failed", msg.reference)
    try:
        send_email(
            to=msg.email,
            subject=f"We've received your message ({msg.reference})",
            html=render_template(
                "emails/notification.html",
                title="Thanks for contacting ScholarDesk",
                full_name=msg.name,
                message=(
                    "Thanks for reaching out. A member of our team has your message "
                    f"(reference <strong>{msg.reference}</strong>) and will reply to this "
                    "email address, usually within a few hours and always within 24 hours."
                ),
                sender_team="ScholarDesk Support",
                company_name="ScholarDesk",
                year=year,
            ),
        )
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Contact %s: acknowledgement failed", msg.reference)


def create_contact_message(payload, ip=None, user_agent=None):
    data = validate_contact_payload(payload)
    _enforce_rate_limits(ip, data["email"])
    msg = ContactMessage(
        reference=_new_reference(),
        ip_address=(ip or "")[:64] or None,
        user_agent=(user_agent or "")[:400] or None,
        **data,
    )
    db.session.add(msg)
    db.session.commit()
    _notify(msg)
    return msg


def list_contact_messages(page=1, per_page=20, status=None, search=None):
    query = ContactMessage.query
    if status:
        query = query.filter(ContactMessage.status == status)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                ContactMessage.name.ilike(pattern),
                ContactMessage.email.ilike(pattern),
                ContactMessage.subject.ilike(pattern),
                ContactMessage.reference.ilike(pattern),
            )
        )
    per_page = max(1, min(per_page, 100))
    pagination = query.order_by(ContactMessage.created_at.desc()).paginate(
        page=max(page, 1), per_page=per_page, error_out=False
    )
    return pagination


def update_contact_message(message_id, payload):
    msg = db.session.get(ContactMessage, message_id)
    if not msg:
        raise NotFoundError("Contact message not found.")
    status = payload.get("status")
    if status is not None:
        if status not in CONTACT_STATUSES:
            raise ValidationError(
                "Invalid status.", details={"status": f"Use one of: {', '.join(CONTACT_STATUSES)}."}
            )
        msg.status = status
    if "admin_note" in payload:
        note = payload.get("admin_note")
        msg.admin_note = note.strip()[:5000] if isinstance(note, str) else None
    db.session.commit()
    return msg
