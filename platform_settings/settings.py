# platform_settings/settings.py
"""
Platform-wide, admin-configurable flags shared across the ScholarDesk
sites - currently just the expert/writer-hiring switch.

Deliberately a narrow, dedicated model rather than the much larger
"workspace settings" (brand, SLAs, notifications, team) the admin
frontend's settingsService.ts already sketches out under
/admin/settings - that surface is still unbuilt/out of scope; this is
a separate, single-purpose singleton so the two don't collide when
the bigger settings feature eventually gets built.

Singleton pattern: exactly one row, id=1, fetched/created on demand
by platform_settings/service.py::get_settings(). This avoids adding
an application-startup migration step just to seed one row.
"""

from datetime import datetime, timezone

from extensions import db


class PlatformSettings(db.Model):
    __tablename__ = "platform_settings"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # Public contract (see auth-portal frontend repo,
    # src/lib/platform.ts): GET /platform/settings ->
    # { writer_hiring_open: boolean, hiring_notice?: string }
    writer_hiring_open = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    hiring_notice = db.Column(
        db.String(500),
        nullable=True,
    )

    updated_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            "writer_hiring_open": self.writer_hiring_open,
            "hiring_notice": self.hiring_notice,
            "updated_at": (
                self.updated_at.isoformat()
                if self.updated_at
                else None
            ),
        }
