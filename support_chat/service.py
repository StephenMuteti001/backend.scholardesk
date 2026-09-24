# support_chat/service.py

from datetime import datetime, timezone

from support_chat.constants import (
    DEFAULT_AGENT_NAME,
    REOPEN_ON_MESSAGE_FROM_STATUSES,
)
from support_chat.support_chat import ChatAuthor, ChatStatus, SupportMessage, SupportThread
from extensions import db
from utils.exceptions import NotFoundError
from utils.transaction import transaction


def _get_thread_or_raise(thread_id, user):
    thread = db.session.get(SupportThread, thread_id)

    if not thread or thread.customer_id != user.id:
        raise NotFoundError(
            "Support thread not found.",
            {"thread_id": str(thread_id)},
        )

    return thread


def _agent_name(thread):
    if thread.agent:
        return f"{thread.agent.name}, Client Support"
    return DEFAULT_AGENT_NAME


def thread_to_dict(thread):
    last_message = (
        thread.messages[-1].body if thread.messages else ""
    )

    return {
        "id": str(thread.id),
        "subject": thread.subject,
        "orderReference": thread.order_reference,
        "status": thread.status,
        "agentName": _agent_name(thread),
        "unread": thread.client_unread_count,
        "updatedAt": thread.updated_at.isoformat(),
        "lastMessage": last_message,
    }


def list_threads(user):
    threads = (
        SupportThread.query.filter(SupportThread.customer_id == user.id)
        .order_by(SupportThread.updated_at.desc())
        .all()
    )

    return [thread_to_dict(thread) for thread in threads]


def get_thread(thread_id, user):
    return _get_thread_or_raise(thread_id, user)


def list_messages(thread_id, user):
    """
    Fetching messages marks the thread read for the customer, matching
    docs/API.md: "GET /support-chat/{chatId}/messages | Messages
    (marks thread read)".
    """
    thread = _get_thread_or_raise(thread_id, user)

    with transaction():
        if thread.client_unread_count:
            thread.client_unread_count = 0

        db.session.flush()

    return [message.to_dict() for message in thread.messages]


def start_thread(user, subject, order_reference=None):
    is_expert = getattr(user, "is_expert", False)

    with transaction():
        thread = SupportThread(
            customer_id=user.id,
            subject=subject,
            order_reference=order_reference,
            status=ChatStatus.OPEN,
        )

        db.session.add(thread)
        db.session.flush()

        opening_message = SupportMessage(
            thread_id=thread.id,
            author=ChatAuthor.SUPPORT,
            author_name=DEFAULT_AGENT_NAME,
            body=(
                "You're chatting with the ScholarDesk support team. "
                "A specialist agent will pick this up shortly."
                + (
                    ""
                    if is_expert
                    else " Experts are never part of this conversation."
                )
            ),
        )

        db.session.add(opening_message)
        db.session.flush()

        return thread


def send_message(thread_id, user, body):
    thread = _get_thread_or_raise(thread_id, user)

    author = (
        ChatAuthor.EXPERT
        if getattr(user, "is_expert", False)
        else ChatAuthor.CUSTOMER
    )

    with transaction():
        message = SupportMessage(
            thread_id=thread.id,
            author=author,
            author_name=user.full_name,
            author_user_id=user.id,
            body=body,
        )

        db.session.add(message)

        thread.updated_at = datetime.now(timezone.utc)

        if thread.status in REOPEN_ON_MESSAGE_FROM_STATUSES:
            thread.status = ChatStatus.OPEN

        db.session.flush()

        return message
