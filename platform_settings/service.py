# platform_settings/service.py

from extensions import db
from platform_settings.settings import PlatformSettings
from utils.exceptions import ValidationError
from utils.transaction import transaction

SETTINGS_ROW_ID = 1


def get_settings():
    """
    Fetch the singleton settings row, creating it with defaults on
    first use so callers never have to think about seeding.
    """
    settings = db.session.get(PlatformSettings, SETTINGS_ROW_ID)

    if settings:
        return settings

    with transaction():
        settings = PlatformSettings(
            id=SETTINGS_ROW_ID,
            writer_hiring_open=True,
            hiring_notice=None,
        )

        db.session.add(settings)
        db.session.flush()

    return settings


def update_settings(payload, actor):
    payload = payload or {}

    settings = get_settings()

    with transaction():
        if "writer_hiring_open" in payload:
            value = payload["writer_hiring_open"]

            if not isinstance(value, bool):
                raise ValidationError(
                    "writer_hiring_open must be a boolean.",
                    {"field": "writer_hiring_open"},
                )

            settings.writer_hiring_open = value

        if "hiring_notice" in payload:
            notice = payload["hiring_notice"]

            if notice is not None and not isinstance(notice, str):
                raise ValidationError(
                    "hiring_notice must be a string.",
                    {"field": "hiring_notice"},
                )

            if notice and len(notice) > 500:
                raise ValidationError(
                    "hiring_notice must not exceed 500 characters.",
                    {"field": "hiring_notice"},
                )

            settings.hiring_notice = notice or None

        settings.updated_by = actor.id if actor else None

        db.session.flush()

    return settings
