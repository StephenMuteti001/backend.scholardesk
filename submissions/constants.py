# submissions/constants.py

MAX_FILES = 20
MAX_NOTE_LENGTH = 20_000

# Mirrors customer_orders/constants.py::UPLOAD_SUBDIR's pattern, kept
# separate because submissions are keyed by order, not by
# user_id/request reference.
UPLOAD_SUBDIR = "submissions/{order_id}"
