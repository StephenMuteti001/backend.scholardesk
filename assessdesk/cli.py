# assessdesk/cli.py
"""
Scheduled maintenance.

    flask assessdesk sweep

Run every 10 minutes (cron / systemd timer / Render cron job). The
3-hour grace window means a 10-minute cadence keeps notifications and
forfeiture accurate to within ~10 minutes of the true UTC instant;
balance reads never depend on the sweep (expiry is also enforced at
read/debit time).
"""

import click
from flask.cli import AppGroup

from assessdesk import service

assessdesk_cli = AppGroup("assessdesk", help="AssessDesk maintenance commands.")


@assessdesk_cli.command("sweep")
def sweep():
    stats = service.run_sweep()
    click.echo(f"assessdesk sweep: {stats}")
