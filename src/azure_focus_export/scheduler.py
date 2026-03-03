# SPDX-License-Identifier: AGPL-3.0-only

"""Recurring export scheduler — sets up monthly FOCUS exports for ongoing data."""

import logging
from datetime import datetime, timedelta

from .config import AppConfig
from .exports_api import ExportsApiClient, ExportsApiError
from .utils import console

logger = logging.getLogger(__name__)

# Default recurrence window: 10 years into the future
DEFAULT_RECURRENCE_YEARS = 10


class RecurringScheduler:
    """Creates and manages scheduled monthly FOCUS exports."""

    def __init__(self, api_client: ExportsApiClient, config: AppConfig):
        self._api = api_client
        self._config = config

    def setup_monthly_export(
        self,
        export_name: str = None,
        dry_run: bool = False,
    ) -> dict:
        """Create or update a recurring monthly FOCUS export.

        This export runs monthly and exports the previous month's data.
        It's idempotent — if the export already exists, it will be updated.

        Args:
            export_name: Optional custom name. Defaults to "{prefix}-monthly".
            dry_run: If True, only show what would be done.

        Returns:
            The created/updated export resource.
        """
        prefix = self._config.export.export_name_prefix
        name = export_name or f"{prefix}-monthly"

        now = datetime.utcnow()
        # Schedule starts from the 1st of next month
        if now.month == 12:
            start = datetime(now.year + 1, 1, 1)
        else:
            start = datetime(now.year, now.month + 1, 1)

        # Recurrence window
        end = datetime(now.year + DEFAULT_RECURRENCE_YEARS, 12, 31)

        recurrence_from = start.strftime("%Y-%m-%dT00:00:00Z")
        recurrence_to = end.strftime("%Y-%m-%dT00:00:00Z")

        console.print(f"\n[bold]Setting up recurring monthly FOCUS export[/bold]")
        console.print(f"  Export name: {name}")
        console.print(f"  Scope: {self._config.scope.scope_uri}")
        console.print(f"  Timeframe: TheLastMonth (previous month's data)")
        console.print(f"  Recurrence: Monthly from {recurrence_from[:10]} to {recurrence_to[:10]}")
        console.print(f"  Format: {self._config.export.format} ({self._config.export.compression})")
        console.print(f"  Storage: {self._config.storage.account_name}/{self._config.storage.container}/{self._config.storage.root_folder}")

        if dry_run:
            console.print("\n[yellow]DRY RUN — no export will be created[/yellow]")
            return {}

        try:
            result = self._api.create_export(
                export_name=name,
                export_type="FocusCost",
                time_period_from="",  # Not used for TheLastMonth
                time_period_to="",    # Not used for TheLastMonth
                timeframe="TheLastMonth",
                schedule_status="Active",
                schedule_recurrence="Monthly",
                recurrence_period_from=recurrence_from,
                recurrence_period_to=recurrence_to,
            )

            next_run = result.get("properties", {}).get("nextRunTimeEstimate", "Unknown")
            console.print(f"\n[green]Monthly export created successfully![/green]")
            console.print(f"  Next scheduled run: {next_run}")
            return result

        except ExportsApiError as e:
            console.print(f"\n[red]Failed to create monthly export: {e}[/red]")
            raise
