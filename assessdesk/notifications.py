# assessdesk/notifications.py
"""
User-facing AssessDesk emails. Sent from a background thread so a slow
SMTP server never adds latency to consume/balance requests.
"""

import logging
import threading
from datetime import datetime

from flask import current_app, render_template

from utils.mailer import send_email

log = logging.getLogger(__name__)

COMPANY_NAME = "AssessDesk by ScholarDesk"


def _send_async(to, subject, full_name, message):
    app = current_app._get_current_object()

    def _run():
        with app.app_context():
            try:
                html = render_template(
                    "emails/notification.html",
                    title=subject,
                    full_name=full_name,
                    message=message,
                    sender_team="The AssessDesk Team",
                    company_name=COMPANY_NAME,
                    year=datetime.utcnow().year,
                )
                send_email(to=to, subject=subject, html=html)
            except Exception:
                log.exception("[assessdesk] failed to send '%s' to %s", subject, to)

    threading.Thread(target=_run, daemon=True).start()


def _fmt_utc(dt):
    return dt.strftime("%d %b %Y, %H:%M UTC")


def send_low_balance(user, remaining):
    if remaining <= 0:
        subject = "You're out of AssessDesk questions"
        message = (
            "You've used all your AssessDesk questions. Top up at "
            "https://assessdesk.scholardesk.pro before your next session."
        )
    else:
        subject = f"Only {remaining} AssessDesk question{'s' if remaining != 1 else ''} left"
        message = (
            f"You have {remaining} question{'s' if remaining != 1 else ''} left. "
            "Top up now at https://assessdesk.scholardesk.pro so you aren't caught short mid-session."
        )
    _send_async(user.email, subject, user.full_name, message)


def send_expiry_warning(user, grant, hours):
    subject = f"{grant.questions_remaining} AssessDesk questions expire within {hours} hours"
    message = (
        f"{grant.questions_remaining} of your questions expire on {_fmt_utc(grant.expires_at)} "
        "(shown in UTC; your app shows your local time). Use them or top up to keep going."
    )
    _send_async(user.email, subject, user.full_name, message)


def send_grace_started(user, grant, usable_until):
    subject = "Your AssessDesk questions have expired — 3-hour grace period started"
    message = (
        f"Your {grant.questions_remaining} remaining questions passed their expiry date. "
        f"You can still use them until {_fmt_utc(usable_until)}; after that they're forfeited. "
        "Top up at https://assessdesk.scholardesk.pro to keep your balance."
    )
    _send_async(user.email, subject, user.full_name, message)


def send_purchase_receipt(user, purchase, grant):
    subject = f"{purchase.questions} AssessDesk questions added"
    message = (
        f"Payment received ({purchase.currency} {purchase.amount_minor / 100:,.2f}, ref "
        f"{purchase.reference}). {purchase.questions} questions were added to your account and "
        f"are valid until {_fmt_utc(grant.expires_at)}."
    )
    _send_async(user.email, subject, user.full_name, message)
