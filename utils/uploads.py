# utils/uploads.py
"""
Shared local-disk upload helper.

exam_materials/service.py already models file attachment via a
storage_key/file_url pair supplied by the client (i.e. it expects
uploads to go straight to object storage). expert_applications, by
contrast, works with simple form-encoded multipart submissions and
stores plain file paths on the model (essay_file_path, cv_file_path,
work_samples, degree_certificates) - so it needs an actual "save this
upload to disk" helper.

This is the single place that logic should live, rather than each
module re-implementing its own copy of secure_filename() + uuid
namespacing (the writer-applications reference implementation had it
inlined in application_service.py - centralising it here is the fix).
"""

import os
import uuid

from flask import current_app
from werkzeug.utils import secure_filename

from utils.exceptions import ValidationError

ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024


def save_uploaded_file(file_storage, subdir, *, allowed_extensions=None, max_bytes=None):
    """
    Persist an uploaded file under UPLOAD_FOLDER/<subdir>/ with a
    collision-proof filename, and return the absolute path written.

    Returns None when `file_storage` is falsy, so callers can do:

        path = save_uploaded_file(files.get("cv"), f"{user.id}/cv")
    """

    if not file_storage:
        return None

    upload_folder = current_app.config.get("UPLOAD_FOLDER")

    if not upload_folder:
        raise RuntimeError(
            "UPLOAD_FOLDER is not configured on the Flask app."
        )

    filename = secure_filename(file_storage.filename or "")

    if not filename:
        raise ValidationError(
            "Uploaded file must have a valid filename."
        )

    extension = os.path.splitext(filename)[1].lower()
    if allowed_extensions is not None and extension not in allowed_extensions:
        raise ValidationError("Unsupported file type. Upload PDF, DOC, DOCX or TXT files only.")

    stream = file_storage.stream
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    if max_bytes is not None and size > max_bytes:
        raise ValidationError("Uploaded file must not exceed 25MB.")

    unique_name = f"{uuid.uuid4().hex}_{filename}"

    target_dir = os.path.join(upload_folder, subdir)
    os.makedirs(target_dir, exist_ok=True)

    full_path = os.path.join(target_dir, unique_name)
    file_storage.save(full_path)

    return full_path


def save_uploaded_files(file_storages, subdir, **validation):
    """
    Persist multiple uploads (e.g. request.files.getlist(...)) under
    the same subdirectory and return the list of paths written.
    """
    return [
        save_uploaded_file(file_storage, subdir, **validation)
        for file_storage in file_storages
        if file_storage
    ]


def relative_upload_path(absolute_path):
    """
    Convert an absolute path previously returned by
    save_uploaded_file()/save_uploaded_files() into a path relative to
    UPLOAD_FOLDER, suitable for building a download URL with
    url_for(..., filename=relative_upload_path(path)).
    """
    if not absolute_path:
        return None

    upload_folder = current_app.config.get("UPLOAD_FOLDER")

    if not upload_folder:
        return absolute_path

    return os.path.relpath(absolute_path, upload_folder)


def resolve_upload_path(relative_path):
    """
    Resolve a path relative to UPLOAD_FOLDER back to an absolute path,
    guarding against path traversal outside of UPLOAD_FOLDER.

    Raises ValidationError if the resolved path escapes UPLOAD_FOLDER.
    """
    upload_folder = current_app.config.get("UPLOAD_FOLDER")

    if not upload_folder:
        raise RuntimeError(
            "UPLOAD_FOLDER is not configured on the Flask app."
        )

    safe_root = os.path.abspath(upload_folder)
    candidate = os.path.abspath(
        os.path.join(safe_root, relative_path)
    )

    if not candidate.startswith(safe_root):
        raise ValidationError("Invalid file path.")

    return candidate
