# integrity_reports/constants.py

from integrity_reports.integrity_report import IntegrityStatus

INTEGRITY_STATUSES = IntegrityStatus.CHOICES

MAX_FILE_NAME_LENGTH = 255
MAX_WORD_COUNT = 200_000

UPLOAD_SUBDIR = "integrity-reports/{user_id}"

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100
