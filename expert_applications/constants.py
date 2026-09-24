# expert_applications/constants.py

from expert_applications.expert_application import ExpertApplicationStatus

# ---------------------------------------------------------------------------
# Statuses
#
# Re-exported from the model so callers only ever need to import from
# one of expert_applications.constants / expert_applications.expert_application,
# and so the source of truth stays the model itself.
# ---------------------------------------------------------------------------

APPLICATION_STATUSES = ExpertApplicationStatus.CHOICES

# Statuses that mean "a decision has already been made" - once an
# application reaches one of these, admins may not approve/reject it
# again without first reopening it.
DECIDED_STATUSES = (
    ExpertApplicationStatus.APPROVED,
    ExpertApplicationStatus.REJECTED,
    ExpertApplicationStatus.WITHDRAWN,
)

# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

APPLICATION_SORT_FIELDS = {
    "created_at",
    "updated_at",
    "status",
    "country",
}

DEFAULT_SORT_BY = "created_at"
DEFAULT_SORT_DIRECTION = "desc"

# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100

# ---------------------------------------------------------------------------
# Uploads
#
# Sub-directories (relative to UPLOAD_FOLDER, namespaced per applicant)
# that expert-application files are written under. See utils/uploads.py.
# ---------------------------------------------------------------------------

UPLOAD_SUBDIR_ESSAY = "expert-applications/{user_id}/essay"
UPLOAD_SUBDIR_CV = "expert-applications/{user_id}/cv"
UPLOAD_SUBDIR_WORK_SAMPLES = "expert-applications/{user_id}/work-samples"
UPLOAD_SUBDIR_DEGREE_CERTIFICATES = (
    "expert-applications/{user_id}/degree-certificates"
)

MAX_WORK_SAMPLES = 10
MAX_DEGREE_CERTIFICATES = 10
