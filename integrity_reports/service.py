# integrity_reports/service.py

import hashlib
from datetime import datetime, timezone

from integrity_reports.constants import UPLOAD_SUBDIR
from integrity_reports.integrity_report import (
    IntegrityReport,
    IntegrityStatus,
)
from extensions import db
from utils.exceptions import NotFoundError
from utils.pagination import paginate_query
from utils.transaction import transaction
from utils.uploads import ALLOWED_DOCUMENT_EXTENSIONS, MAX_DOCUMENT_BYTES, save_uploaded_file


def _get_report_or_raise(report_id, user):
    report = db.session.get(IntegrityReport, report_id)

    if not report or report.customer_id != user.id:
        raise NotFoundError(
            "Integrity report not found.",
            {"report_id": str(report_id)},
        )

    return report


def list_reports(user, page=1, per_page=20):
    query = (
        IntegrityReport.query.filter(
            IntegrityReport.customer_id == user.id
        )
        .order_by(IntegrityReport.submitted_at.desc())
    )

    items, pagination = paginate_query(query, page, per_page)

    return {
        "items": [report.to_dict() for report in items],
        "pagination": pagination,
    }


def submit_scan(user, fields):
    file_path = save_uploaded_file(
        fields.get("uploaded_file"),
        UPLOAD_SUBDIR.format(user_id=user.id),
        allowed_extensions=ALLOWED_DOCUMENT_EXTENSIONS,
        max_bytes=MAX_DOCUMENT_BYTES,
    )

    with transaction():
        report = IntegrityReport(
            customer_id=user.id,
            file_name=fields["file_name"],
            word_count=fields["word_count"],
            file_path=file_path,
            check_ai=fields["check_ai"],
            check_plagiarism=fields["check_plagiarism"],
            status=IntegrityStatus.PROCESSING,
        )

        db.session.add(report)
        db.session.flush()

        # Run the (placeholder) scan synchronously so the endpoint
        # contract works end to end without a background-job runner.
        # See the module docstring in integrity_reports/integrity_report.py.
        _run_scan(report)

        return report


def _run_scan(report):
    """
    Deterministic, clearly-labelled placeholder scorer.

    Produces a stable score per document (same input -> same score)
    so the UI behaves sensibly in demos/tests, without pretending to
    be a real AI-detection or plagiarism-matching engine. Replace this
    function with a call to a real provider (Turnitin, Copyleaks,
    GPTZero, Originality.ai, ...) before relying on these numbers for
    anything academic-integrity-consequential.
    """

    digest = hashlib.sha256(
        f"{report.file_name}:{report.word_count}".encode("utf-8")
    ).hexdigest()

    ai_score = int(digest[:2], 16) % 15 if report.check_ai else None
    plagiarism_score = (
        int(digest[2:4], 16) % 10 if report.check_plagiarism else None
    )

    report.ai_score = ai_score
    report.plagiarism_score = plagiarism_score
    report.status = IntegrityStatus.READY
    report.completed_at = datetime.now(timezone.utc)

    if report.check_plagiarism and plagiarism_score and plagiarism_score > 0:
        report.top_matches = [
            {
                "source": "Open access repository match",
                "overlap": round(plagiarism_score * 0.6, 1),
            }
        ]
    else:
        report.top_matches = []

    db.session.flush()
