# support_chat/constants.py

from support_chat.support_chat import ChatAuthor, ChatStatus

CHAT_STATUSES = ChatStatus.CHOICES
CHAT_AUTHORS = ChatAuthor.CHOICES

# Statuses a customer is allowed to (re)open a thread into by sending a
# new message - matches docs/API.md: "support-side, customer read-only"
# for explicit status changes, but sending a message always reopens.
REOPEN_ON_MESSAGE_FROM_STATUSES = (ChatStatus.RESOLVED, ChatStatus.ARCHIVED)

DEFAULT_AGENT_NAME = "Support Team"

MAX_SUBJECT_LENGTH = 255
MAX_MESSAGE_LENGTH = 10_000

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100
